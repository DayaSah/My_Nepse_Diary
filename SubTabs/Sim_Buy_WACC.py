import streamlit as st
import pandas as pd

# --- NEPSE Fee Configuration & Calculator ---
def calculate_nepse_fees(qty, price, transaction_type, include_dp=True, is_long_term=False, current_wacc=0):
    amount = qty * price
    
    # Broker commission tiers
    if amount <= 50000:
        broker_pct = 0.0040
    elif amount <= 500000:
        broker_pct = 0.0037
    elif amount <= 2000000:
        broker_pct = 0.0034
    elif amount <= 10000000:
        broker_pct = 0.0030
    else:
        broker_pct = 0.0027

    broker_commission = amount * broker_pct
    sebon_fee = amount * 0.00015
    dp_fee = 25.0 if include_dp else 0.0

    total_fees = broker_commission + sebon_fee + dp_fee

    if transaction_type == 'BUY':
        total_cost = amount + total_fees
        return total_cost, broker_commission, total_fees, 0.0
    else: # SELL
        # CGT calculation based on profit
        profit = amount - (current_wacc * qty) - total_fees
        cgt = 0.0
        if profit > 0:
            cgt_rate = 0.05 if is_long_term else 0.075
            cgt = profit * cgt_rate
            
        net_receivable = amount - total_fees - cgt
        return net_receivable, broker_commission, total_fees, cgt

# --- App Initialization ---

st.title("Advanced NEPSE WACC & Trade Simulator")
st.write("Understand your true costs. Factor in commissions, taxes, and fees before you execute.")

# --- Sidebar Controls ---
st.sidebar.header("Simulation Settings")
data_source = st.sidebar.radio("Portfolio Source", ["Manual Entry", "Database (Neon)"])
include_dp = st.sidebar.checkbox("Include DP Fee (Rs 25/txn)", value=True)

initial_qty = 0
initial_wacc = 0.0
symbol = "CUSTOM"

# --- Data Loading ---
if data_source == "Database (Neon)":
    try:
        conn = st.connection("neon", type="sql")
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        
        if port_df.empty:
            st.sidebar.warning("Database portfolio is empty. Switching to manual.")
            data_source = "Manual Entry"
        else:
            symbols = port_df['symbol'].unique().tolist()
            symbol = st.sidebar.selectbox("Select Asset", symbols)
            
            # Simple aggregation (Note: True FIFO is recommended for production)
            asset_data = port_df[port_df['symbol'] == symbol]
            buys = asset_data[asset_data['transaction_type'] == 'BUY']
            total_bought = buys['qty'].sum()
            total_cost = (buys['qty'] * buys['price']).sum()
            
            sells = asset_data[asset_data['transaction_type'] == 'SELL']['qty'].sum()
            
            initial_qty = total_bought - sells
            initial_wacc = total_cost / total_bought if total_bought > 0 else 0.0
            
            # Allow user to override DB WACC
            st.sidebar.markdown("---")
            st.sidebar.write("Override DB Values:")
            initial_wacc = st.sidebar.number_input("Starting WACC", value=float(initial_wacc))
            
    except Exception as e:
        st.sidebar.error("Failed to connect to DB. Using Manual Mode.")
        data_source = "Manual Entry"

if data_source == "Manual Entry":
    symbol = st.sidebar.text_input("Symbol", value="NABIL")
    initial_qty = st.sidebar.number_input("Current Quantity", min_value=0, value=100)
    initial_wacc = st.sidebar.number_input("Current WACC (Rs)", min_value=0.0, value=500.0)

# --- State Display ---
col1, col2, col3 = st.columns(3)
col1.metric("Asset", symbol)
col2.metric("Current Holdings", f"{initial_qty:,.0f} Units")
col3.metric("Current WACC", f"Rs {initial_wacc:,.2f}")

st.divider()

# --- Multiple Transactions Editor ---
st.subheader("Simulate Multiple Executions")
st.write("Add your anticipated buy and sell orders. The simulator processes them sequentially top-to-bottom.")

# Initialize an empty dataframe for the data editor
if 'trade_plan' not in st.session_state:
    st.session_state.trade_plan = pd.DataFrame(
        columns=["Type", "Qty", "Price", "Is_Long_Term"],
        data=[["BUY", 100, float(initial_wacc), False]]
    )

# Use data_editor to allow adding/removing multiple rows
edited_plan = st.data_editor(
    st.session_state.trade_plan,
    column_config={
        "Type": st.column_config.SelectboxColumn("Action", options=["BUY", "SELL"], required=True),
        "Qty": st.column_config.NumberColumn("Quantity", min_value=10, step=10, required=True),
        "Price": st.column_config.NumberColumn("Execution Price", min_value=1.0, format="%.2f", required=True),
        "Is_Long_Term": st.column_config.CheckboxColumn("Long Term Sell? (>365 Days)")
    },
    num_rows="dynamic",
    use_container_width=True
)

if st.button("Run Execution Analysis", type="primary"):
    current_qty = initial_qty
    current_wacc = initial_wacc
    
    results = []
    
    for index, row in edited_plan.iterrows():
        action = row['Type']
        qty = row['Qty']
        price = row['Price']
        is_lt = row['Is_Long_Term']
        
        if action == "BUY":
            total_cost, broker_comm, total_fees, _ = calculate_nepse_fees(
                qty, price, "BUY", include_dp
            )
            
            # Calculate new WACC
            current_value = current_qty * current_wacc
            current_qty += qty
            current_wacc = (current_value + total_cost) / current_qty
            
            results.append({
                "Action": "BUY", "Qty": qty, "Price": price, 
                "Fees": total_fees, "CGT": 0, "Cash Flow": -total_cost,
                "Running Qty": current_qty, "Running WACC": current_wacc
            })
            
        elif action == "SELL":
            if qty > current_qty:
                st.error(f"Row {index+1}: Cannot sell {qty} shares. Only {current_qty} available.")
                st.stop()
                
            net_receivable, broker_comm, total_fees, cgt = calculate_nepse_fees(
                qty, price, "SELL", include_dp, is_lt, current_wacc
            )
            
            current_qty -= qty
            # WACC does not change on sell, only quantity changes.
            if current_qty == 0:
                current_wacc = 0.0
                
            results.append({
                "Action": "SELL", "Qty": qty, "Price": price, 
                "Fees": total_fees, "CGT": cgt, "Cash Flow": net_receivable,
                "Running Qty": current_qty, "Running WACC": current_wacc
            })

    # Display Results
    res_df = pd.DataFrame(results)
    
    st.subheader("Execution Breakdown")
    st.dataframe(
        res_df.style.format({
            "Price": "{:.2f}", "Fees": "{:.2f}", "CGT": "{:.2f}", 
            "Cash Flow": "{:.2f}", "Running WACC": "{:.2f}"
        }), 
        use_container_width=True
    )
    
    st.markdown("### Final Position Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Final Quantity", f"{current_qty:,.0f}")
    
    wacc_diff = current_wacc - initial_wacc
    c2.metric("Final WACC", f"Rs {current_wacc:,.2f}", f"{wacc_diff:,.2f} Rs", delta_color="inverse")
    
    total_cash_flow = res_df['Cash Flow'].sum()
    c3.metric("Net Cash Flow from Trades", f"Rs {total_cash_flow:,.2f}")

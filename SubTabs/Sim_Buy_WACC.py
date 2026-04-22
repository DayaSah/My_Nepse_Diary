import streamlit as st
import pandas as pd

def calculate_nepse_fees(qty, price, transaction_type, include_dp=True, is_long_term=False, current_wacc=0):
    """
    Analyzes trade execution on both sides:
    Buy Side: Increases cost basis by adding commissions.
    Sell Side: Reduces net payout by subtracting commissions and CGT.
    """
    amount = qty * price
    
    # NEPSE Tiered Broker Commission
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
        # BUY SIDE: You pay more than the ticker price
        total_cost = amount + total_fees
        return total_cost, total_fees, 0.0
    else: 
        # SELL SIDE: You receive less than the ticker price
        # CGT is calculated on (Sales - Fees) - (WACC * Qty)
        cost_basis = current_wacc * qty
        profit = amount - total_fees - cost_basis
        cgt = 0.0
        if profit > 0:
            cgt_rate = 0.05 if is_long_term else 0.075
            cgt = profit * cgt_rate
            
        net_receivable = amount - total_fees - cgt
        return net_receivable, total_fees, cgt

def render(role):
    st.header("Advanced WACC & Execution Simulator")
    st.write("Simulate buys/sells with real NEPSE fees and manual WACC overrides.")

    # --- INPUT OVERRIDES ---
    with st.expander("🛠️ Manual Portfolio Overrides", expanded=True):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            custom_symbol = st.text_input("Symbol", value="NABIL")
        with col_b:
            manual_qty = st.number_input("Existing Quantity", min_value=0, value=100)
        with col_c:
            manual_wacc = st.number_input("Existing WACC (Rs)", min_value=0.0, value=500.0)
        
        include_dp = st.checkbox("Apply Rs 25 DP Fee to every transaction?", value=True)

    st.divider()

    # --- MULTIPLE TRANSACTION TABLE ---
    st.subheader("Step 1: Plan Multiple Transactions")
    st.info("The simulator processes these sequentially. Buy side increases WACC; Sell side reduces quantity.")
    
    if 'txn_buffer' not in st.session_state:
        st.session_state.txn_buffer = pd.DataFrame([
            {"Type": "BUY", "Qty": 50, "Price": manual_wacc * 0.95, "LT_Sell": False}
        ])

    edited_plan = st.data_editor(
        st.session_state.txn_buffer,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Type": st.column_config.SelectboxColumn("Action", options=["BUY", "SELL"], required=True),
            "Qty": st.column_config.NumberColumn("Quantity", min_value=1, step=10),
            "Price": st.column_config.NumberColumn("Price (Rs)", min_value=1.0),
            "LT_Sell": st.column_config.CheckboxColumn("LT (>1yr)?")
        }
    )

    # --- EXECUTION ANALYSIS ---
    if st.button("🚀 Execute Simulation", type="primary"):
        curr_qty = manual_qty
        curr_wacc = manual_wacc
        history = []

        for i, row in edited_plan.iterrows():
            if row["Type"] == "BUY":
                # BUY SIDE ANALYSIS
                total_outflow, fees, _ = calculate_nepse_fees(row["Qty"], row["Price"], "BUY", include_dp)
                
                # Math: (Old Value + New Outflow) / Total Qty
                new_total_qty = curr_qty + row["Qty"]
                curr_wacc = ((curr_qty * curr_wacc) + total_outflow) / new_total_qty
                curr_qty = new_total_qty
                
                history.append({
                    "Step": i+1, "Action": "BUY", "Qty": row["Qty"], "Price": row["Price"],
                    "Fees": fees, "CGT": 0.0, "Net Cashflow": -total_outflow, "New WACC": curr_wacc
                })
                
            elif row["Type"] == "SELL":
                # SELL SIDE ANALYSIS
                if row["Qty"] > curr_qty:
                    st.error(f"Row {i+1}: Insufficient shares to sell {row['Qty']}.")
                    continue
                
                total_inflow, fees, cgt = calculate_nepse_fees(row["Qty"], row["Price"], "SELL", include_dp, row["LT_Sell"], curr_wacc)
                curr_qty -= row["Qty"]
                
                history.append({
                    "Step": i+1, "Action": "SELL", "Qty": row["Qty"], "Price": row["Price"],
                    "Fees": fees, "CGT": cgt, "Net Cashflow": total_inflow, "New WACC": curr_wacc
                })

        # --- RESULTS DISPLAY ---
        st.subheader("Simulation Results")
        res_df = pd.DataFrame(history)
        st.table(res_df.style.format({
            "Price": "{:.2f}", "Fees": "{:.2f}", "CGT": "{:.2f}", 
            "Net Cashflow": "{:.2f}", "New WACC": "{:.2f}"
        }))

        c1, c2, c3 = st.columns(3)
        c1.metric("Final Units", f"{curr_qty:,.0f}")
        c2.metric("Final WACC", f"Rs {curr_wacc:,.2f}", f"{curr_wacc - manual_wacc:,.2f} Rs", delta_color="inverse")
        c3.metric("Net Cash Movement", f"Rs {res_df['Net Cashflow'].sum():,.2f}")

        if curr_wacc > row["Price"] and row["Type"] == "BUY":
            st.warning("Decision Critique: You are buying above your current WACC, which is increasing your break-even point. Ensure the fundamental upside justifies this.")
        elif curr_wacc < manual_wacc:
            st.success("Decision Critique: Successfully averaged down. Your cost basis has improved.")

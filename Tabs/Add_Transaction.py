import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

def get_current_stock_info(conn, symbol):
    """Calculates current quantity, WACC, and First Buy Date for a specific stock."""
    if not symbol: return 0, 0.0, date.today()
    
    try:
        df = conn.query(f"SELECT * FROM portfolio WHERE symbol = '{symbol.upper()}'", ttl=0)
        if df.empty: return 0, 0.0, date.today()
        
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        buys = df[df['transaction_type'].str.upper() == 'BUY']
        sells = df[df['transaction_type'].str.upper() == 'SELL']
        
        # Calculate WACC and Qty
        total_buy_qty = buys['qty'].sum()
        total_buy_cost = (buys['qty'] * buys['price']).sum()
        wacc = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0.0
        net_qty = total_buy_qty - sells['qty'].sum()
        
        # Get First Purchase Date
        first_buy_date = buys['date'].min() if not buys.empty else date.today()
        
        return net_qty, wacc, first_buy_date
    except:
        return 0, 0.0, date.today()

def calculate_fees(qty, price, trx_type, include_dp, wacc=0.0, cgt_rate=0.05):
    """Core logic for NEPSE commissions and taxes."""
    base = qty * price
    
    # Tiered Broker Commission (NEPSE standard)
    if base <= 50000: comm_rate = 0.0040
    elif base <= 500000: comm_rate = 0.0037
    else: comm_rate = 0.0033
    
    broker_comm = max(10, base * comm_rate)
    sebon_fee = base * 0.00015
    dp_fee = 25.0 if include_dp else 0.0
    total_charges = broker_comm + sebon_fee + dp_fee
    
    if trx_type == "BUY":
        total_val = base + total_charges
        # Breakeven includes estimation for future sell charges (~0.5% + 25 DP)
        breakeven = (total_val + (total_val * 0.005) + 25) / qty 
        return {
            "base": base, "broker": broker_comm, "sebon": sebon_fee, 
            "dp": dp_fee, "fees": total_charges, "total": total_val, "be": breakeven
        }
    else:
        profit = (price - wacc) * qty
        cgt = max(0, profit * cgt_rate) if profit > 0 else 0
        receivable = base - total_charges - cgt
        return {
            "base": base, "broker": broker_comm, "sebon": sebon_fee, 
            "dp": dp_fee, "fees": total_charges, "total": receivable, "cgt": cgt, "profit": profit
        }

def render_page(role):
    st.title("📝 Trade & Settlement Engine")
    st.caption("Advanced NEPSE calculator with automated CGT and holding period analysis.")
    
    conn = st.connection("neon", type="sql")
    col_form, col_est = st.columns([1.3, 1])

    with col_form:
        with st.container(border=True):
            trx_type = st.radio("Transaction Type", ["BUY", "SELL"], horizontal=True)
            t_symbol = st.text_input("Stock Symbol", placeholder="e.g. NABIL").upper().strip()
            
            # 1. Fetch current stock data
            owned_qty, calc_wacc, first_date = get_current_stock_info(conn, t_symbol)
            
            c1, c2 = st.columns(2)
            t_qty = c1.number_input("Quantity", min_value=1, step=1, value=10)
            t_price = c2.number_input("Execution Price (Rs)", min_value=1.0, step=0.1, value=100.0)
            
            t_date = st.date_input("Transaction Date", value=date.today())

            # --- SELL SIDE SPECIFIC LOGIC ---
            user_wacc = calc_wacc
            cgt_val = 0.05 # Default
            
            if trx_type == "SELL":
                # Calculate Days Held
                days_held = (date.today() - first_date).days
                
                st.markdown(f"**Holding Info:** Purchased on `{first_date}` ({days_held} days ago)")
                
                # Portfolio Warning
                if t_qty > owned_qty:
                    st.error(f"⚠️ **Short Sell Warning:** You only own {owned_qty} units of {t_symbol}.")
                else:
                    st.success(f"✅ Portfolio Balance: {owned_qty} units available.")

                sc1, sc2 = st.columns(2)
                user_wacc = sc1.number_input("Adjusted WACC", value=float(calc_wacc), help="Calculated from your ledger. Edit if needed.")
                
                # Auto-select CGT Rate based on days
                default_tax_idx = 0 if days_held > 365 else 1
                cgt_selection = sc2.selectbox(
                    "CGT Rate", 
                    ["5% (Long Term > 1yr)", "7.5% (Short Term < 1yr)"],
                    index=default_tax_idx
                )
                cgt_val = 0.05 if "5%" in cgt_selection else 0.075

            # --- COMMON OPTIONS ---
            st.divider()
            include_dp = st.checkbox("Include DP Fee (Rs. 25)", value=True)
            
            # --- ACTION BUTTONS ---
            st.write("")
            btn_calc = st.button("🧮 Calculate Estimation", use_container_width=True)
            
            log_btn_label = "🚀 Buy / Average Stock" if trx_type == "BUY" else "🔻 Log Sell Transaction"
            btn_save = st.button(log_btn_label, type="primary", use_container_width=True)

    # ==========================================
    # CALCULATION ENGINE (Calculates every rerun for live feedback)
    # ==========================================
    res = calculate_fees(t_qty, t_price, trx_type, include_dp, user_wacc, cgt_val)

    with col_est:
        st.subheader("🧾 Settlement Bill")
        with st.container(border=True):
            if trx_type == "BUY":
                st.metric("Total Payable Amount", f"Rs {res['total']:,.2f}")
                st.metric("Breakeven Price", f"Rs {res['be']:,.2f}", help="Target price to cover both buy and sell fees.")
            else:
                st.metric("Final Receivable Amount", f"Rs {res['total']:,.2f}")
                st.write(f"⚖️ **Net Profit/Loss:** Rs {res['profit']:,.2f}")

            st.divider()
            st.write(f"🔸 **Base Amount:** Rs {res['base']:,.2f}")
            st.write(f"🔹 **Broker Commission:** Rs {res['broker']:,.2f}")
            st.write(f"🔹 **SEBON Fee:** Rs {res['sebon']:,.2f}")
            st.write(f"🔹 **DP Fee:** Rs {res['dp']:,.2f}")
            
            if trx_type == "SELL":
                st.write(f"🚩 **Capital Gains Tax ({cgt_val*100}%):** Rs {res['cgt']:,.2f}")
            
            st.divider()
            total_cost_of_trade = res['fees'] + (res.get('cgt', 0) if trx_type == "SELL" else 0)
            st.info(f"**Total Fees & Taxes:** Rs {total_cost_of_trade:,.2f}")

    # ==========================================
    # SAVE TO DATABASE
    # ==========================================
    if btn_save:
        if not t_symbol:
            st.error("Please enter a valid Stock Symbol.")
        else:
            try:
                with conn.session as s:
                    # 1. Insert into Portfolio
                    s.execute(text("""
                        INSERT INTO portfolio (date, symbol, qty, price, transaction_type) 
                        VALUES (:d, :s, :q, :p, :t)
                    """), {"d": t_date, "s": t_symbol, "q": t_qty, "p": t_price, "t": trx_type})
                    
                    # 2. Audit Logging
                    s.execute(text("""
                        INSERT INTO audit_log (action, symbol, details) 
                        VALUES (:act, :sym, :det)
                    """), {
                        "act": f"TRADE_{trx_type}", 
                        "sym": t_symbol, 
                        "det": f"{t_qty} units @ Rs {t_price} | Net: Rs {res['total']:.2f}"
                    })
                    s.commit()
                st.success(f"✅ {trx_type} logged for {t_symbol}!")
                st.balloons()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    # --- RECENT TRANSACTIONS ---
    st.markdown("---")
    st.markdown("### 🕒 Recent Entries")
    try:
        recent = conn.query("SELECT date, symbol, transaction_type as type, qty, price FROM portfolio ORDER BY id DESC LIMIT 5", ttl=0)
        st.dataframe(recent, use_container_width=True, hide_index=True)
    except:
        st.caption("No records found in the ledger.")

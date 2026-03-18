import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

def get_current_stock_info(conn, symbol):
    """Calculates current quantity and WACC for a specific stock."""
    if not symbol: return 0, 0.0
    df = conn.query(f"SELECT * FROM portfolio WHERE symbol = '{symbol.upper()}'", ttl=0)
    if df.empty: return 0, 0.0
    
    df.columns = [c.lower() for c in df.columns]
    buys = df[df['transaction_type'].str.upper() == 'BUY']
    sells = df[df['transaction_type'].str.upper() == 'SELL']
    
    total_buy_qty = buys['qty'].sum()
    total_buy_cost = (buys['qty'] * buys['price']).sum()
    wacc = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0.0
    
    net_qty = total_buy_qty - sells['qty'].sum()
    return net_qty, wacc

def calculate_fees(qty, price, trx_type, include_dp, wacc=0.0, cgt_rate=0.05):
    base = qty * price
    # Tiered Commission
    if base <= 50000: comm_rate = 0.0040
    elif base <= 500000: comm_rate = 0.0037
    else: comm_rate = 0.0033
    
    broker_comm = max(10, base * comm_rate)
    sebon_fee = base * 0.00015
    dp_fee = 25.0 if include_dp else 0.0
    total_charges = broker_comm + sebon_fee + dp_fee
    
    cgt = 0.0
    breakeven = 0.0
    
    if trx_type == "BUY":
        net_payable = base + total_charges
        # Breakeven = Total Cost / Qty / 0.995 (roughly accounts for sell fees)
        # More accurate: (Net_Payable + Sell_Charges + Sell_DP) / Qty
        breakeven = (net_payable + (net_payable * 0.005) + 25) / qty
        return {"base": base, "fees": total_charges, "total": net_payable, "cgt": 0, "be": breakeven}
    else:
        profit = (price - wacc) * qty
        if profit > 0:
            cgt = profit * cgt_rate
        net_receivable = base - total_charges - cgt
        return {"base": base, "fees": total_charges, "total": net_receivable, "cgt": cgt}

def render_page(role):
    st.title("📝 Trade & Settlement Engine")
    conn = st.connection("neon", type="sql")

    col_form, col_est = st.columns([1.2, 1])

    with col_form:
        with st.container(border=True):
            trx_type = st.radio("Transaction", ["BUY", "SELL"], horizontal=True)
            t_symbol = st.text_input("Stock Symbol", placeholder="NABIL").upper().strip()
            
            # Fetch Data for Sell Side
            owned_qty, calc_wacc = get_current_stock_info(conn, t_symbol)
            
            c1, c2 = st.columns(2)
            t_qty = c1.number_input("Quantity", min_value=1, step=1, value=10)
            t_price = c2.number_input("Price (Rs)", min_value=1.0, step=0.1, value=100.0)
            
            # Sell Side Logic: Warning & WACC
            user_wacc = 0.0
            if trx_type == "SELL":
                st.warning(f"Portfolio: You own **{owned_qty}** units.")
                if t_qty > owned_qty:
                    st.error("⚠️ **SHORT SELLING ALERT:** You are selling more than you own.")
                
                user_wacc = st.number_input("Your Buy WACC (for CGT)", value=float(calc_wacc), help="Editable for manual adjustment")
            
            include_dp = st.checkbox("Include DP Fee (Rs. 25)", value=True)
            cgt_val = 0.05
            if trx_type == "SELL":
                cgt_type = st.selectbox("CGT Rate", ["5% (Long Term)", "7.5% (Short Term)"])
                cgt_val = 0.05 if "5%" in cgt_type else 0.075

            st.divider()
            btn_save = st.button(f"💾 Log {trx_type} Transaction", type="primary", use_container_width=True)

    # Calculation Engine
    res = calculate_fees(t_qty, t_price, trx_type, include_dp, user_wacc, cgt_val)

    with col_est:
        st.subheader("🧾 Estimated Bill")
        with st.container(border=True):
            st.write(f"**Action:** {trx_type} {t_symbol}")
            label = "Total Payable" if trx_type == "BUY" else "Net Receivable"
            st.metric(label, f"Rs {res['total']:,.2f}")
            
            if trx_type == "BUY":
                st.metric("Breakeven Price", f"Rs {res['be']:,.2f}", help="Target sell price to cover all fees.")

            st.divider()
            st.write(f"💵 **Base Amount:** Rs {res['base']:,.2f}")
            st.write(f"📑 **Total Charges:** Rs {res['fees']:,.2f}")
            if trx_type == "SELL":
                st.write(f"⚖️ **Profit Tax (CGT):** Rs {res['cgt']:,.2f}")
                st.caption(f"Estimated Profit: Rs {(t_price - user_wacc)*t_qty:,.2f}")
            st.divider()
            st.info("Charges include: Broker Commission, SEBON fee, and DP fee.")

    if btn_save:
        if not t_symbol:
            st.error("Enter a Symbol")
        else:
            try:
                with conn.session as s:
                    s.execute(text("INSERT INTO portfolio (date, symbol, qty, price, transaction_type) VALUES (:d, :s, :q, :p, :t)"),
                              {"d": date.today(), "s": t_symbol, "q": t_qty, "p": t_price, "t": trx_type})
                    s.commit()
                st.success("Transaction Saved!")
                st.balloons()
            except Exception as e:
                st.error(f"Error: {e}")

    # Recent Data
    st.markdown("### 🕒 Recent Ledger")
    recent = conn.query("SELECT date, symbol, transaction_type as type, qty, price FROM portfolio ORDER BY id DESC LIMIT 5", ttl=0)
    st.dataframe(recent, use_container_width=True, hide_index=True)

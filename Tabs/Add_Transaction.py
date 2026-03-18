import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

def calculate_nepse_charges(qty, price, trx_type, include_dp=True, cgt_rate=0.05):
    """Calculates exact NEPSE fees and commissions."""
    base_amount = qty * price
    
    # 1. Broker Commission (Tiered)
    if base_amount <= 50000:
        commission_rate = 0.0040 # 0.40%
    elif base_amount <= 500000:
        commission_rate = 0.0037 # 0.37%
    else:
        commission_rate = 0.0033 # 0.33%
        
    broker_commission = base_amount * commission_rate
    
    # Minimum commission rule (Rs. 10)
    if broker_commission < 10:
        broker_commission = 10
        
    # 2. SEBON Fee (0.015%)
    sebon_fee = base_amount * 0.00015
    
    # 3. DP Fee (Rs. 25)
    dp_fee = 25.0 if include_dp else 0.0
    
    total_charges = broker_commission + sebon_fee + dp_fee
    
    if trx_type == "BUY":
        final_amount = base_amount + total_charges
        return {
            "base": base_amount,
            "broker": broker_commission,
            "sebon": sebon_fee,
            "dp": dp_fee,
            "total_fees": total_charges,
            "final": final_amount,
            "cgt": 0
        }
    else:
        # For Sells, CGT is usually on (Sell Price - Buy Price). 
        # Since we don't know the Buy Price here, we estimate CGT on 20% of Sell Value 
        # as a placeholder for 'Profit Tax' for the UI.
        estimated_profit = base_amount * 0.20 
        cgt = estimated_profit * cgt_rate
        final_amount = base_amount - total_charges - cgt
        return {
            "base": base_amount,
            "broker": broker_commission,
            "sebon": sebon_fee,
            "dp": dp_fee,
            "total_fees": total_charges,
            "final": final_amount,
            "cgt": cgt
        }

def render_page(role):
    st.title("📝 Trade Entry & Calculator")
    st.caption("Calculate NEPSE charges and log your trades to the master ledger.")

    conn = st.connection("neon", type="sql")

    if role == "View Only":
        st.warning("🔒 View Only mode: Entry disabled.")
        return

    # Create two columns: Left for Form, Right for Estimation
    col_form, col_est = st.columns([1.2, 1])

    with col_form:
        with st.container(border=True):
            trx_type = st.radio("Action Type", ["BUY", "SELL"], horizontal=True)
            
            t_symbol = st.text_input("Stock Symbol", placeholder="NABIL").upper().strip()
            
            c1, c2 = st.columns(2)
            t_qty = c1.number_input("Quantity", min_value=1, step=10, value=10)
            t_price = c2.number_input("Price (Rs)", min_value=1.0, step=1.0, value=200.0)
            
            t_date = st.date_input("Transaction Date", value=date.today())
            
            st.markdown("---")
            st.markdown("##### ⚙️ Options")
            use_dp = st.checkbox("Include DP Fee (Rs. 25)", value=True)
            
            cgt_val = 0.05
            if trx_type == "SELL":
                cgt_type = st.selectbox("CGT Rate", ["5% (Individual)", "7.5% (Short Term)"])
                cgt_val = 0.05 if "5%" in cgt_type else 0.075

            btn_calc = st.button("🧮 Calculate Estimation", use_container_width=True)
            btn_save = st.button(f"🚀 Confirm & Log {trx_type} Trade", type="primary", use_container_width=True)

    # ==========================================
    # LOGIC: ESTIMATION BOX
    # ==========================================
    res = calculate_nepse_charges(t_qty, t_price, trx_type, use_dp, cgt_val)

    with col_est:
        st.subheader("🧾 Settlement Summary")
        
        # Display the breakdown in a clean list
        with st.container(border=True):
            st.write(f"**Symbol:** {t_symbol if t_symbol else '---'}")
            st.metric("Final Payable/Receivable", f"Rs {res['final']:,.2f}")
            
            st.divider()
            
            st.write(f"🔹 **Base Amount:** Rs {res['base']:,.2f}")
            st.write(f"🔹 **Broker Comm:** Rs {res['broker']:,.2f}")
            st.write(f"🔹 **SEBON Fee:** Rs {res['sebon']:,.2f}")
            st.write(f"🔹 **DP Fee:** Rs {res['dp']:,.2f}")
            
            if trx_type == "SELL":
                st.write(f"🔸 **Est. CGT (on 20% profit):** Rs {res['cgt']:,.2f}")
            
            st.divider()
            st.info(f"**Total Charges:** Rs {res['total_fees'] + res['cgt']:,.2f}")

    # ==========================================
    # LOGIC: DATABASE SAVE
    # ==========================================
    if btn_save:
        if not t_symbol:
            st.error("Missing Symbol!")
        else:
            try:
                with conn.session as s:
                    # 1. Insert Transaction
                    s.execute(text("""
                        INSERT INTO portfolio (date, symbol, qty, price, transaction_type) 
                        VALUES (:date, :sym, :qty, :price, :type)
                    """), {"date": t_date, "sym": t_symbol, "qty": t_qty, "price": t_price, "type": trx_type})
                    
                    # 2. Log Activity
                    s.execute(text("""
                        INSERT INTO audit_log (action, symbol, details) 
                        VALUES (:act, :sym, :det)
                    """), {
                        "act": f"TRADE_{trx_type}", 
                        "sym": t_symbol, 
                        "det": f"{t_qty} units @ Rs {t_price} (Fees: Rs {res['total_fees']:.2f})"
                    })
                    s.commit()
                st.success(f"Successfully logged {t_symbol} {trx_type}")
                st.balloons()
            except Exception as e:
                st.error(f"Database Error: {e}")

    # 3. RECENT PREVIEW
    st.markdown("---")
    st.markdown("### 🕒 Recent Entries")
    recent = conn.query("SELECT date, symbol, transaction_type, qty, price FROM portfolio ORDER BY id DESC LIMIT 5", ttl=0)
    st.dataframe(recent, use_container_width=True, hide_index=True)

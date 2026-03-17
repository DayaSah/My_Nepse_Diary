import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date

def render_page(role):
    st.title("📝 Add Transaction")
    st.caption("Record your Buy and Sell orders. The portfolio and TMS will update automatically.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 0. SYSTEM LOGGING UTILITY
    # ==========================================
    def log_system_error(error_msg):
        """Silently logs errors to the audit_log table."""
        try:
            with conn.session as s:
                sql = text("INSERT INTO audit_log (action, details) VALUES ('SYSTEM_ERROR', :msg)")
                s.execute(sql, {"msg": str(error_msg)})
                s.commit()
        except:
            pass

    # ==========================================
    # 1. THE TRANSACTION FORM
    # ==========================================
    if role == "View Only":
        st.warning("🔒 View Only mode: You cannot add transactions.")
        return

    # Use a neat card-like container for the form
    with st.container(border=True):
        # Transaction Type Selector (Large Radio Buttons)
        trx_type = st.radio(
            "Transaction Type", 
            options=["BUY", "SELL"], 
            horizontal=True,
            help="Are you buying new shares or selling existing ones?"
        )

        st.divider()

        with st.form("trade_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                t_date = st.date_input("Transaction Date", value=date.today())
                t_symbol = st.text_input("Stock Symbol", placeholder="e.g. NABIL").upper().strip()
            
            with col2:
                t_qty = st.number_input("Quantity (Shares)", min_value=1, step=10)
                t_price = st.number_input("Execution Price (Rs)", min_value=1.0, step=1.0, format="%.2f")

            # --- Live Estimate Section (Visual Aid Only) ---
            st.markdown("##### 🧾 Estimated NEPSE Settlement")
            base_amount = t_qty * t_price
            
            # Rough NEPSE logic (approximate broker commission + 25 DP + 0.015% SEBON)
            estimated_broker = base_amount * 0.004 # roughly 0.4% average
            sebon_fee = base_amount * 0.00015
            dp_fee = 25.0
            
            if trx_type == "BUY":
                est_total = base_amount + estimated_broker + sebon_fee + dp_fee
                st.info(f"**Estimated Total Cost:** Rs {est_total:,.2f} *(Includes approx Rs {estimated_broker+sebon_fee+dp_fee:,.2f} in fees)*")
            else:
                cgt = (base_amount * 0.05) # Assuming 5% CGT for rough visual estimate
                est_total = base_amount - estimated_broker - sebon_fee - dp_fee - cgt
                st.info(f"**Estimated Bank Deposit:** Rs {est_total:,.2f} *(After approx Rs {estimated_broker+sebon_fee+dp_fee:,.2f} fees & 5% CGT)*")

            st.divider()
            submitted = st.form_submit_button(f"💾 Log {trx_type} Order", type="primary", use_container_width=True)

            # ==========================================
            # 2. SAVE LOGIC
            # ==========================================
            if submitted:
                if not t_symbol:
                    st.error("Please enter a valid stock symbol.")
                else:
                    try:
                        with conn.session as s:
                            # 1. Insert into Portfolio Table
                            sql = text("""
                                INSERT INTO portfolio (date, symbol, qty, price, transaction_type) 
                                VALUES (:date, :sym, :qty, :price, :type)
                            """)
                            s.execute(sql, {
                                "date": t_date, 
                                "sym": t_symbol, 
                                "qty": t_qty, 
                                "price": t_price, 
                                "type": trx_type
                            })
                            
                            # 2. Insert into Audit Log
                            audit_sql = text("""
                                INSERT INTO audit_log (action, symbol, details) 
                                VALUES (:act, :sym, :det)
                            """)
                            s.execute(audit_sql, {
                                "act": f"TRADE_{trx_type}", 
                                "sym": t_symbol, 
                                "det": f"{trx_type} {t_qty} units @ Rs {t_price}"
                            })
                            
                            s.commit()
                            
                        st.success(f"✅ Successfully logged {trx_type} of {t_qty} {t_symbol} shares!")
                        st.balloons()
                        
                    except Exception as e:
                        st.error("❌ Failed to save transaction.")
                        log_system_error(f"Trade Save Error ({trx_type} {t_symbol}): {e}")

    # ==========================================
    # 3. RECENT TRANSACTIONS PREVIEW
    # ==========================================
    st.markdown("### 🕒 Recent Transactions")
    try:
        recent_df = conn.query("SELECT date, symbol, transaction_type, qty, price FROM portfolio ORDER BY id DESC LIMIT 5")
        if not recent_df.empty:
            recent_df.columns = [c.capitalize() for c in recent_df.columns] # Make headers pretty
            st.dataframe(recent_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No recent transactions found.")
    except Exception as e:
        log_system_error(f"Recent Trade Fetch Error: {e}")

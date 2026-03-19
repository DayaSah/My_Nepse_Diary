import streamlit as st
import pandas as pd
from sqlalchemy import text
import plotly.express as px
from datetime import date

def render_page(role):
    st.title("🏦 TMS Command Center")
    st.caption("Cash Flow Reconciliation & Broker Ledger")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA LOADING
    try:
        df = conn.query("SELECT * FROM tms_trx ORDER BY date DESC", ttl=0)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"⚠️ Connection Error: {e}")
        df = pd.DataFrame()

    # --- DYNAMIC MEDIUM LOGIC ---
    existing_mediums = []
    if not df.empty and 'medium' in df.columns:
        existing_mediums = df['medium'].dropna().unique().tolist()
    medium_options = sorted(list(set(existing_mediums + ["Bank Transfer", "ConnectIPS", "Collateral", "Cheque"])))

    tms_tabs = st.tabs(["📊 Metrics", "📜 Ledger", "✍️ Log Entry"])

    # ==========================================
    # TAB 1: METRICS (Simplified Calculations)
    # ==========================================
    with tms_tabs[0]:
        if df.empty:
            st.info("No data found. Log a transaction or check Neon.")
        else:
            # Quick Math
            net_bal = df['amount'].sum()
            deposits = df[df['type'].str.upper() == 'DEPOSIT']
            total_in = (deposits['amount'] + deposits['charge']).sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Wallet Balance", f"Rs {net_bal:,.2f}")
            c2.metric("Total Principal In", f"Rs {total_in:,.2f}")
            c3.metric("Buying Power", f"Rs {net_bal + 10824:,.2f}")

    # ==========================================
    # TAB 2: LEDGER & STABLE DELETE
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Universal Ledger")
        if not df.empty:
            # We show the ID column now so you know which one to delete
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", help="Use this ID to delete mistakes"),
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Charges", format="Rs %.2f"),
                }
            )

            # --- STABLE DELETE UI ---
            st.divider()
            st.subheader("🗑️ Undo / Delete Transaction")
            with st.expander("Click here to delete an entry"):
                delete_id = st.number_input("Enter Transaction ID to delete", min_value=1, step=1)
                if st.button("Permanently Delete", type="primary"):
                    try:
                        with conn.session as s:
                            s.execute(text("DELETE FROM tms_trx WHERE id = :id"), {"id": delete_id})
                            s.commit()
                        st.success(f"Transaction #{delete_id} deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.info("Ledger is empty.")

    # ==========================================
    # TAB 3: LOG TRANSACTION (Correct Math)
    # ==========================================
    with tms_tabs[2]:
        if role == "View Only":
            st.warning("🔒 Admin access required.")
        else:
            with st.form("tms_form_v10"):
                c1, c2 = st.columns(2)
                t_date = c1.date_input("Date", value=date.today())
                t_type = c1.selectbox("Type", ["Deposit", "Withdrawal", "Buy", "Sell"])
                
                raw_amt = c2.number_input("Principal Amount (Rs)", min_value=0.0)
                t_charge = c2.number_input("Charges/Fees (Rs)", min_value=0.0)
                
                t_stock = st.text_input("Symbol (Optional)").upper()
                t_medium = st.selectbox("Medium", medium_options)
                
                # Math Logic
                if t_type == "Buy":
                    final_amt = -(raw_amt + t_charge)
                elif t_type == "Sell":
                    final_amt = (raw_amt - t_charge)
                elif t_type == "Withdrawal":
                    final_amt = -abs(raw_amt)
                else: # Deposit
                    final_amt = abs(raw_amt)

                if st.form_submit_button("Save Transaction"):
                    try:
                        with conn.session as s:
                            s.execute(text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge) 
                                VALUES (:d, :s, :t, :m, :a, :c)
                            """), {"d": t_date, "s": t_stock, "t": t_type, "m": t_medium, "a": final_amt, "c": t_charge})
                            s.commit()
                        st.success("Saved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

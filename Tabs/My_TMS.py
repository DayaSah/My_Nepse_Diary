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
        # Crucial: Ensure 'id' is selected
        df = conn.query("SELECT * FROM tms_trx ORDER BY date ASC", ttl=0)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"⚠️ Connection Error: {e}")
        df = pd.DataFrame()

    # --- DYNAMIC MEDIUM LOGIC ---
    existing_mediums = []
    if not df.empty and 'medium' in df.columns:
        existing_mediums = df['medium'].dropna().unique().tolist()
    
    defaults = ["Bank Transfer", "ConnectIPS", "Collateral", "Cheque"]
    medium_options = sorted(list(set(existing_mediums + defaults)))

    tms_tabs = st.tabs(["📊 Financial Metrics", "📜 Universal Ledger", "✍️ Log Transaction"])

    # ==========================================
    # LOGIC: SHARED CALCULATIONS
    # ==========================================
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df['running_balance'] = df['amount'].cumsum()
        display_df = df.sort_values(by="date", ascending=False)

        # 1. Total Cash In: (Amount + Charge) for Deposits
        deposits = df[df['type'].str.upper() == 'DEPOSIT']
        total_cash_in = (deposits['amount'] + deposits['charge']).sum()
        
        # 2. Total Cash Out: (Abs(Amount) - Charge) for Withdrawals (Net in Bank)
        withdrawals = df[df['type'].str.upper() == 'WITHDRAWAL']
        total_cash_out = (withdrawals['amount'].abs() - withdrawals['charge']).sum()
        
        net_cash_in_tms = total_cash_in - total_cash_out
        net_tms_balance = df['amount'].sum()
        
        buys = abs(df[df['type'].str.upper() == 'BUY']['amount'].sum())
        sells = df[df['type'].str.upper() == 'SELL']['amount'].sum()
        net_settlement = sells - buys
        
        base_collateral = 10824.0
        buying_power = net_tms_balance + base_collateral

    # ==========================================
    # TAB 1: FINANCIAL METRICS
    # ==========================================
    with tms_tabs[0]:
        if df.empty:
            st.info("No transactions logged yet.")
        else:
            st.subheader("💰 Cash Flow Summary")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Cash In", f"Rs {total_cash_in:,.2f}")
            col2.metric("Total Cash Out", f"Rs {total_cash_out:,.2f}")
            col3.metric("Net Principal in TMS", f"Rs {net_cash_in_tms:,.2f}")
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Net TMS Balance", f"Rs {net_tms_balance:,.2f}")
            m2.metric("Net Settlement", f"Rs {net_settlement:,.2f}", delta=f"{'Profit' if net_settlement > 0 else 'Loss'}")
            m3.metric("Buying Power", f"Rs {buying_power:,.2f}")

            st.subheader("📈 Liquidity Trend")
            fig = px.area(df, x='date', y='running_balance', color_discrete_sequence=['#00CC96'])
            st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER (Fixed Selection Error)
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Universal Ledger")
        if not df.empty:
            # FIX: selection_mode="row" works on all versions
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="row", 
                column_config={
                    "id": None, # Keep ID hidden
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Charges", format="Rs %.2f"),
                    "running_balance": st.column_config.NumberColumn("Net Balance", format="Rs %.2f"),
                },
                column_order=("date", "type", "stock", "amount", "charge", "running_balance", "status", "medium")
            )

            # Use modern selection access
            if hasattr(event, 'selection') and event.selection.rows:
                selected_index = event.selection.rows[0]
                row_to_delete = display_df.iloc[selected_index]
                
                st.warning(f"🗑️ Delete {row_to_delete['type']} of Rs {row_to_delete['amount']}?")
                if st.button("Confirm Permanent Delete", type="primary"):
                    try:
                        with conn.session as s:
                            s.execute(text("DELETE FROM tms_trx WHERE id = :id"), {"id": row_to_delete['id']})
                            s.commit()
                        st.success("Deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}. Check if 'id' column exists in database.")

    # ==========================================
    # TAB 3: LOG TRANSACTION (Fixed Math)
    # ==========================================
    with tms_tabs[2]:
        if role == "View Only":
            st.warning("🔒 Admin access required.")
        else:
            st.subheader("✍️ Log New Transaction")
            with st.form("tms_entry_v5", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    t_date = st.date_input("Date", value=date.today())
                    t_type = st.selectbox("Type", ["Buy", "Sell", "Deposit", "Withdrawal", "Charges"])
                    t_status = st.selectbox("Status", ["Settled", "Pending"])
                with c2:
                    t_stock = st.text_input("Symbol (Optional)").upper()
                    selected_medium = st.selectbox("Payment Medium", medium_options + ["➕ Add New..."])
                    t_medium = st.text_input("New Medium") if selected_medium == "➕ Add New..." else selected_medium
                with c3:
                    raw_amount = st.number_input("Amount (Rs)", min_value=0.0)
                    t_charge = st.number_input("Charges (Fees)", min_value=0.0)

                t_ref = st.text_input("Reference Code")
                t_remark = st.text_input("Remarks")

                # --- THE SMART MATH LOGIC ---
                if t_type == "Deposit":
                    final_amount = raw_amount # Charge is external (1000 + 10 extra)
                elif t_type == "Buy":
                    final_amount = -(raw_amount + t_charge) # Charge is deducted from wallet
                elif t_type == "Sell":
                    final_amount = (raw_amount - t_charge) # Received net after charges
                elif t_type in ["Withdrawal", "Charges"]:
                    final_amount = -abs(raw_amount)
                else:
                    final_amount = abs(raw_amount)

                if st.form_submit_button("💾 Save to Ledger", type="primary", use_container_width=True):
                    try:
                        with conn.session as s:
                            s.execute(text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark, status, reference) 
                                VALUES (:d, :s, :t, :m, :a, :c, :r, :st, :ref)
                            """), {"d": t_date, "s": t_stock, "t": t_type, "m": t_medium, 
                                   "a": final_amount, "c": t_charge, "r": t_remark, "st": t_status, "ref": t_ref})
                            s.commit()
                        st.success("✅ Saved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

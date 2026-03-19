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
        # We select * to ensure 'id' is available for the delete function
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

    # --- TAB NAVIGATION ---
    tms_tabs = st.tabs(["📊 Financial Metrics", "📜 Universal Ledger", "✍️ Log Transaction"])

    # ==========================================
    # LOGIC: SHARED CALCULATIONS
    # ==========================================
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        
        # 1. Sorting by date for accurate running balance
        df = df.sort_values(by="date", ascending=True)
        df['running_balance'] = df['amount'].cumsum()
        
        # 2. Display version (Newest first)
        display_df = df.sort_values(by="date", ascending=False)

        # 3. Total Cash In: Sum of (Principal + Charge) for Deposits
        # Example: Depo 1000 + 10 charge = 1010 leaves your bank.
        deposits = df[df['type'].str.upper() == 'DEPOSIT']
        total_cash_in = (deposits['amount'] + deposits['charge']).sum()
        
        # 4. Total Cash Out: Sum of (Abs(Principal) - Charge) for Withdrawals
        # Example: Withdraw 1000 - 10 charge = 990 arrives in your bank.
        withdrawals = df[df['type'].str.upper() == 'WITHDRAWAL']
        total_cash_out = (withdrawals['amount'].abs() - withdrawals['charge']).sum()
        
        # 5. Net Principal in TMS (Money tied up)
        net_cash_in_tms = total_cash_in - total_cash_out
        
        # 6. Net TMS Balance (Current Wallet)
        net_tms_balance = df['amount'].sum()
        
        # 7. Net Settlement (Stock trading performance)
        buys = abs(df[df['type'].str.upper() == 'BUY']['amount'].sum())
        sells = df[df['type'].str.upper() == 'SELL']['amount'].sum()
        net_settlement = sells - buys
        
        # 8. Buying Power
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
            col1.metric("Total Cash In", f"Rs {total_cash_in:,.2f}", help="Principal + Charges sent to Broker")
            col2.metric("Total Cash Out", f"Rs {total_cash_out:,.2f}", help="Net money received back in Bank")
            col3.metric("Net Principal in TMS", f"Rs {net_cash_in_tms:,.2f}", help="Total capital currently inside the system")
            
            st.divider()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Net TMS Balance", f"Rs {net_tms_balance:,.2f}", help="Usable cash in Wallet")
            m2.metric("Net Settlement", f"Rs {net_settlement:,.2f}", delta=f"{'Profit' if net_settlement > 0 else 'Loss'}")
            m3.metric("Buying Power", f"Rs {buying_power:,.2f}", help="Balance + 10,824 Free Collateral")

            st.subheader("📈 Wallet Balance Trend")
            fig = px.area(df, x='date', y='running_balance', color_discrete_sequence=['#00CC96'])
            fig.update_layout(xaxis_title="Date", yaxis_title="Balance (Rs)")
            st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER (With Fixed Delete)
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Universal Ledger")
        if not df.empty:
            # FIX: Using selection_mode="row" for compatibility
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="row",
                column_config={
                    "id": None, # Hide ID from user
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Charges", format="Rs %.2f"),
                    "running_balance": st.column_config.NumberColumn("Net Balance", format="Rs %.2f"),
                },
                column_order=("date", "type", "stock", "amount", "charge", "running_balance", "status", "medium", "reference")
            )

            # DELETE LOGIC
            if hasattr(event, 'selection') and event.selection.rows:
                selected_index = event.selection.rows[0]
                row_to_delete = display_df.iloc[selected_index]
                
                st.divider()
                st.warning(f"⚠️ Delete {row_to_delete['type']} entry for Rs {row_to_delete['amount']}?")
                if st.button("🗑️ Confirm Permanent Delete", type="primary", use_container_width=True):
                    try:
                        with conn.session as s:
                            s.execute(text("DELETE FROM tms_trx WHERE id = :id"), {"id": int(row_to_delete['id'])})
                            s.commit()
                        st.success("Transaction Deleted Successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.info("Ledger is empty.")

    # ==========================================
    # TAB 3: LOG TRANSACTION
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
                    t_type = st.selectbox("Type", ["Deposit", "Withdrawal", "Buy", "Sell", "Charges"])
                    t_status = st.selectbox("Status", ["Settled", "Pending"])
                with c2:
                    t_stock = st.text_input("Symbol (Optional)").upper()
                    selected_medium = st.selectbox("Payment Medium", medium_options + ["➕ Add New..."])
                    t_medium = st.text_input("New Medium Name") if selected_medium == "➕ Add New..." else selected_medium
                with c3:
                    raw_amount = st.number_input("Principal Amount (Rs)", min_value=0.0)
                    t_charge = st.number_input("Charges (Bank/Gateway/DP)", min_value=0.0)

                t_ref = st.text_input("Reference (Txn ID/Cheque)")
                t_remark = st.text_input("Remarks")

                # --- THE SMART MATH LOGIC ---
                # Deposit 1000 + 10 extra: Wallet gets 1000. Total Cash In calculation handles the +10.
                if t_type == "Deposit":
                    final_amount = raw_amount
                # Buy 1000 + 5 charge: Wallet loses 1005.
                elif t_type == "Buy":
                    final_amount = -(raw_amount + t_charge)
                # Sell 1000 - 5 charge: Wallet gets 995.
                elif t_type == "Sell":
                    final_amount = (raw_amount - t_charge)
                # Withdrawal/Pure Charge: Wallet loses principal.
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
                            """), {
                                "d": t_date, "s": t_stock, "t": t_type, "m": t_medium, 
                                "a": final_amount, "c": t_charge, "r": t_remark, 
                                "st": t_status, "ref": t_ref
                            })
                            s.commit()
                        st.success(f"✅ Success! Net Wallet impact: Rs {final_amount}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

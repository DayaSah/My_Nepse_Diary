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
        
        # Wallet Balance Calculation: Only the 'amount' affects the TMS wallet
        # (Charges are considered external 'extra' costs as per your requirement)
        df['running_balance'] = df['amount'].cumsum()
        display_df = df.sort_values(by="date", ascending=False)

        # 1. Total Cash In: Sum of (Amount + Charges) for all Deposits
        deposits = df[df['type'].str.upper() == 'DEPOSIT']
        total_cash_in = (deposits['amount'] + deposits['charge']).sum()
        
        # 2. Total Cash Out: Sum of (Abs(Amount) - Charges) for all Withdrawals (Net received in bank)
        withdrawals = df[df['type'].str.upper() == 'WITHDRAWAL']
        total_cash_out = (withdrawals['amount'].abs() - withdrawals['charge']).sum()
        
        # 3. Net Cash in TMS (External Capital Tied Up)
        net_cash_in_tms = total_cash_in - total_cash_out
        
        # 4. Net TMS Balance (Actual Cash in Wallet)
        net_tms_balance = df['amount'].sum()
        
        # 5. Net Settlement (Sells - Buys)
        buys = abs(df[df['type'].str.upper() == 'BUY']['amount'].sum())
        sells = df[df['type'].str.upper() == 'SELL']['amount'].sum()
        net_settlement = sells - buys
        
        # 6. Buying Power (Fixed Collateral 10824)
        base_collateral = 10824.0
        buying_power = net_tms_balance + base_collateral

    # ==========================================
    # TAB 1: FINANCIAL METRICS
    # ==========================================
    with tms_tabs[0]:
        if df.empty:
            st.info("No transactions logged yet.")
        else:
            # Main Summary Table (The "Whole Table" requested)
            st.subheader("💰 Cash Flow Summary")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Cash In", f"Rs {total_cash_in:,.2f}", help="Total money sent from Bank including gateway charges")
            col2.metric("Total Cash Out", f"Rs {total_cash_out:,.2f}", help="Total money received in Bank after charges")
            col3.metric("Net Cash in TMS", f"Rs {net_cash_in_tms:,.2f}", help="Your total principal currently in the broker system")
            
            st.divider()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Net TMS Balance", f"Rs {net_tms_balance:,.2f}", help="Actual withdrawable/usable cash in TMS")
            m2.metric("Net Settlement", f"Rs {net_settlement:,.2f}", delta=f"{'Profit/Credit' if net_settlement > 0 else 'Loss/Debit'}")
            m3.metric("Buying Power", f"Rs {buying_power:,.2f}", help="TMS Balance + 10,824 Free Collateral")

            # Liquidity Trend
            st.subheader("📈 Liquidity Trend")
            fig = px.area(df, x='date', y='running_balance', color_discrete_sequence=['#00CC96'])
            fig.update_layout(xaxis_title="Date", yaxis_title="Wallet Balance (Rs)")
            st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Universal Ledger")
        if not df.empty:
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Charges", format="Rs %.2f"),
                    "running_balance": st.column_config.NumberColumn("Net Balance", format="Rs %.2f"),
                    "status": st.column_config.SelectboxColumn("Status", options=["Settled", "Pending"]),
                },
                column_order=("date", "type", "stock", "amount", "charge", "running_balance", "status", "medium", "reference", "remark")
            )
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
            with st.form("tms_entry_v4", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    t_date = st.date_input("Date", value=date.today())
                    t_type = st.selectbox("Type", ["Buy", "Sell", "Deposit", "Withdrawal", "Charges", "Collateral Load"])
                    t_status = st.selectbox("Status", ["Settled", "Pending"])
                with c2:
                    t_stock = st.text_input("Symbol (Optional)").upper()
                    
                    # DYNAMIC MEDIUM SELECTION
                    selected_medium = st.selectbox("Payment Medium", medium_options + ["➕ Add New..."])
                    if selected_medium == "➕ Add New...":
                        t_medium = st.text_input("Enter New Medium Name")
                    else:
                        t_medium = selected_medium

                with c3:
                    raw_amount = st.number_input("Amount (Rs)", min_value=0.0)
                    # "Fee" is now "Charges"
                    t_charge = st.number_input("Charges (Bank/Gateway Fees)", min_value=0.0)

                r1, r2 = st.columns(2)
                t_ref = r1.text_input("Reference (Txn ID/Cheque)")
                t_remark = r2.text_input("Remarks")

                # AUTO-SIGN LOGIC
                if t_type in ["Withdrawal", "Buy", "Charges"]:
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
                                "d": t_date, "s": t_stock, "t": t_type, 
                                "m": t_medium, "a": final_amount, "c": t_charge, 
                                "r": t_remark, "st": t_status, "ref": t_ref
                            })
                            s.commit()
                        st.success(f"✅ Logged {t_type} with Rs {t_charge} extra charges.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

import streamlit as st
import pandas as pd
from sqlalchemy import text
import plotly.express as px
from datetime import date

def render_page(role):
    st.title("🏦 TMS Command Center")
    st.caption("Professional Broker Ledger & Cash Flow Reconciliation")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA LOADING
    try:
        df = conn.query("SELECT * FROM tms_trx ORDER BY date ASC", ttl=0)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"⚠️ Connection Error: {e}")
        df = pd.DataFrame()

    # --- DYNAMIC MEDIUM LOGIC (Moved outside the 'if not empty' so it always exists) ---
    existing_mediums = []
    if not df.empty and 'medium' in df.columns:
        existing_mediums = df['medium'].dropna().unique().tolist()
    
    defaults = ["Bank Transfer", "ConnectIPS", "Collateral", "Cheque"]
    medium_options = sorted(list(set(existing_mediums + defaults)))

    # --- TAB NAVIGATION ---
    tms_tabs = st.tabs(["📊 Financial Health", "📜 Universal Ledger", "✍️ Log Transaction"])

    # ==========================================
    # LOGIC: SHARED CALCULATIONS
    # ==========================================
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df['net_flow'] = df['amount'] - df['charge']
        df['running_balance'] = df['net_flow'].cumsum()
        
        display_df = df.sort_values(by="date", ascending=False)
        base_collateral = 10824.0
        
        cash_in = df[df['type'].str.upper() == 'DEPOSIT']['amount'].sum()
        cash_out = abs(df[df['type'].str.upper() == 'WITHDRAWAL']['amount'].sum())
        buys = abs(df[df['type'].str.upper() == 'BUY']['amount'].sum())
        sells = df[df['type'].str.upper() == 'SELL']['amount'].sum()
        net_settlement = sells - buys
        tms_cash = df['running_balance'].iloc[-1]
        buying_power = tms_cash + base_collateral

    # ==========================================
    # TAB 1: THE DASHBOARD
    # ==========================================
    with tms_tabs[0]:
        if df.empty:
            st.info("No transactions logged yet. Go to 'Log Transaction' to start.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Cash In", f"Rs {cash_in:,.0f}")
            m2.metric("Total Cash Out", f"Rs {cash_out:,.0f}")
            m3.metric("Net Settlement", f"Rs {net_settlement:,.2f}", 
                      delta=f"{'Creditor' if net_settlement > 0 else 'Debtor'}")
            m4.metric("Buying Power", f"Rs {buying_power:,.0f}")

            st.divider()
            c1, c2 = st.columns([1, 2])
            with c1:
                st.subheader("Current Wallet")
                st.title(f"Rs {tms_cash:,.2f}")
                pending_amt = df[df['status'].str.upper() == 'PENDING']['amount'].sum()
                if pending_amt != 0:
                    st.warning(f"⏳ T+2 Pending: Rs {pending_amt:,.2f}")
            with c2:
                fig = px.area(df, x='date', y='running_balance', title="Liquidity Trend")
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Broker Ledger")
        if not df.empty:
            f1, f2 = st.columns([1, 3])
            show_pending = f1.checkbox("Show Pending Only")
            
            final_display = display_df.copy()
            if show_pending:
                final_display = final_display[final_display['status'].str.upper() == 'PENDING']

            st.dataframe(
                final_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "reference": "Ref #",
                    "status": st.column_config.SelectboxColumn("Status", options=["Settled", "Pending"]),
                    "running_balance": st.column_config.NumberColumn("Running Balance", format="Rs %.2f"),
                },
                column_order=("date", "type", "stock", "amount", "reference", "running_balance", "status", "medium")
            )
        else:
            st.info("Ledger is empty.")

    # ==========================================
    # TAB 3: ADD TRANSACTIONS (FIXED INDENTATION)
    # ==========================================
    with tms_tabs[2]:
        if role == "View Only":
            st.warning("🔒 Admin access required.")
        else:
            st.subheader("✍️ Record Transaction")
            with st.form("tms_entry_v3", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    t_date = st.date_input("Date", value=date.today())
                    t_type = st.selectbox("Type", ["Buy", "Sell", "Deposit", "Withdrawal", "Fee", "Collateral Load"])
                    t_status = st.selectbox("Status", ["Settled", "Pending"])
                with c2:
                    t_stock = st.text_input("Stock Symbol").upper()
                    selected_medium = st.selectbox("Medium", medium_options + ["➕ Add New..."])
                    custom_medium = st.text_input("New Medium Name") if selected_medium == "➕ Add New..." else ""
                    t_medium = custom_medium if selected_medium == "➕ Add New..." else selected_medium
                with c3:
                    raw_amount = st.number_input("Amount", min_value=0.0)
                    t_charge = st.number_input("Fee", min_value=0.0)

                r1, r2 = st.columns(2)
                t_ref = r1.text_input("Reference Code")
                t_remark = r2.text_input("Remarks")

                if t_type in ["Withdrawal", "Buy", "Fee"]:
                    final_amount = -abs(raw_amount)
                else:
                    final_amount = abs(raw_amount)

                if st.form_submit_button("💾 Save Transaction", type="primary", use_container_width=True):
                    try:
                        with conn.session as s:
                            s.execute(text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark, status, reference) 
                                VALUES (:d, :s, :t, :m, :a, :c, :r, :st, :ref)
                            """), {"d": t_date, "s": t_stock, "t": t_type, "m": t_medium, "a": final_amount, "c": t_charge, "r": t_remark, "st": t_status, "ref": t_ref})
                            s.commit()
                        st.success("✅ Transaction Saved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

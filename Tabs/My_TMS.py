import streamlit as st
import pandas as pd
from sqlalchemy import text
import plotly.express as px
from datetime import date

def render_page(role):
    st.title("🏦 TMS Command Center")
    st.caption("Professional Broker Ledger & Cash Flow Reconciliation")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA LOADING & PRE-PROCESSING
    try:
        # We fetch all and sort by date ascending to calculate Running Balance correctly
        df = conn.query("SELECT * FROM tms_trx ORDER BY date ASC", ttl=0)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"⚠️ Connection Error: {e}")
        df = pd.DataFrame()

    # --- TAB NAVIGATION ---
    tms_tabs = st.tabs(["📊 Financial Health", "📜 Universal Ledger", "✍️ Log Transaction"])

    # ==========================================
    # LOGIC: SHARED CALCULATIONS
    # ==========================================
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        
        # Calculate Running Balance
        # Net Flow = Amount + Charge (since charges are usually negative fees)
        # Note: In your logic, we subtract charge from the flow.
        df['net_flow'] = df['amount'] - df['charge']
        df['running_balance'] = df['net_flow'].cumsum()
        
        # Sort back to DESC for display preference (newest first)
        display_df = df.sort_values(by="date", ascending=False)

        # Metrics Calculations
        base_collateral = 10824.0
        
        # Cash In: Only Deposits from Bank
        cash_in = df[df['type'].str.upper() == 'DEPOSIT']['amount'].sum()
        
        # Cash Out: Only Withdrawals to Bank
        cash_out = abs(df[df['type'].str.upper() == 'WITHDRAWAL']['amount'].sum())
        
        # Trading Settlement: Sells (Pos) - Buys (Neg)
        buys = abs(df[df['type'].str.upper() == 'BUY']['amount'].sum())
        sells = df[df['type'].str.upper() == 'SELL']['amount'].sum()
        net_settlement = sells - buys
        
        # TMS Cash Balance: The actual money in the wallet
        tms_cash = df['running_balance'].iloc[-1]
        
        # Buying Power
        buying_power = tms_cash + base_collateral

    # ==========================================
    # TAB 1: THE DASHBOARD
    # ==========================================
    with tms_tabs[0]:
        if df.empty:
            st.info("No transactions logged yet. Go to 'Log Transaction' to start.")
        else:
            # Row 1: The Big 4 Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Cash In (Bank)", f"Rs {cash_in:,.0f}")
            m2.metric("Total Cash Out (Bank)", f"Rs {cash_out:,.0f}")
            m3.metric("Net Trading Settlement", f"Rs {net_settlement:,.2f}", 
                      delta=f"{'Creditor' if net_settlement > 0 else 'Debtor'}")
            m4.metric("Buying Power", f"Rs {buying_power:,.0f}", help="Cash Balance + 10,824 Free Collateral")

            # Row 2: The Critical Cash Balance
            st.divider()
            c1, c2 = st.columns([1, 2])
            with c1:
                st.subheader("Current Wallet")
                st.title(f"Rs {tms_cash:,.2f}")
                st.caption("Actual Cash available in TMS (After all Buys/Sells/Fees)")
                
                # Settlement Alert
                pending_amt = df[df['status'].str.upper() == 'PENDING']['amount'].sum()
                if pending_amt != 0:
                    st.warning(f"⏳ T+2 Pending: Rs {pending_amt:,.2f}")

            with c2:
                # Visual: Running Balance over time
                fig = px.area(df, x='date', y='running_balance', 
                              title="Cash Liquidity Trend",
                              color_discrete_sequence=['#00CC96'])
                fig.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER (THE STAR)
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Comprehensive Broker Ledger")
        if not df.empty:
            # Filter UI
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
                    "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                    "type": "Action",
                    "stock": "Symbol",
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Txn Fee", format="Rs %.2f"),
                    "running_balance": st.column_config.NumberColumn("Running Balance", format="Rs %.2f"),
                    "status": st.column_config.SelectboxColumn("Status", options=["Settled", "Pending"]),
                    "medium": "Via",
                    "remark": "Notes"
                },
                column_order=("date", "type", "stock", "amount", "charge", "running_balance", "status", "medium", "remark")
            )
        else:
            st.info("Ledger is empty.")

    # ==========================================
    # TAB 3: ADD TRANSACTIONS
    # ==========================================
    with tms_tabs[2]:
        if role == "View Only":
            st.warning("🔒 Admin access required to log entries.")
        else:
            st.subheader("✍️ Record New Cash Movement")
            with st.form("tms_entry_v2", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    t_date = st.date_input("Date", value=date.today())
                    t_type = st.selectbox("Transaction Type", 
                                         ["Buy", "Sell", "Deposit", "Withdrawal", "Fee", "Collateral Load"])
                    t_status = st.selectbox("Settlement Status", ["Settled", "Pending"], 
                                           help="Sells are usually Pending for T+2 days")
                with c2:
                    t_stock = st.text_input("Stock Symbol (Optional)").upper()
                    t_medium = st.selectbox("Payment Medium", ["ConnectIPS", "Bank Transfer", "Collateral", "Cheque"])
                with c3:
                    raw_amount = st.number_input("Amount (Rs)", min_value=0.0, step=1.0)
                    t_charge = st.number_input("Transaction Fee (e.g. Rs 8)", min_value=0.0)

                t_remark = st.text_input("Entry Remarks (e.g. 'Sold for profit', 'Added margin')")

                # AUTO-SIGN LOGIC
                # Buy, Withdrawal, and Fee are cash OUTFLOWS (Negative)
                if t_type in ["Withdrawal", "Buy", "Fee"]:
                    final_amount = -abs(raw_amount)
                else:
                    final_amount = abs(raw_amount)

                if st.form_submit_button("💾 Commit to Ledger", type="primary", use_container_width=True):
                    try:
                        with conn.session as s:
                            # 1. Insert into Ledger
                            query = text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark, status) 
                                VALUES (:d, :s, :t, :m, :a, :c, :r, :st)
                            """)
                            s.execute(query, {
                                "d": t_date, "s": t_stock, "t": t_type, 
                                "m": t_medium, "a": final_amount, "c": t_charge, 
                                "r": t_remark, "st": t_status
                            })
                            
                            # 2. Audit Log
                            s.execute(text("INSERT INTO audit_log (action, details) VALUES (:act, :det)"), 
                                      {"act": f"TMS_{t_type.upper()}", "det": f"{t_type} Rs {final_amount} status {t_status}"})
                            s.commit()
                        st.success(f"✅ Logged {t_type} of Rs {final_amount} successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save: {e}")

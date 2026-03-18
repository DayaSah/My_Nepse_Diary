import streamlit as st
import pandas as pd
from sqlalchemy import text
import plotly.express as px

def render_page(role):
    st.title("🏦 TMS Command Center")
    st.caption("Central hub for Broker Ledger, Cash Flows, and T+2 Settlements")

    conn = st.connection("neon", type="sql")
    
    # 1. DATA LOADING
    try:
        trx_df = conn.query("SELECT * FROM tms_trx ORDER BY date DESC", ttl=0)
        trx_df.columns = [c.lower() for c in trx_df.columns]
    except Exception as e:
        st.error(f"⚠️ Table 'tms_trx' missing in Neon. Please run migration. Error: {e}")
        trx_df = pd.DataFrame()
        
    tms_tabs = st.tabs(["📊 Dashboard", "✍️ Add Transactions", "📜 View Ledger"])
    
    # ==========================================
    # TAB 1: THE DASHBOARD
    # ==========================================
    with tms_tabs[0]:
        if not trx_df.empty:
            trx_df["date"] = pd.to_datetime(trx_df["date"])
            
            # Calculations
            is_collateral = (trx_df["medium"].str.upper() == "COLLATERAL") | \
                            (trx_df["type"].str.upper() == "COLLATERAL LOAD")
            
            real_cash = trx_df[~is_collateral]
            cash_in = float(real_cash[real_cash["amount"] > 0]["amount"].sum())
            cash_out = abs(float(real_cash[real_cash["amount"] < 0]["amount"].sum()))
            total_charges = float(trx_df["charge"].sum())
            net_balance = (cash_in - cash_out) - total_charges
            
            # Buying Power (Note: Consider moving '10824' to a sidebar setting)
            base_collateral = 10824.0 
            loaded_collateral = float(trx_df[trx_df["type"].str.upper() == "COLLATERAL LOAD"]["amount"].sum())
            total_collateral = base_collateral + loaded_collateral
            buying_power = total_collateral + net_balance

            # UI Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Cash In", f"Rs {cash_in:,.0f}")
            m2.metric("Cash Out", f"Rs {cash_out:,.0f}", delta_color="inverse")
            m3.metric("Net Cash", f"Rs {net_balance:,.0f}")
            m4.metric("Buying Power", f"Rs {buying_power:,.0f}", help="Available limit for tomorrow's trade")

            st.divider()

            # Visual: Cash Flow Trend
            st.subheader("📈 Cash Flow Trend")
            daily_flow = real_cash.groupby('date')['amount'].sum().reset_index()
            fig = px.bar(daily_flow, x='date', y='amount', 
                         color='amount', color_continuous_scale='RdYlGn',
                         title="Daily Net Cash Movement")
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.info("No data available to display dashboard.")

    # ==========================================
    # TAB 2: ADD TRANSACTIONS (IMPROVED UX)
    # ==========================================
    with tms_tabs[1]:
        st.subheader("✍️ Log a New Transaction")
        
        if role == "View Only":
            st.warning("🔒 Access Denied: Admin role required to log transactions.")
        else:
            with st.form("tms_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    t_date = st.date_input("Transaction Date")
                    t_type = st.selectbox("Type", ["Deposit", "Withdrawal", "Buy", "Sell", "Collateral Load", "Fee"])
                    t_stock = st.text_input("Symbol (If applicable)").upper()
                with c2:
                    t_medium = st.selectbox("Medium", ["Bank Transfer", "ConnectIPS", "Collateral", "Cheque"])
                    raw_amount = st.number_input("Amount (Rs)", min_value=0.0, step=100.0)
                    t_charge = st.number_input("Broker/Bank Fee", min_value=0.0)
                
                t_remark = st.text_input("Remarks")
                
                # AUTO-LOGIC: Handle signs automatically
                # Buy, Withdrawal, and Fee should be negative flows
                if t_type in ["Withdrawal", "Buy", "Fee"]:
                    final_amount = -abs(raw_amount)
                else:
                    final_amount = abs(raw_amount)

                if st.form_submit_button("💾 Save Transaction", type="primary"):
                    try:
                        with conn.session as s:
                            # 1. Insert into Ledger
                            s.execute(text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark) 
                                VALUES (:d, :s, :t, :m, :a, :c, :r)
                            """), {"d":t_date, "s":t_stock, "t":t_type, "m":t_medium, "a":final_amount, "c":t_charge, "r":t_remark})
                            
                            # 2. Insert into Audit Log
                            s.execute(text("INSERT INTO audit_log (action, details) VALUES (:act, :det)"), 
                                      {"act": f"TMS_{t_type.upper()}", "det": f"{t_stock} {t_type} Rs {final_amount}"})
                            s.commit()
                        st.success(f"Registered {t_type} of Rs {final_amount}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ==========================================
    # TAB 3: VIEW LEDGER (BETTER FORMATTING)
    # ==========================================
    with tms_tabs[2]:
        st.subheader("📜 Broker Ledger")
        if not trx_df.empty:
            # Using column_config to make it look professional
            st.dataframe(
                trx_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Fee", format="Rs %.2f"),
                    "date": st.column_config.DateColumn("Date"),
                    "type": "Action",
                    "medium": "Payment Via"
                }
            )
        else:
            st.info("Ledger is empty.")

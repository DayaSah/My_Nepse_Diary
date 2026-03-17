import streamlit as st
import pandas as pd
from sqlalchemy import text

def render_page(role):
    st.title("🏦 TMS Command Center")
    st.caption("Central hub for Broker Ledger, Cash Flows, and T+2 Settlements")

    # Initialize the Neon database connection
    conn = st.connection("neon", type="sql")
    
    # Try loading the tms_trx table
    try:
        # Standardizing all columns to lowercase for Postgres compatibility
        trx_df = conn.query("SELECT * FROM tms_trx ORDER BY date DESC")
        trx_df.columns = [c.lower() for c in trx_df.columns]
    except Exception as e:
        st.error(f"Database error: Please ensure the 'tms_trx' table is created in Neon. {e}")
        trx_df = pd.DataFrame()
        
    # Creating the Nested Tabs
    tms_tabs = st.tabs([
        "📊 Dashboard", 
        "✍️ Add Transactions", 
        "📜 View Ledger"
    ])
    
    # ==========================================
    # TAB 1: THE DASHBOARD
    # ==========================================
    with tms_tabs[0]:
        st.subheader("💸 TMS Cash Flow & Solvency")
        
        if not trx_df.empty:
            trx_df["date"] = pd.to_datetime(trx_df["date"])
            
            # --- CORE FINANCIAL CALCULATIONS ---
            # Exclude Collateral movements from real cash flow
            is_collateral_entry = (trx_df["medium"].astype(str).str.upper() == "COLLATERAL") | \
                                  (trx_df["type"].astype(str).str.upper() == "COLLATERAL LOAD")
            
            real_cash_df = trx_df[~is_collateral_entry]
            
            # Real Cash In: Deposits + Sales (Positive amounts)
            cash_in = float(real_cash_df[real_cash_df["amount"] > 0]["amount"].sum())
            
            # Real Cash Out: Withdraws + Buys + Fines (Convert negative to positive for display)
            cash_out = abs(float(real_cash_df[real_cash_df["amount"] < 0]["amount"].sum()))
            
            total_charges = float(trx_df["charge"].sum()) if "charge" in trx_df.columns else 0.0
            
            # Net Balance Calculation
            net_balance = (cash_in - cash_out) - total_charges
            
            # Buying Power Logic
            base_free_collateral = 10824.0 # Hardcoded base from your previous logic
            loaded_collateral = float(trx_df[trx_df["type"].astype(str).str.upper() == "COLLATERAL LOAD"]["amount"].sum())
            total_collateral = base_free_collateral + loaded_collateral
            
            # Final Buying Power
            buying_power = total_collateral + net_balance
            
            # --- UI: MAIN METRICS ---
            st.markdown("### Account Balances")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cash In (Deposits/Sales)", f"Rs {cash_in:,.2f}")
            c2.metric("Cash Out (Buys/Withdraws)", f"Rs {cash_out:,.2f}")
            c3.metric("Net Balance", f"Rs {net_balance:,.2f}", help="Cash In - Cash Out - Fees")
            c4.metric("Buying Power", f"Rs {buying_power:,.2f}", help="(Collateral + Net Balance)")
            
            st.divider()
            st.markdown("### Collateral & Fees")
            col1, col2 = st.columns(2)
            col1.metric("Total Active Collateral", f"Rs {total_collateral:,.2f}", help="Base + Loaded Collateral")
            col2.metric("Total TMS Charges & Fines", f"Rs {total_charges:,.2f}")
            
        else:
            st.info("No TMS transactions found. Go to 'Add Transactions' to record your first ledger entry.")

    # ==========================================
    # TAB 2: ADD TRANSACTIONS
    # ==========================================
    with tms_tabs[1]:
        st.subheader("✍️ Log a New Transaction")
        
        if role == "View Only":
            st.warning("🔒 You are in View Only mode. You cannot add transactions.")
        else:
            with st.form("add_trx_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    t_date = st.date_input("Transaction Date")
                    t_stock = st.text_input("Stock Symbol (Optional)")
                    t_type = st.selectbox("Transaction Type", ["Deposit", "Withdrawal", "Buy", "Sell", "Collateral Load", "Fee"])
                    
                with col2:
                    t_medium = st.selectbox("Medium", ["Bank Transfer", "ConnectIPS", "Collateral", "Cheque", "Other"])
                    t_amount = st.number_input("Amount (Rs)", help="Use negative (-) for Cash Out (Buys/Withdrawals). Positive for Cash In.")
                    t_charge = st.number_input("Broker/Bank Charge (Rs)", min_value=0.0)
                    
                t_remark = st.text_input("Remark / Description")
                t_ref = st.text_input("Reference ID")
                
                submitted = st.form_submit_button("💾 Save to Ledger", type="primary")
                
                if submitted:
                    try:
                        with conn.session as s:
                            sql = text("""
                                INSERT INTO tms_trx (date, stock, type, medium, amount, charge, remark, reference) 
                                VALUES (:date, :stock, :type, :medium, :amount, :charge, :remark, :reference)
                            """)
                            s.execute(sql, {
                                "date": t_date,
                                "stock": t_stock.upper(),
                                "type": t_type,
                                "medium": t_medium,
                                "amount": t_amount,
                                "charge": t_charge,
                                "remark": t_remark,
                                "reference": t_ref
                            })
                          
                            audit_sql = text("INSERT INTO audit_log (action, symbol, details) VALUES (:act, :sym, :det)")
                            s.execute(audit_sql, {
                                "act": f"TMS_{t_type.upper().replace(' ', '_')}",
                                "sym": t_stock.upper() if t_stock else "-",
                                "det": f"{t_type} of Rs {t_amount} via {t_medium}"
                            })
                            
                            s.commit()
                        st.success("✅ Transaction saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error saving transaction: {e}")

    # ==========================================
    # TAB 3: VIEW LEDGER
    # ==========================================
    with tms_tabs[2]:
        st.subheader("📜 Full Transaction Ledger")
        if not trx_df.empty:
            st.dataframe(trx_df, use_container_width=True, hide_index=True)
        else:
            st.info("Ledger is empty.")

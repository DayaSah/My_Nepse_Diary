import streamlit as st
import pandas as pd
from sqlalchemy import text

# ==========================================
# 1. THE IMPACT ANALYSIS ENGINE
# ==========================================
def analyze_impact(table_name, editor_state):
    """Analyzes the Streamlit data_editor state and returns specific system warnings."""
    warnings = []
    
    deleted = editor_state.get("deleted_rows", [])
    edited = editor_state.get("edited_rows", {})
    added = editor_state.get("added_rows", [])

    # --- Deletion Warnings ---
    if deleted:
        warnings.append(f"🚨 **CRITICAL:** You are permanently deleting {len(deleted)} row(s). This cannot be undone.")
        if table_name == 'portfolio':
            warnings.append("⚠️ **Portfolio Impact:** Deleting a trade will permanently alter your WACC, Net Quantity, and all 'Trade Simulation' math.")
        elif table_name == 'tms_trx':
            warnings.append("⚠️ **TMS Impact:** Deleting a collateral/cash record will immediately change your Buying Power on the Dashboard.")
        elif table_name == 'wealth':
            warnings.append("⚠️ **Wealth Impact:** Deleting a snapshot will create a gap in your Wealth Trajectory and Drawdown graphs.")

    # --- Addition Warnings ---
    if added:
        warnings.append(f"➕ You are manually inserting {len(added)} new row(s).")
        if table_name == 'portfolio':
            warnings.append("⚠️ **Data Integrity:** Manually adding a trade bypasses the NEPSE fee calculators. Ensure your 'price' includes all broker/SEBON commissions.")
            
    # --- Edit Warnings ---
    if edited:
        warnings.append(f"✏️ You are modifying data in {len(edited)} existing row(s).")
        if table_name == 'portfolio':
            warnings.append("⚠️ **Math Warning:** Changing 'qty' or 'price' will shift your historical cost basis. Changing 'transaction_type' (Buy to Sell) could cause negative unit counts.")
        elif table_name == 'audit_log':
            warnings.append("🕵️ **Audit Warning:** You are tampering with the system log. The Activity Timeline will reflect these fake/altered timestamps.")

    return warnings

# ==========================================
# 2. MAIN PAGE ROUTER
# ==========================================
def render_page(role):
    # Security Check
    if role != "Admin":
        st.error("🛑 ACCESS DENIED: This module is restricted to Administrators only.")
        st.image("https://http.cat/403", width=400) # A little developer humor for unauthorized access
        return

    st.title("⚙️ Database Management (Admin)")
    st.caption("Direct read/write access to the Neon PostgreSQL database.")

    conn = st.connection("neon", type="sql")

    # Fetch list of user tables (excluding postgres system tables)
    try:
        tables_df = conn.query("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        available_tables = tables_df['table_name'].tolist()
    except Exception as e:
        st.error(f"Failed to fetch schema: {e}")
        return

    tabs = st.tabs(["🗃️ Visual Data Editor", "💻 Raw SQL Console"])

    # ==========================================
    # TAB 1: VISUAL DATA EDITOR
    # ==========================================
    with tabs[0]:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            sel_table = st.selectbox("Select Table to Manage", available_tables)
            st.info(f"Currently viewing: **{sel_table}**")

        # Load the selected table
        try:
            df = conn.query(f"SELECT * FROM {sel_table} ORDER BY 1 ASC") # Assumes first col is ID or Date
        except Exception as e:
            st.error(f"Failed to load table {sel_table}: {e}")
            df = pd.DataFrame()

        if not df.empty:
            st.markdown("### Editor Workspace")
            
            # Using Session State to track changes for the Impact Engine
            editor_key = f"editor_{sel_table}"
            
            # The actual interactive editor
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key=editor_key,
                height=400
            )

            # Check the session state for changes
            current_state = st.session_state[editor_key]
            has_changes = any([current_state["edited_rows"], current_state["added_rows"], current_state["deleted_rows"]])

            if has_changes:
                st.divider()
                st.markdown("### ⚠️ Impact Analysis Report")
                
                # Run the Impact Engine
                warnings = analyze_impact(sel_table, current_state)
                for w in warnings:
                    if "CRITICAL" in w or "🚨" in w:
                        st.error(w)
                    else:
                        st.warning(w)

                # Save Mechanism (Overwrites table safely using pandas to_sql for simplicity in this admin tool)
                # Note: In an enterprise app, we would write row-by-row SQL updates. For a personal terminal, 
                # replacing the table with the edited dataframe is the cleanest way to handle dynamic adds/edits/deletes via Streamlit.
                st.markdown("---")
                if st.button(f"🔥 I understand the risks. Commit Changes to {sel_table}", type="primary"):
                    try:
                        # Get the underlying SQLAlchemy engine
                        engine = conn.engine
                        # Write the entirely new dataframe back to the DB. 
                        # if_exists='replace' drops the table and recreates it.
                        edited_df.to_sql(sel_table, engine, if_exists='replace', index=False)
                        
                        # Log the admin action
                        with engine.begin() as sql_conn:
                            sql = text("INSERT INTO audit_log (action, symbol, details) VALUES (:act, :sym, :det)")
                            sql_conn.execute(sql, {"act": "ADMIN_OVERRIDE", "sym": sel_table, "det": f"Admin manually edited {sel_table} via Visual Editor"})
                            
                        st.success(f"✅ Successfully committed changes to `{sel_table}`!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Database Write Error: {e}")
                        st.caption("Hint: Replacing tables might fail if there are complex foreign key constraints.")
        else:
            st.warning("Table is empty.")

    # ==========================================
    # TAB 2: RAW SQL CONSOLE ("GOD MODE")
    # ==========================================
    with tabs[1]:
        st.subheader("Raw SQL Console")
        st.caption("Execute direct SQL queries. USE WITH EXTREME CAUTION. There are no warnings here.")

        query = st.text_area("Enter SQL Command", height=150, placeholder="e.g., DELETE FROM portfolio WHERE symbol = 'NABIL';")
        
        c1, c2 = st.columns([1, 4])
        is_select = query.strip().upper().startswith("SELECT")
        
        if c1.button("▶️ Execute Query", type="primary"):
            if not query.strip():
                st.warning("Query cannot be empty.")
            else:
                try:
                    engine = conn.engine
                    with engine.begin() as sql_conn:
                        result = sql_conn.execute(text(query))
                        
                        if is_select:
                            # Fetch and display results for SELECT queries
                            fetched_data = result.fetchall()
                            if fetched_data:
                                res_df = pd.DataFrame(fetched_data, columns=result.keys())
                                st.success(f"Query executed successfully. Returned {len(res_df)} rows.")
                                st.dataframe(res_df, use_container_width=True)
                            else:
                                st.info("Query executed successfully but returned 0 rows.")
                        else:
                            # For UPDATE, DELETE, INSERT
                            st.success(f"Command executed successfully! Affected rows: {result.rowcount}")
                            
                            # Log the raw query execution
                            log_sql = text("INSERT INTO audit_log (action, symbol, details) VALUES (:act, :sym, :det)")
                            sql_conn.execute(log_sql, {"act": "RAW_SQL_EXEC", "sym": "-", "det": f"Executed: {query[:50]}..."})

                except Exception as e:
                    st.error(f"❌ SQL Execution Failed: {e}")

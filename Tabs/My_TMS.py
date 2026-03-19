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

    # --- HARDCODED MEDIUM OPTIONS ---
    medium_options = [
        "ConnectIPS", 
        "Collateral", 
        "NABIL Bank", 
        "GLOBAL IME Bank", 
        "SIDDHARTHA Bank", 
        "NIMB Bank", 
        "Nic Asia Bank", 
        "Khalti", 
        "Esewa", 
        "Other Specified In Remark"
    ]

    # --- TAB NAVIGATION ---
    tms_tabs = st.tabs([
        "📊 Financial Metrics", 
        "📜 Universal Ledger", 
        "✍️ Log Transaction",
        "📈 Smart Graphs",     # NEW
        "💾 Export Data",      # NEW
        "⚙️ Manage Data"       # NEW
    ])

    # ==========================================
    # LOGIC: SHARED CALCULATIONS
    # ==========================================
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        
        # 1. Sorting by date for accurate running balance
        df = df.sort_values(by="date", ascending=True)
        df['running_balance'] = df['amount'].cumsum()
        
        # 2. Display version (Newest first) - reset_index ensures correct selection
        display_df = df.sort_values(by="date", ascending=False).reset_index(drop=True)

        # 3. Total Cash In: Sum of (Principal + Charge) for Deposits
        deposits = df[df['type'].str.upper() == 'DEPOSIT']
        total_cash_in = (deposits['amount'] + deposits['charge']).sum()
        
        # 4. Total Cash Out: Sum of (Abs(Principal) - Charge) for Withdrawals
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

            # --- T+2 Pending Alert ---
            if 'status' in df.columns:
                pending_amt = df[df['status'].str.upper() == 'PENDING']['amount'].sum()
                if pending_amt != 0:
                    st.warning(f"⏳ T+2 Settlement Pending: **Rs {pending_amt:,.2f}**")

            st.subheader("📈 Wallet Balance Trend")
            fig = px.area(df, x='date', y='running_balance', color_discrete_sequence=['#00CC96'])
            fig.update_layout(xaxis_title="Date", yaxis_title="Balance (Rs)")
            st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # TAB 2: UNIVERSAL LEDGER
    # ==========================================
    with tms_tabs[1]:
        st.subheader("📜 Universal Ledger")
        if not df.empty:
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "id": None, # Hide ID from user
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount", format="Rs %.2f"),
                    "charge": st.column_config.NumberColumn("Charges", format="Rs %.2f"),
                    "running_balance": st.column_config.NumberColumn("Net Balance", format="Rs %.2f"),
                },
                column_order=("date", "type", "stock", "amount", "charge", "running_balance", "status", "medium", "reference", "remark")
            )

            # DELETE LOGIC
            if hasattr(event, 'selection') and event.selection.rows:
                selected_index = event.selection.rows[0]
                row_to_delete = display_df.iloc[selected_index]
                
                st.divider()
                st.warning(f"⚠️ Delete '{row_to_delete['type']}' entry of Rs {row_to_delete['amount']} logged on {row_to_delete['date'].date()}?")
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
            
            # Moved OUTSIDE the form so it triggers the dynamic default below instantly
            t_type = st.radio("Transaction Type", ["Deposit", "Withdrawal", "Buy", "Sell", "Charges", "Collateral Load"], horizontal=True)
            
            with st.form("tms_entry_v7", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    t_date = st.date_input("Date", value=date.today())
                    t_status = st.selectbox("Status", ["Settled", "Pending"])
                
                with c2:
                    t_stock = st.text_input("Symbol (Optional)").upper()
                    
                    # --- DYNAMIC DEFAULT LOGIC ---
                    if t_type == "Withdrawal":
                        default_index = medium_options.index("NABIL Bank")
                    elif t_type in ["Buy", "Sell", "Collateral Load"]:
                        default_index = medium_options.index("Collateral")
                    else:
                        default_index = medium_options.index("ConnectIPS")
                        
                    t_medium = st.selectbox("Payment Medium", medium_options, index=default_index)
                
                with c3:
                    raw_amount = st.number_input("Principal Amount (Rs)", min_value=0.0)
                    t_charge = st.number_input("Charges (Bank/Gateway/DP)", min_value=0.0)

                t_ref = st.text_input("Reference (Txn ID/Cheque)")
                t_remark = st.text_input("Remarks")

                # --- THE SMART MATH LOGIC ---
                if t_type == "Deposit":
                    final_amount = raw_amount
                elif t_type == "Buy":
                    final_amount = -(raw_amount + t_charge)
                elif t_type == "Sell":
                    final_amount = (raw_amount - t_charge)
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

    # ==========================================
    # TAB 4: SMART GRAPHS
    # ==========================================
    with tms_tabs[3]:
        st.subheader("📈 Smart Financial Visuals")
        if df.empty:
            st.info("Not enough data to generate graphs.")
        else:
            # --- DATE FILTER ---
            st.markdown("##### 📅 Filter Timeframe")
            
            filter_col1, filter_col2 = st.columns([1, 2])
            with filter_col1:
                date_filter = st.selectbox("Select Range", 
                    ["Last 7 Days", "Last 15 Days", "Last 1 Month", "Last 2 Months", "Last 3 Months", "Last 6 Months", "Last 1 Year", "All Time", "Custom Range"], 
                    index=7, label_visibility="collapsed")
            
            today_ts = pd.Timestamp.today().normalize()
            start_date = None
            end_date = today_ts

            with filter_col2:
                if date_filter == "Custom Range":
                    date_range = st.date_input("Select Dates", value=(today_ts.date() - pd.Timedelta(days=30), today_ts.date()), label_visibility="collapsed")
                    if len(date_range) == 2:
                        start_date = pd.to_datetime(date_range[0])
                        end_date = pd.to_datetime(date_range[1])
                    else:
                        start_date = pd.to_datetime(date_range[0])
                        end_date = start_date
                elif date_filter == "Last 7 Days":
                    start_date = today_ts - pd.Timedelta(days=7)
                elif date_filter == "Last 15 Days":
                    start_date = today_ts - pd.Timedelta(days=15)
                elif date_filter == "Last 1 Month":
                    start_date = today_ts - pd.DateOffset(months=1)
                elif date_filter == "Last 2 Months":
                    start_date = today_ts - pd.DateOffset(months=2)
                elif date_filter == "Last 3 Months":
                    start_date = today_ts - pd.DateOffset(months=3)
                elif date_filter == "Last 6 Months":
                    start_date = today_ts - pd.DateOffset(months=6)
                elif date_filter == "Last 1 Year":
                    start_date = today_ts - pd.DateOffset(years=1)
            
            # Apply Filter
            if start_date is not None:
                mask = (df['date'] >= start_date) & (df['date'] <= end_date + pd.Timedelta(days=1)) # +1 to include the end date fully
                graph_df = df.loc[mask].copy()
            else:
                graph_df = df.copy()

            if graph_df.empty:
                st.warning("No data found for the selected date range.")
            else:
                st.markdown("##### 💓 The Pulse: Cumulative Net Balance")
                fig_pulse = px.line(graph_df, x='date', y='running_balance', markers=True, 
                                    color_discrete_sequence=['#00CC96'])
                fig_pulse.update_layout(xaxis_title="Date", yaxis_title="Net Balance (Rs)")
                st.plotly_chart(fig_pulse, use_container_width=True)

                st.markdown("##### 📊 Cash Flow Trends (Cumulative vs Daily)")
                # Base daily aggregation from the FILTERED dataframe
                daily_df = graph_df.groupby('date').agg({'amount': 'sum', 'charge': 'sum'}).reset_index()
                
                # Calculate series indexed by date
                dep_series = graph_df[graph_df['type'].str.upper() == 'DEPOSIT'].groupby('date')['amount'].sum()
                with_series = graph_df[graph_df['type'].str.upper() == 'WITHDRAWAL'].groupby('date')['amount'].sum().abs()
                
                # Map the values properly to avoid index mismatch
                daily_df['Cash In (Daily)'] = daily_df['date'].map(dep_series).fillna(0)
                daily_df['Cash Out (Daily)'] = daily_df['date'].map(with_series).fillna(0)
                
                # --- CUMULATIVE SUM LOGIC (Always going forward) ---
                daily_df['Cash In (Cumulative)'] = daily_df['Cash In (Daily)'].cumsum()
                daily_df['Cash Out (Cumulative)'] = daily_df['Cash Out (Daily)'].cumsum()
                daily_df['Charges (Cumulative)'] = daily_df['charge'].cumsum()

                # 'amount' remains daily net, the others are cumulative
                fig_trends = px.line(daily_df, x='date', 
                                     y=['amount', 'Cash In (Cumulative)', 'Cash Out (Cumulative)', 'Charges (Cumulative)'],
                                     labels={'value': 'Amount (Rs)', 'variable': 'Metric'})
                st.plotly_chart(fig_trends, use_container_width=True)

                st.markdown("##### 🔄 Portfolio Composition")
                c1, c2 = st.columns([1, 3])
                with c1:
                    pie_category = st.selectbox("Group By:", ["medium", "type", "status", "stock"])
                with c2:
                    pie_df = graph_df.dropna(subset=[pie_category]).copy()
                    pie_df['abs_amount'] = pie_df['amount'].abs()
                    if not pie_df.empty and pie_df['abs_amount'].sum() > 0:
                        fig_pie = px.pie(pie_df, names=pie_category, values='abs_amount', hole=0.4)
                        st.plotly_chart(fig_pie, use_container_width=True)
                    else:
                        st.info(f"No valid data available to group by {pie_category}.")

                st.markdown("##### 💸 Cost of Trading (Fines & Charges)")
                # Applying cumsum to charges specifically for this graph as well
                cumulative_charges = graph_df[['date', 'charge']].copy()
                cumulative_charges['Cumulative Charges'] = cumulative_charges['charge'].cumsum()
                fig_charges = px.line(cumulative_charges, x='date', y='Cumulative Charges', markers=True,
                                      color_discrete_sequence=['#EF553B'])
                st.plotly_chart(fig_charges, use_container_width=True)

    # ==========================================
    # TAB 5: EXPORT DATA (FIXED)
    # ==========================================
    with tms_tabs[4]:
        st.subheader("💾 Export Ledger Data")
        if df.empty:
            st.info("No data available to export.")
        else:
            st.markdown("Filter your data before exporting:")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                start_date = st.date_input("Start Date", value=df['date'].min())
                end_date = st.date_input("End Date", value=df['date'].max())
            with col2:
                types_to_export = st.multiselect("Filter by Type", df['type'].unique(), default=df['type'].unique())
            with col3:
                # FIX: Using medium_options instead of existing_mediums
                mediums_to_export = st.multiselect("Filter by Medium", medium_options, default=medium_options)

            mask = (
                (df['date'].dt.date >= start_date) & 
                (df['date'].dt.date <= end_date) &
                (df['type'].isin(types_to_export)) &
                (df['medium'].isin(mediums_to_export) | df['medium'].isna())
            )
                
            filtered_export_df = df.loc[mask].drop(columns=['id', 'running_balance'], errors='ignore')
            st.dataframe(filtered_export_df, use_container_width=True, hide_index=True)

            csv = filtered_export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv,
                file_name=f"tms_export_{date.today()}.csv",
                mime="text/csv",
                type="primary"
            )

    # ==========================================
    # TAB 6: MANAGE DATA (SAFE DELETE OVERHAUL)
    # ==========================================
    with tms_tabs[5]:
        if role == "View Only":
            st.warning("🔒 Admin access required to manage database.")
        else:
            st.subheader("⚙️ Database Management")
            
            if df.empty:
                st.info("Database is empty.")
            else:
                st.caption("Raw Database View (Includes ID numbers)")
                # Show raw dataframe WITH IDs so the admin knows what to delete
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                st.divider()
                st.markdown("#### 🗑️ Delete Specific Record")
                st.info("Identify the 'id' from the table above and enter it below to permanently delete that record.")
                
                del_col1, del_col2 = st.columns([1, 2])
                with del_col1:
                    delete_id = st.number_input("Enter Record ID", min_value=1, step=1, value=1)
                with del_col2:
                    st.write("") # Spacing
                    st.write("") # Spacing
                    if st.button("Permanently Delete Record", type="primary"):
                        try:
                            with conn.session as s:
                                s.execute(text("DELETE FROM tms_trx WHERE id = :id"), {"id": delete_id})
                                s.commit()
                            st.success(f"✅ Record #{delete_id} deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

                st.divider()
                st.markdown("#### 🚨 Danger Zone")
                with st.expander("Wipe Entire Ledger"):
                    st.error("This action cannot be undone. It will delete ALL transaction history.")
                    delete_confirm = st.text_input("Type 'DELETE ALL' to confirm:")
                    if st.button("Wipe Database", type="primary", use_container_width=True):
                        if delete_confirm == "DELETE ALL":
                            try:
                                with conn.session as s:
                                    s.execute(text("TRUNCATE TABLE tms_trx RESTART IDENTITY"))
                                    s.commit()
                                st.success("Database completely wiped. Starting fresh.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Confirmation text did not match.")
                        st.warning("Confirmation text did not match.")

import streamlit as st
import pandas as pd
from sqlalchemy import text
import plotly.express as px
from datetime import datetime, timedelta, timezone

def render_page(role):
    st.title("🗂️ Master Activity Log")
    st.caption("A chronological, tamper-proof trail of every action taken in your terminal.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 1. FETCH AND PROCESS DATA
    # ==========================================
    try:
        # IMPROVEMENT 1: Added ttl=0 for live data and LIMIT 2000 to prevent future memory crashes
        log_df = conn.query("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 2000", ttl=0)
        log_df.columns = [c.lower() for c in log_df.columns]
    except Exception as e:
        st.error(f"⚠️ Failed to load Activity Log: {e}")
        log_df = pd.DataFrame()

    if log_df.empty:
        st.info("No activity recorded yet.")
        return

    # --- Timezone Conversion (UTC to Nepal Time UTC+5:45) ---
    log_df['timestamp'] = pd.to_datetime(log_df['timestamp'])
    
    # IMPROVEMENT 2: Safely assign UTC and convert to Nepal Time without crashing
    if log_df['timestamp'].dt.tz is None:
        log_df['timestamp'] = log_df['timestamp'].dt.tz_localize('UTC')
        
    log_df['nepal_time'] = log_df['timestamp'].dt.tz_convert('Asia/Kathmandu')

    # Format it to look like "2026-03-17 02:30 PM"
    log_df['display_time'] = log_df['nepal_time'].dt.strftime('%Y-%m-%d %I:%M %p')
    log_df['date_only'] = log_df['nepal_time'].dt.date

    # Fill empty symbols with dashes for cleaner UI
    log_df['symbol'] = log_df['symbol'].fillna('-')

    # ==========================================
    # 2. UI FILTERS & SEARCH
    # ==========================================
    st.markdown("### 🔍 Filter & Search")
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        # Extract unique base categories (e.g., 'TRADE_BUY' -> 'TRADE')
        log_df['category'] = log_df['action'].apply(lambda x: str(x).split('_')[0] if '_' in str(x) else str(x))
        categories = ["All"] + list(log_df['category'].unique())
        sel_category = st.selectbox("Filter by Category", categories)

    with col2:
        actions = ["All"] + list(log_df['action'].unique())
        sel_action = st.selectbox("Filter by Specific Action", actions)
        
    with col3:
        search_query = st.text_input("Search Symbol or Details...", placeholder="e.g. NABIL, 500 units, Error...")

    # --- Apply Filters ---
    filtered_df = log_df.copy()
    
    if sel_category != "All":
        filtered_df = filtered_df[filtered_df['category'] == sel_category]
    if sel_action != "All":
        filtered_df = filtered_df[filtered_df['action'] == sel_action]
    if search_query:
        # Case insensitive search across symbol and details
        mask = filtered_df['symbol'].str.contains(search_query, case=False, na=False) | \
               filtered_df['details'].str.contains(search_query, case=False, na=False)
        filtered_df = filtered_df[mask]

    st.divider()

    # ==========================================
    # 3. ACTIVITY DASHBOARD & EXPORT
    # ==========================================
    c1, c2, c3 = st.columns([2, 2, 1])
    
    c1.metric("Total Events Displayed", len(filtered_df))
    
    # Calculate events today (in precise Nepal Time)
    np_tz = timezone(timedelta(hours=5, minutes=45))
    today_nepal = datetime.now(np_tz).date()
    events_today = len(filtered_df[filtered_df['date_only'] == today_nepal])
    
    # Added a nice visual delta indicator for today's activity
    c2.metric("Events Today", events_today, delta="Active Today" if events_today > 0 else None, delta_color="normal")

    with c3:
        # Pro Feature: CSV Downloader
        st.write("") # Spacing
        csv = filtered_df[['display_time', 'action', 'symbol', 'details']].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Export Log to CSV",
            data=csv,
            file_name=f"nepse_activity_log_{today_nepal}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # ==========================================
    # 4. DATA VISUALIZATION & TABLE
    # ==========================================
    tab_table, tab_chart = st.tabs(["📜 Log Ledger", "📊 Activity Timeline"])

    with tab_table:
        display_cols = filtered_df[['display_time', 'action', 'symbol', 'details']].copy()
        
        # IMPROVEMENT 3: Advanced Streamlit Column Configuration for a polished look
        st.dataframe(
            display_cols,
            use_container_width=True,
            hide_index=True,
            height=600,
            column_config={
                "display_time": st.column_config.TextColumn("🕒 Timestamp (NST)", width="medium"),
                "action": st.column_config.TextColumn("⚡ Event Action", width="small"),
                "symbol": st.column_config.TextColumn("🏷️ Symbol", width="small"),
                "details": st.column_config.TextColumn("📝 Transaction Details", width="large")
            }
        )

    with tab_chart:
        st.markdown("#### System Activity Over Time")
        if not filtered_df.empty:
            # Group by date and category to make a stacked bar chart
            chart_df = filtered_df.groupby(['date_only', 'category']).size().reset_index(name='count')
            
            # IMPROVEMENT 4: Enhanced Plotly Aesthetics
            fig = px.bar(
                chart_df, 
                x='date_only', 
                y='count', 
                color='category',
                title="Events per Day by Category",
                labels={'date_only': 'Date', 'count': 'Number of Events', 'category': 'Event Type'},
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            
            # Make the chart look cleaner by removing the background grid
            fig.update_layout(
                xaxis_tickangle=-45,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified"
            )
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data to generate a chart.")

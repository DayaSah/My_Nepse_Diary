import streamlit as st
import pandas as pd
import plotly.express as px

def render(role):
    conn = st.connection("neon", type="sql")
    
    try:
        df = conn.query("SELECT * FROM wealth ORDER BY snapshot_date ASC")
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if df.empty:
        st.info("No wealth history recorded yet. Use the 'Sync Now' button to take your first daily snapshot.")
        return

    # --- Data Processing Engine ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df['total_pl'] = df['current_value'] - df['total_investment']
    
    # Dynamically calculate day-to-day changes
    df['day_change'] = df['current_value'].diff().fillna(0)
    df['roi_pct'] = (df['total_pl'] / df['total_investment'] * 100).fillna(0)

    # --- UI & Charting ---
    st.subheader("Net Worth Trajectory")
    
    # View Selector
    metric_map = {
        "Current Portfolio Value": "current_value",
        "Total Active Investment": "total_investment",
        "Net Unrealized P/L": "total_pl",
        "Daily Value Change": "day_change"
    }
    sel_metric_label = st.selectbox("Select Metric to Visualize", list(metric_map.keys()))
    sel_metric = metric_map[sel_metric_label]

    # Plotly Line Chart
    line_color = "#00FF00" if sel_metric in ["current_value", "total_pl"] else "#00CCFF"
    fig = px.area(
        df, x="snapshot_date", y=sel_metric, 
        markers=True, title=f"{sel_metric_label} Over Time"
    )
    fig.update_traces(line_color=line_color, fillcolor=line_color, fill='tozeroy')
    fig.update_layout(xaxis_title="Date", yaxis_title="Amount (Rs)", margin=dict(t=30, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

    # Raw Data Table
    with st.expander("📋 View Raw Snapshot Data"):
        display_df = df[['snapshot_date', 'total_investment', 'current_value', 'total_pl', 'day_change', 'roi_pct']].copy()
        display_df['snapshot_date'] = display_df['snapshot_date'].dt.strftime('%Y-%m-%d')
        display_df.rename(columns={
            'snapshot_date': 'Date', 'total_investment': 'Invested', 
            'current_value': 'Value', 'total_pl': 'Net P/L', 
            'day_change': 'Day Change', 'roi_pct': 'ROI %'
        }, inplace=True)
        
        st.dataframe(display_df.style.format({
            "Invested": "{:,.2f}", "Value": "{:,.2f}", 
            "Net P/L": "{:,.2f}", "Day Change": "{:,.2f}", "ROI %": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

def render(role):
    conn = st.connection("neon", type="sql")
    
    try:
        # Added ttl=600 (10 mins) to cache the query and dramatically speed up the app
        df = conn.query("SELECT * FROM wealth ORDER BY snapshot_date ASC", ttl=600)
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
    df['day_change'] = df['current_value'].diff().fillna(0)
    
    # SAFE ROI Calculation: Prevents division by zero crashes
    df['roi_pct'] = 0.0
    mask = df['total_investment'] > 0
    df.loc[mask, 'roi_pct'] = (df.loc[mask, 'total_pl'] / df.loc[mask, 'total_investment']) * 100

    # --- TOP LEVEL KPIs ---
    latest = df.iloc[-1]
    prev_value = df.iloc[-2]['current_value'] if len(df) > 1 else latest['total_investment']
    daily_pct = ((latest['current_value'] - prev_value) / prev_value * 100) if prev_value > 0 else 0.0
    ath = df['current_value'].max()  # All-Time High

    st.markdown("### 💎 Current Portfolio Status")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Worth", f"Rs {latest['current_value']:,.2f}", f"{latest['day_change']:,.2f} ({daily_pct:.2f}%) today")
    m2.metric("Total Invested", f"Rs {latest['total_investment']:,.2f}")
    m3.metric("Unrealized P/L", f"Rs {latest['total_pl']:,.2f}", f"{latest['roi_pct']:.2f}% overall", delta_color="normal")
    m4.metric("All-Time High (ATH)", f"Rs {ath:,.2f}", f"Rs {latest['current_value'] - ath:,.2f} from ATH")

    st.divider()

    # --- UI & Charting ---
    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Trajectory Options")
        
        # New default view overlays Invested vs Value
        metric_map = {
            "Compare: Value vs Invested": "compare",
            "Current Portfolio Value": "current_value",
            "Net Unrealized P/L": "total_pl",
            "Daily Value Change": "day_change"
        }
        sel_metric_label = st.radio("Select Metric to Visualize", list(metric_map.keys()))
        sel_metric = metric_map[sel_metric_label]

        # New Timeframe Filter
        st.write("")
        timeframe = st.selectbox("📅 Timeframe", ["All Time", "Last 30 Days", "Last 90 Days", "Year to Date"])

    # Filter Data by Timeframe
    now = pd.Timestamp.today()
    if timeframe == "Last 30 Days":
        graph_df = df[df['snapshot_date'] >= (now - pd.Timedelta(days=30))]
    elif timeframe == "Last 90 Days":
        graph_df = df[df['snapshot_date'] >= (now - pd.Timedelta(days=90))]
    elif timeframe == "Year to Date":
        graph_df = df[df['snapshot_date'].dt.year == now.year]
    else:
        graph_df = df.copy()

    with c2:
        if graph_df.empty:
            st.warning(f"No snapshot data available for {timeframe}.")
        elif sel_metric == "compare":
            # Advanced Multi-line overlapping chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=graph_df['snapshot_date'], y=graph_df['total_investment'], 
                                     fill='tozeroy', name='Invested Capital', line=dict(color='#A3B1C6')))
            fig.add_trace(go.Scatter(x=graph_df['snapshot_date'], y=graph_df['current_value'], 
                                     fill='tonexty', name='Current Value', line=dict(color='#00CC96')))
            fig.update_layout(title="Investment vs. Current Value Growth", xaxis_title="Date", 
                              yaxis_title="Amount (Rs)", hovermode="x unified", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            # Standard single-metric chart
            line_color = "#00CC96" if sel_metric in ["current_value", "total_pl"] else "#EF553B"
            fig = px.area(
                graph_df, x="snapshot_date", y=sel_metric, 
                markers=True, title=f"{sel_metric_label} ({timeframe})"
            )
            fig.update_traces(line_color=line_color, fillcolor=line_color)
            fig.update_layout(xaxis_title="Date", yaxis_title="Amount (Rs)", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    # Raw Data Table
    with st.expander("📋 View Raw Snapshot Data"):
        display_df = df[['snapshot_date', 'total_investment', 'current_value', 'total_pl', 'day_change', 'roi_pct']].copy()
        # Ensure descending order for the table so newest is on top
        display_df = display_df.sort_values(by="snapshot_date", ascending=False)
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

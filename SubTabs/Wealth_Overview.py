import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

def render(role):
    conn = st.connection("neon", type="sql")
    
    try:
        # Fetching entire history for accurate baseline math
        df = conn.query("SELECT * FROM wealth ORDER BY snapshot_date ASC", ttl=600)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if len(df) < 2:
        st.info("Gathering data... Your wealth trajectory will appear after your second daily sync.")
        return

    # --- 1. CORE DATA PROCESSING (Run on ALL data before filtering) ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df['total_pl'] = df['current_value'] - df['total_investment']
    
    # Identify Cash Flows (Deposits/Withdrawals)
    df['investment_change'] = df['total_investment'].diff().fillna(0)

    # FIX: Isolate True Market Performance (Kill the Deposit Illusion)
    # Daily change in total P/L perfectly isolates market moves from cash deposits
    df['day_market_change'] = df['total_pl'].diff().fillna(0)
    
    # Calculate Daily ROI % correctly by stripping out today's deposits from the denominator
    df['prev_market_value'] = df['current_value'].shift(1)
    df['day_pct'] = np.where(
        df['prev_market_value'] > 0,
        (df['day_market_change'] / df['prev_market_value']) * 100,
        0.0
    )

    # Overall ROI %
    df['roi_pct'] = np.where(
        df['total_investment'] > 0,
        (df['total_pl'] / df['total_investment']) * 100,
        0.0
    )

    # --- 2. HIGH-WATER MARK (Adjusted ATH) ---
    adjusted_ath = []
    current_ath = df['current_value'].iloc[0]

    for idx, row in df.iterrows():
        if row['investment_change'] > 0:
            current_ath += row['investment_change']
        elif row['investment_change'] < 0:
            prev_investment = row['total_investment'] - row['investment_change']
            if prev_investment > 0:
                withdrawal_pct = abs(row['investment_change']) / prev_investment
                current_ath -= (current_ath * withdrawal_pct)

        if row['current_value'] > current_ath:
            current_ath = row['current_value']
        adjusted_ath.append(current_ath)

    df['adjusted_ath'] = adjusted_ath

    # --- 3. TOP LEVEL KPIs ---
    latest = df.iloc[-1]
    
    st.markdown("### 💎 Current Portfolio Status")
    m1, m2, m3, m4 = st.columns(4)
    
    # Dynamic coloring for today's market performance
    day_color = "normal" if latest['day_market_change'] >= 0 else "inverse"
    m1.metric("Net Worth", f"Rs {latest['current_value']:,.2f}", f"{latest['day_market_change']:,.2f} ({latest['day_pct']:.2f}%) today", delta_color=day_color)
    
    m2.metric("Total Invested", f"Rs {latest['total_investment']:,.2f}")
    
    pl_color = "normal" if latest['total_pl'] >= 0 else "inverse"
    m3.metric("Unrealized P/L", f"Rs {latest['total_pl']:,.2f}", f"{latest['roi_pct']:.2f}% overall", delta_color=pl_color)
    
    ath_distance = latest['current_value'] - latest['adjusted_ath']
    m4.metric("True Peak Value (ATH)", f"Rs {latest['adjusted_ath']:,.2f}", f"Rs {ath_distance:,.2f} from ATH", delta_color="inverse")

    st.divider()

    # --- 4. UI & TIMEFRAME FILTERING ---
    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Trajectory Options")
        
        metric_map = {
            "Compare: Value vs Invested": "compare",
            "Net Unrealized P/L": "total_pl",
            "Daily Market Returns": "day_market_change"
        }
        sel_metric_label = st.radio("Select Metric to Visualize", list(metric_map.keys()))
        sel_metric = metric_map[sel_metric_label]

        st.write("")
        timeframe = st.selectbox("📅 Timeframe", ["All Time", "Last 30 Days", "Last 90 Days", "Year to Date"])

    # Slice the dataframe AFTER all math is done
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
            # FIX: Clean multi-line chart (No more green/red overlay bugs)
            fig = go.Figure()
            # Invested Baseline
            fig.add_trace(go.Scatter(
                x=graph_df['snapshot_date'], y=graph_df['total_investment'], 
                name='Invested Capital', mode='lines',
                line=dict(color='#A3B1C6', width=2, dash='dot')
            ))
            # Current Value
            fig.add_trace(go.Scatter(
                x=graph_df['snapshot_date'], y=graph_df['current_value'], 
                name='Current Value', mode='lines',
                line=dict(color='#00CC96' if latest['total_pl'] >= 0 else '#EF553B', width=3)
            ))
            fig.update_layout(title="Investment vs. Current Value", xaxis_title="", yaxis_title="Amount (Rs)", 
                              hovermode="x unified", margin=dict(t=40, b=0, l=0, r=0),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)
            
        elif sel_metric == "total_pl":
            # FIX: Dynamic P/L Chart
            is_profit = graph_df['total_pl'].iloc[-1] >= 0
            line_color = "#00CC96" if is_profit else "#EF553B"
            fill_color = "rgba(0, 204, 150, 0.2)" if is_profit else "rgba(239, 85, 59, 0.2)"
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=graph_df['snapshot_date'], y=graph_df['total_pl'],
                fill='tozeroy', fillcolor=fill_color,
                line=dict(color=line_color, width=2), name="Net P/L"
            ))
            fig.update_layout(title="Net Unrealized Profit/Loss", xaxis_title="", yaxis_title="Rs", 
                              hovermode="x unified", margin=dict(t=40, b=0, l=0, r=0))
            # Add a zero baseline for clarity
            fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(fig, use_container_width=True)
            
        elif sel_metric == "day_market_change":
            # FIX: Daily Market Bar Chart (Green for up days, Red for down days)
            colors = np.where(graph_df['day_market_change'] >= 0, '#00CC96', '#EF553B')
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=graph_df['snapshot_date'], y=graph_df['day_market_change'],
                marker_color=colors, name="Daily Change"
            ))
            fig.update_layout(title="Daily True Market Performance", xaxis_title="", yaxis_title="Rs", 
                              margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    # --- 5. RAW DATA TABLE ---
    with st.expander("📋 View Raw Snapshot Data"):
        display_df = df[['snapshot_date', 'total_investment', 'current_value', 'total_pl', 'day_market_change', 'day_pct', 'roi_pct']].copy()
        display_df = display_df.sort_values(by="snapshot_date", ascending=False)
        display_df['snapshot_date'] = display_df['snapshot_date'].dt.strftime('%Y-%m-%d')
        
        display_df.rename(columns={
            'snapshot_date': 'Date', 
            'total_investment': 'Invested', 
            'current_value': 'Value', 
            'total_pl': 'Net P/L', 
            'day_market_change': 'Market Move (Rs)', 
            'day_pct': 'Daily %',
            'roi_pct': 'Overall ROI %'
        }, inplace=True)
        
        st.dataframe(display_df.style.format({
            "Invested": "{:,.2f}", 
            "Value": "{:,.2f}", 
            "Net P/L": "{:,.2f}", 
            "Market Move (Rs)": "{:,.2f}", 
            "Daily %": "{:.2f}%",
            "Overall ROI %": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

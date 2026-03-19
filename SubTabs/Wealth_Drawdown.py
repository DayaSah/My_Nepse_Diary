import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

def render(role):
    conn = st.connection("neon", type="sql")
    try:
        # Added ttl for caching and fetched total_investment
        df = conn.query("SELECT snapshot_date, current_value, total_investment FROM wealth ORDER BY snapshot_date ASC", ttl=600)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if len(df) < 2:
        st.info("Not enough data points yet. Keep syncing your wealth daily!")
        return

    # --- Drawdown Math Engine ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    
    # Calculate rolling All-Time High (ATH)
    df['rolling_max'] = df['current_value'].cummax()
    
    # Calculate Drawdown (Current Value minus ATH)
    df['drawdown_rs'] = df['current_value'] - df['rolling_max']
    
    # Safe percentage calculation
    df['drawdown_pct'] = 0.0
    mask = df['rolling_max'] > 0
    df.loc[mask, 'drawdown_pct'] = (df.loc[mask, 'drawdown_rs'] / df.loc[mask, 'rolling_max']) * 100

    # --- Advanced Metrics ---
    current_val = df.iloc[-1]['current_value']
    current_ath = df.iloc[-1]['rolling_max']
    current_dd_pct = df.iloc[-1]['drawdown_pct']
    current_dd_rs = df.iloc[-1]['drawdown_rs']
    
    max_dd_pct = df['drawdown_pct'].min()
    max_dd_rs = df['drawdown_rs'].min()

    # Calculate "Days Underwater" (How long since we last hit a new ATH)
    # Find the last date where the current value was equal to the rolling max
    last_ath_date = df[df['current_value'] == df['rolling_max']]['snapshot_date'].max()
    days_underwater = (df.iloc[-1]['snapshot_date'] - last_ath_date).days

    # --- UI & VISUALS ---
    st.markdown("### 📉 Risk & Drawdown Analysis")
    st.caption("Measure the depth and duration of portfolio declines from its peak.")

    # Top Level Risk KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("All-Time High (ATH)", f"Rs {current_ath:,.0f}")
    
    # Delta coloring: inverse means red is down, green is up. Drawdowns are negative.
    c2.metric("Current Drawdown", f"{current_dd_pct:.2f}%", f"Rs {current_dd_rs:,.0f}", delta_color="inverse")
    
    c3.metric("Max Historical Drawdown", f"{max_dd_pct:.2f}%", f"Rs {max_dd_rs:,.0f}", delta_color="inverse")
    
    # Time Underwater Metric
    if days_underwater == 0:
        c4.metric("Days Underwater", "0 Days", "At ATH! 🚀", delta_color="normal")
    else:
        c4.metric("Days Underwater", f"{days_underwater} Days", "Waiting for recovery", delta_color="off")

    st.divider()

    t1, t2 = st.tabs(["⛰️ ATH vs Current (The Gap)", "📊 Depth Chart (%)"])

    with t1:
        st.markdown("##### The Drawdown Gap")
        st.caption("Visually represents the gap between your peak wealth and current wealth.")
        
        fig_gap = go.Figure()
        
        # Plot the ATH Line (Flat top, steps up)
        fig_gap.add_trace(go.Scatter(
            x=df['snapshot_date'], y=df['rolling_max'],
            line=dict(color='#A3B1C6', width=2, dash='dot'),
            name='All-Time High (ATH)',
            hoverinfo='skip'
        ))
        
        # Plot the Current Value Line
        fig_gap.add_trace(go.Scatter(
            x=df['snapshot_date'], y=df['current_value'],
            fill='tonexty', # Fills the gap up to the ATH line
            fillcolor='rgba(239, 85, 59, 0.2)', # Transparent Red
            line=dict(color='#00CC96', width=2),
            name='Current Value'
        ))
        
        fig_gap.update_layout(
            xaxis_title="Date", 
            yaxis_title="Portfolio Value (Rs)",
            hovermode="x unified",
            margin=dict(t=20, b=0, l=0, r=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_gap, use_container_width=True)

    with t2:
        st.markdown("##### Historical Drawdown Depth")
        st.caption("Focuses purely on the percentage decline over time.")
        
        fig_depth = px.area(
            df, x='snapshot_date', y='drawdown_pct', 
            labels={'drawdown_pct': 'Drawdown (%)', 'snapshot_date': 'Date'}
        )
        fig_depth.update_traces(line_color="#EF553B", fillcolor="rgba(239, 85, 59, 0.4)")
        fig_depth.update_layout(margin=dict(t=20, b=0, l=0, r=0))
        st.plotly_chart(fig_depth, use_container_width=True)

    # --- Data Table ---
    with st.expander("📋 View Drawdown History"):
        display_df = df[['snapshot_date', 'current_value', 'rolling_max', 'drawdown_rs', 'drawdown_pct']].copy()
        display_df = display_df.sort_values(by="snapshot_date", ascending=False)
        display_df['snapshot_date'] = display_df['snapshot_date'].dt.strftime('%Y-%m-%d')
        
        display_df.rename(columns={
            'snapshot_date': 'Date',
            'current_value': 'Current Value',
            'rolling_max': 'ATH at Date',
            'drawdown_rs': 'Drawdown (Rs)',
            'drawdown_pct': 'Drawdown (%)'
        }, inplace=True)
        
        st.dataframe(display_df.style.format({
            "Current Value": "{:,.2f}",
            "ATH at Date": "{:,.2f}",
            "Drawdown (Rs)": "{:,.2f}",
            "Drawdown (%)": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

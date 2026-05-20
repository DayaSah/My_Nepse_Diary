import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

def render(role):
    # --- 1. DATA FETCHING ---
    conn = st.connection("neon", type="sql")
    try:
        df = conn.query("SELECT snapshot_date, current_value, total_investment FROM wealth ORDER BY snapshot_date ASC", ttl=600)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if len(df) < 2:
        st.info("Not enough data points yet. Keep syncing your wealth daily!")
        return

    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])

    # --- 2. THE HIGH-WATER MARK (HWM) MATH ENGINE ---
    # Calculate daily changes in invested capital (Deposits/Withdrawals)
    df['investment_change'] = df['total_investment'].diff().fillna(0)
    
    adjusted_ath = []
    current_ath = df['current_value'].iloc[0]

    for idx, row in df.iterrows():
        # Adjust ATH for Cash Flows to prevent the "Deposit Illusion"
        if row['investment_change'] > 0:
            current_ath += row['investment_change'] # Deposit raises the ATH threshold
        elif row['investment_change'] < 0:
            # Withdrawals reduce the ATH proportionately so drawdown % stays accurate
            prev_investment = row['total_investment'] - row['investment_change']
            if prev_investment > 0:
                withdrawal_pct = abs(row['investment_change']) / prev_investment
                current_ath -= (current_ath * withdrawal_pct)

        # Update ATH if organic market growth pushes value past the adjusted threshold
        if row['current_value'] > current_ath:
            current_ath = row['current_value']

        adjusted_ath.append(current_ath)

    df['adjusted_ath'] = adjusted_ath
    
    # Drawdown Calculations (Stored as positive absolute numbers)
    df['drawdown_rs'] = df['adjusted_ath'] - df['current_value']
    df['drawdown_pct'] = np.where(df['adjusted_ath'] > 0, (df['drawdown_rs'] / df['adjusted_ath']) * 100, 0.0)

    # --- 3. METRIC EXTRACTION ---
    current = df.iloc[-1]
    current_val = current['current_value']
    current_ath_val = current['adjusted_ath']
    current_dd_pct = current['drawdown_pct']
    current_dd_rs = current['drawdown_rs']
    
    # Find the EXACT day of the worst historical drawdown
    worst_idx = df['drawdown_pct'].idxmax()
    worst_day = df.loc[worst_idx]
    max_dd_pct = worst_day['drawdown_pct']
    max_dd_rs = worst_day['drawdown_rs']
    worst_date_str = worst_day['snapshot_date'].strftime('%b %d, %Y')

    # Days Underwater (Days since current_value was equal to adjusted_ath)
    # Adding a tiny tolerance (0.1) for floating point precision safety
    is_at_ath = df['current_value'] >= (df['adjusted_ath'] - 0.1)
    last_ath_date = df[is_at_ath]['snapshot_date'].max()
    days_underwater = (current['snapshot_date'] - last_ath_date).days

    # --- 4. UI & VISUALS ---
    st.markdown("### 📉 Risk & Drawdown Analysis")
    st.caption("Measure the true market decline of your portfolio, adjusted perfectly for your cash deposits and withdrawals.")

    # Top Level Risk KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("True Peak Value (ATH)", f"Rs {current_ath_val:,.0f}", help="Adjusts upward when you deposit cash so your drawdown doesn't magically disappear.")
    
    # We pass negative values to the delta so Streamlit naturally paints them Red
    c2.metric("Current Drawdown", f"{current_dd_pct:.2f}% down", f"-Rs {current_dd_rs:,.0f}", delta_color="inverse")
    
    c3.metric("Worst Historical Drop", f"{max_dd_pct:.2f}% down", f"-Rs {max_dd_rs:,.0f}", delta_color="inverse", help=f"This occurred on {worst_date_str}")
    
    if days_underwater == 0:
        c4.metric("Days Underwater", "0 Days", "At ATH! 🚀", delta_color="normal")
    else:
        c4.metric("Days Underwater", f"{days_underwater} Days", "Waiting for recovery", delta_color="off")

    st.divider()

    t1, t2 = st.tabs(["⛰️ ATH vs Current (The Gap)", "📊 Depth Chart (%)"])

    with t1:
        st.markdown("##### The Drawdown Gap")
        st.caption("The red shaded area represents wealth temporarily lost to the market.")
        
        fig_gap = go.Figure()
        
        # Plot 1: Current Value (Plotted FIRST)
        fig_gap.add_trace(go.Scatter(
            x=df['snapshot_date'], y=df['current_value'],
            line=dict(color='#00CC96', width=2),
            name='Current Value'
        ))
        
        # Plot 2: Adjusted ATH (Plotted SECOND with tonexty fill)
        fig_gap.add_trace(go.Scatter(
            x=df['snapshot_date'], y=df['adjusted_ath'],
            fill='tonexty', # Perfectly fills the gap down to the Current Value line
            fillcolor='rgba(239, 85, 59, 0.2)', 
            line=dict(color='#A3B1C6', width=2, dash='dot'),
            name='Adjusted Peak (ATH)',
            hoverinfo='skip'
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
        
        # Convert to negative for the classic 'underwater' area chart look
        df['chart_dd_pct'] = -df['drawdown_pct']
        
        fig_depth = px.area(
            df, x='snapshot_date', y='chart_dd_pct', 
            labels={'chart_dd_pct': 'Drawdown (%)', 'snapshot_date': 'Date'}
        )
        fig_depth.update_traces(line_color="#EF553B", fillcolor="rgba(239, 85, 59, 0.4)")
        fig_depth.update_layout(
            margin=dict(t=20, b=0, l=0, r=0),
            yaxis=dict(autorange="reversed") # Flips the Y axis so drops go DOWN visually
        )
        st.plotly_chart(fig_depth, use_container_width=True)

    # --- 5. DATA TABLE ---
    with st.expander("📋 View True Drawdown History"):
        display_df = df[['snapshot_date', 'current_value', 'total_investment', 'adjusted_ath', 'drawdown_rs', 'drawdown_pct']].copy()
        display_df = display_df.sort_values(by="snapshot_date", ascending=False)
        display_df['snapshot_date'] = display_df['snapshot_date'].dt.strftime('%Y-%m-%d')
        
        display_df.rename(columns={
            'snapshot_date': 'Date',
            'current_value': 'Current Value',
            'total_investment': 'Total Invested',
            'adjusted_ath': 'Adjusted ATH',
            'drawdown_rs': 'Lost from Peak (Rs)',
            'drawdown_pct': 'Drawdown (%)'
        }, inplace=True)
        
        st.dataframe(display_df.style.format({
            "Current Value": "{:,.2f}",
            "Total Invested": "{:,.2f}",
            "Adjusted ATH": "{:,.2f}",
            "Lost from Peak (Rs)": "{:,.2f}",
            "Drawdown (%)": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

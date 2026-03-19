import streamlit as st
import pandas as pd
import plotly.express as px

def render(role):
    conn = st.connection("neon", type="sql")
    try:
        # Added ttl for caching and fetched total_investment to calculate true PnL
        df = conn.query("SELECT snapshot_date, total_investment, current_value FROM wealth ORDER BY snapshot_date ASC", ttl=600)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if len(df) < 2:
        st.info("Gathering data... Monthly charts will appear when more history is recorded.")
        return

    # --- Monthly Performance Engine ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df['Year'] = df['snapshot_date'].dt.year
    df['Month_Num'] = df['snapshot_date'].dt.month
    df['Month'] = df['snapshot_date'].dt.month_name().str[:3] # Jan, Feb, Mar...

    # Calculate actual PnL for each day
    df['total_pl'] = df['current_value'] - df['total_investment']

    # Group by Year and Month, taking the LAST recorded value of that month
    monthly_df = df.groupby(['Year', 'Month_Num', 'Month']).last().reset_index()
    monthly_df = monthly_df.sort_values(['Year', 'Month_Num'])

    # 1. Calculate MoM % Change (Net Worth Growth - Includes Deposits)
    monthly_df['MoM_NW_Change_%'] = monthly_df['current_value'].pct_change() * 100

    # 2. Calculate Absolute Monthly PnL Generated (True Trading Profit/Loss)
    # This takes the Total PnL at the end of the month and subtracts the Total PnL from the end of last month
    monthly_df['Monthly_PnL_Rs'] = monthly_df['total_pl'].diff().fillna(monthly_df['total_pl'])

    if monthly_df['MoM_NW_Change_%'].isna().all():
        st.info("Not enough months crossed yet to calculate monthly returns.")
        return

    # --- UI & VISUALS ---
    st.markdown("### 🗓️ Monthly Performance Analytics")
    
    t1, t2 = st.tabs(["🔥 Growth Heatmap (%)", "📊 Absolute Profit/Loss (Rs)"])

    with t1:
        st.caption("Month-over-Month percentage growth of your Total Net Worth (Note: Includes capital deposits/withdrawals).")
        
        # Pivot table for Heatmap
        heatmap_data = monthly_df.pivot(index='Year', columns='Month', values='MoM_NW_Change_%')
        
        # Force correct chronological order of columns even if months are missing
        months_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        existing_months = [m for m in months_order if m in heatmap_data.columns]
        heatmap_data = heatmap_data[existing_months]

        # Heatmap Plotly Chart
        fig_heat = px.imshow(
            heatmap_data, 
            text_auto=".2f", 
            aspect="auto",
            color_continuous_scale="RdYlGn", 
            color_continuous_midpoint=0,
            labels=dict(color="Growth %")
        )
        fig_heat.update_layout(xaxis_title="", yaxis_title="Year", margin=dict(t=20, b=0, l=0, r=0))
        st.plotly_chart(fig_heat, use_container_width=True)

    with t2:
        st.caption("Actual Unrealized Profit or Loss generated *within* each specific month.")
        
        # Create a combined label for the X-axis (e.g., "2023 Jan")
        monthly_df['Period'] = monthly_df['Year'].astype(str) + " " + monthly_df['Month']
        
        # Color coding: Green for profit, Red for loss
        monthly_df['Color'] = monthly_df['Monthly_PnL_Rs'].apply(lambda x: '#00CC96' if x >= 0 else '#EF553B')

        # Bar Chart
        fig_bar = px.bar(
            monthly_df, 
            x='Period', 
            y='Monthly_PnL_Rs',
            text_auto='.2s', # Format text to look clean (e.g., 15k, -2.5k)
            title="Monthly Absolute Trading Profit/Loss"
        )
        
        # Apply custom colors and formatting
        fig_bar.update_traces(marker_color=monthly_df['Color'], textposition='outside')
        fig_bar.update_layout(
            xaxis_title="Month", 
            yaxis_title="Net PnL (Rs)", 
            margin=dict(t=40, b=0, l=0, r=0),
            showlegend=False
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- Data Table ---
    with st.expander("📋 View Monthly Tabular Data"):
        display_df = monthly_df[['Year', 'Month', 'current_value', 'total_pl', 'Monthly_PnL_Rs', 'MoM_NW_Change_%']].copy()
        display_df = display_df.sort_values(['Year', 'Month_Num'], ascending=[False, False])
        display_df.rename(columns={
            'current_value': 'End of Month Net Worth',
            'total_pl': 'Cumulative PnL',
            'Monthly_PnL_Rs': 'PnL Generated This Month',
            'MoM_NW_Change_%': 'Net Worth Growth %'
        }, inplace=True)
        
        st.dataframe(display_df.style.format({
            "End of Month Net Worth": "{:,.2f}",
            "Cumulative PnL": "{:,.2f}",
            "PnL Generated This Month": "{:,.2f}",
            "Net Worth Growth %": "{:.2f}%"
        }), use_container_width=True, hide_index=True)

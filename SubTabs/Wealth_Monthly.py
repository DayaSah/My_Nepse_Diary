import streamlit as st
import pandas as pd
import plotly.express as px

def render(role):
    conn = st.connection("neon", type="sql")
    try:
        df = conn.query("SELECT snapshot_date, current_value FROM wealth ORDER BY snapshot_date ASC")
    except:
        return

    if len(df) < 2:
        st.info("Gathering data... Monthly charts will appear when more history is recorded.")
        return

    # --- Monthly Performance Engine ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df['Year'] = df['snapshot_date'].dt.year
    df['Month'] = df['snapshot_date'].dt.month_name().str[:3] # Jan, Feb, Mar...

    # Group by Year and Month, taking the LAST value of that month
    monthly_df = df.groupby(['Year', 'Month']).last().reset_index()
    
    # Sort chronological months
    months_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_df['Month'] = pd.Categorical(monthly_df['Month'], categories=months_order, ordered=True)
    monthly_df = monthly_df.sort_values(['Year', 'Month'])

    # Calculate Month-over-Month % Change
    monthly_df['MoM_Change'] = monthly_df['current_value'].pct_change() * 100

    if monthly_df['MoM_Change'].isna().all():
        st.info("Not enough months crossed yet to calculate monthly returns.")
        return

    st.subheader("🗓️ Monthly Performance Heatmap")
    st.caption("Month-over-Month percentage growth of your portfolio value.")

    # Pivot table for Heatmap
    heatmap_data = monthly_df.pivot(index='Year', columns='Month', values='MoM_Change')

    # Heatmap Plotly Chart
    fig = px.imshow(
        heatmap_data, 
        text_auto=".2f", # Show numbers with 2 decimals
        aspect="auto",
        color_continuous_scale="RdYlGn", # Red for negative, Green for positive
        color_continuous_midpoint=0,
        labels=dict(color="Growth %")
    )
    fig.update_layout(xaxis_title="", yaxis_title="Year", margin=dict(t=20, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

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
        st.info("Not enough data points yet. Keep syncing your wealth daily!")
        return

    # --- Drawdown Math Engine ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    
    # Calculate rolling All-Time High (ATH)
    df['rolling_max'] = df['current_value'].cummax()
    
    # Calculate Drawdown (How far below the ATH we currently are)
    df['drawdown_rs'] = df['current_value'] - df['rolling_max']
    df['drawdown_pct'] = (df['drawdown_rs'] / df['rolling_max']) * 100

    current_dd = df.iloc[-1]['drawdown_pct']
    max_dd = df['drawdown_pct'].min()

    st.subheader("📉 Portfolio Drawdown")
    st.caption("Measures the decline from your portfolio's All-Time High (ATH).")

    c1, c2, c3 = st.columns(3)
    c1.metric("All-Time High Value", f"Rs {df['rolling_max'].max():,.0f}")
    c2.metric("Current Drawdown", f"{current_dd:.2f}%", help="0% means you are currently AT an All-Time High.")
    c3.metric("Max Historical Drawdown", f"{max_dd:.2f}%", help="The deepest your portfolio has ever fallen.")

    # Charting the Drawdown
    fig = px.area(
        df, x='snapshot_date', y='drawdown_pct', 
        title="Drawdown Percentage Over Time"
    )
    # Make it red because drawdowns are negative
    fig.update_traces(line_color="#FF4B4B", fillcolor="rgba(255, 75, 75, 0.3)")
    fig.update_layout(yaxis_title="Drawdown (%)", xaxis_title="Date")
    st.plotly_chart(fig, use_container_width=True)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

def render(role):
    # --- 1. DATA FETCHING ---
    conn = st.connection("neon", type="sql")
    try:
        df = conn.query("SELECT snapshot_date, total_investment, current_value FROM wealth ORDER BY snapshot_date ASC", ttl=600)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        st.error(f"Database Error: {e}")
        return

    if len(df) < 1:
        st.info("Gathering data... Analytics will appear when history is recorded.")
        return

    # --- 2. CONTINUOUS CALENDAR & TRUE PnL ENGINE ---
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df['year_month'] = df['snapshot_date'].dt.to_period('M')

    # Group by Month, taking the LAST recorded value of that month
    monthly_df = df.groupby('year_month').last().reset_index()

    # FIX: The Missing Month Trap (Continuous Calendar)
    # Generate a flawless calendar from your first month to your current month
    min_month = monthly_df['year_month'].min()
    max_month = monthly_df['year_month'].max()
    all_months = pd.period_range(min_month, max_month, freq='M')
    
    # Reindex the dataframe to include missing months
    monthly_df = monthly_df.set_index('year_month').reindex(all_months)
    
    # Forward-fill capital. If you didn't sync in April, your April ending balance was the same as March's.
    monthly_df['total_investment'] = monthly_df['total_investment'].ffill()
    monthly_df['current_value'] = monthly_df['current_value'].ffill()
    
    # Calculate True Cumulative PnL
    monthly_df['total_pl'] = monthly_df['current_value'] - monthly_df['total_investment']
    monthly_df = monthly_df.reset_index().rename(columns={'index': 'year_month'})

    # FIX: The First-Month Spike & True ROI
    # Calculate PnL generated *specifically* inside this month
    monthly_df['Monthly_PnL_Rs'] = monthly_df['total_pl'].diff()
    # For the very first month ever recorded, the monthly PnL is simply the cumulative PnL
    monthly_df.loc[0, 'Monthly_PnL_Rs'] = monthly_df.loc[0, 'total_pl']

    # True ROI % (Isolates trading performance from cash deposits)
    monthly_df['True_ROI_%'] = np.where(
        monthly_df['total_investment'] > 0,
        (monthly_df['Monthly_PnL_Rs'] / monthly_df['total_investment']) * 100,
        0.0
    )

    # --- 3. THE 8% MONTHLY TARGET SYSTEM ---
    TARGET_ROI = 8.0
    monthly_df['Target_PnL_Rs'] = monthly_df['total_investment'] * (TARGET_ROI / 100.0)
    monthly_df['Variance_Rs'] = monthly_df['Monthly_PnL_Rs'] - monthly_df['Target_PnL_Rs']
    monthly_df['Target_Hit'] = monthly_df['True_ROI_%'] >= TARGET_ROI

    # Formatting columns for UI
    monthly_df['Year'] = monthly_df['year_month'].dt.year
    monthly_df['Month'] = monthly_df['year_month'].dt.strftime('%b')
    monthly_df['Period_Str'] = monthly_df['year_month'].dt.strftime('%b %Y')

    # --- 4. ADVANCED METRICS EXTRACTION ---
    total_months = len(monthly_df)
    months_hit_target = monthly_df['Target_Hit'].sum()
    target_hit_rate = (months_hit_target / total_months) * 100 if total_months > 0 else 0
    
    avg_monthly_roi = monthly_df['True_ROI_%'].mean()
    
    best_month_idx = monthly_df['True_ROI_%'].idxmax()
    best_month_str = monthly_df.loc[best_month_idx, 'Period_Str']
    best_month_roi = monthly_df.loc[best_month_idx, 'True_ROI_%']

    # --- 5. UI & VISUALS ---
    st.markdown("### 🗓️ Monthly Analytics & Target Tracking")
    st.caption("Track your True ROI against your 8% monthly growth objective.")

    # Top Level Target KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Average Monthly ROI", f"{avg_monthly_roi:.2f}%")
    c2.metric("8% Target Hit Rate", f"{target_hit_rate:.1f}%", f"{months_hit_target} / {total_months} Months")
    c3.metric("Best Month", f"{best_month_str}", f"+{best_month_roi:.2f}%", delta_color="normal")
    
    # Current Month Trajectory
    current_month = monthly_df.iloc[-1]
    variance_str = f"+Rs {current_month['Variance_Rs']:,.0f}" if current_month['Variance_Rs'] >= 0 else f"-Rs {abs(current_month['Variance_Rs']):,.0f}"
    c4.metric("Current Month Variance", f"{current_month['True_ROI_%']:.2f}%", variance_str, 
              delta_color="normal" if current_month['Variance_Rs'] >= 0 else "inverse")

    st.divider()

    t1, t2 = st.tabs(["📊 Profit vs. 8% Target (Rs)", "🔥 True ROI Heatmap (%)"])

    with t1:
        st.markdown("##### Absolute PnL vs Target Trajectory")
        st.caption("Bars represent actual profit generated. The yellow line represents the 8% monetary target based on your deployed capital.")
        
        # Color coding: Green for profit, Red for loss
        monthly_df['Color'] = np.where(monthly_df['Monthly_PnL_Rs'] >= 0, '#00CC96', '#EF553B')

        fig_target = go.Figure()
        
        # Actual PnL Bars
        fig_target.add_trace(go.Bar(
            x=monthly_df['Period_Str'], 
            y=monthly_df['Monthly_PnL_Rs'],
            marker_color=monthly_df['Color'],
            name='Actual Net PnL',
            text=monthly_df['Monthly_PnL_Rs'].apply(lambda x: f"{x/1000:.1f}k" if abs(x) >= 1000 else str(round(x))),
            textposition='outside'
        ))
        
        # 8% Target Line
        fig_target.add_trace(go.Scatter(
            x=monthly_df['Period_Str'], 
            y=monthly_df['Target_PnL_Rs'],
            mode='lines+markers',
            line=dict(color='#FFB703', width=3, dash='dot'), # Golden Yellow Target Line
            marker=dict(size=8, color='#FFB703'),
            name='8% Target Required'
        ))

        fig_target.update_layout(
            xaxis_title="", 
            yaxis_title="Net PnL (Rs)", 
            margin=dict(t=20, b=0, l=0, r=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_target, use_container_width=True)

    with t2:
        st.markdown("##### True ROI Heatmap")
        st.caption("Pure trading performance percentage, immune to cash deposits and withdrawals.")
        
        # Pivot table for Heatmap
        heatmap_data = monthly_df.pivot(index='Year', columns='Month', values='True_ROI_%')
        
        # Force correct chronological order of columns
        months_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        existing_months = [m for m in months_order if m in heatmap_data.columns]
        heatmap_data = heatmap_data[existing_months]

        # FIX: The Plotly NaN Quirk (Create custom text array to hide 'nan' text)
        text_array = heatmap_data.applymap(lambda x: f"{x:.2f}%" if pd.notna(x) else "")

        fig_heat = px.imshow(
            heatmap_data, 
            aspect="auto",
            color_continuous_scale="RdYlGn", 
            color_continuous_midpoint=0,
            labels=dict(color="True ROI %")
        )
        fig_heat.update_traces(text=text_array, texttemplate="%{text}")
        fig_heat.update_layout(xaxis_title="", yaxis_title="Year", margin=dict(t=20, b=0, l=0, r=0))
        st.plotly_chart(fig_heat, use_container_width=True)

    # --- 6. DATA TABLE ---
    with st.expander("📋 View Monthly Target Data"):
        display_df = monthly_df[['Period_Str', 'total_investment', 'Monthly_PnL_Rs', 'Target_PnL_Rs', 'Variance_Rs', 'True_ROI_%', 'Target_Hit']].copy()
        display_df = display_df.sort_index(ascending=False)
        
        display_df.rename(columns={
            'Period_Str': 'Month',
            'total_investment': 'Deployed Capital',
            'Monthly_PnL_Rs': 'Actual PnL',
            'Target_PnL_Rs': 'Target PnL (8%)',
            'Variance_Rs': 'Variance',
            'True_ROI_%': 'True ROI %',
            'Target_Hit': 'Target Hit?'
        }, inplace=True)
        
        # Formatting Target Hit as Emojis
        display_df['Target Hit?'] = display_df['Target Hit?'].apply(lambda x: "✅ Yes" if x else "❌ No")
        
        st.dataframe(display_df.style.format({
            "Deployed Capital": "Rs {:,.2f}",
            "Actual PnL": "Rs {:,.2f}",
            "Target PnL (8%)": "Rs {:,.2f}",
            "Variance": "Rs {:,.2f}",
            "True ROI %": "{:.2f}%"
        }).map(lambda x: 'color: #00CC96; font-weight: bold;' if x == "✅ Yes" else 'color: #EF553B;', subset=['Target Hit?']), 
        use_container_width=True, hide_index=True)

import streamlit as st

def render_page(role):
    st.title("📈 Wealth Analytics Hub")
    st.caption("Track your net worth trajectory, analyze risk drawdowns, and review historical performance.")

    # Create the SubTabs UI
    tabs = st.tabs(["📊 Growth Overview", "📉 Drawdown Analysis", "🗓️ Monthly Heatmap"])
    
    # Dynamically load each subtab
    with tabs[0]:
        try:
            from SubTabs import Wealth_Overview
            Wealth_Overview.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab under construction: {e}")

    with tabs[1]:
        try:
            from SubTabs import Wealth_Drawdown
            Wealth_Drawdown.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab under construction: {e}")
            
    with tabs[2]:
        try:
            from SubTabs import Wealth_Monthly
            Wealth_Monthly.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab under construction: {e}")

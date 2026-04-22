import streamlit as st

def render_page(role):
    st.title("🧮 Trade Simulation & Planners")
    st.caption("Simulate buys, calculate exact net payouts, and plan your breakeven targets.")

    # Create the SubTabs UI
    tabs = st.tabs(["📉 WACC Averaging (Buy)", "💰 Net Profit Simulator (Sell)", "🚑 Recovery & Breakeven", "Entry And Exit Plan"])
    
    # Dynamically load each subtab
    with tabs[0]:
        try:
            from SubTabs import Sim_Buy_WACC
            Sim_Buy_WACC.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")

    with tabs[1]:
        try:
            from SubTabs import Sim_Sell_Target
            Sim_Sell_Target.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")
            
    with tabs[2]:
        try:
            from SubTabs import Sim_Recovery
            Sim_Recovery.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")

    with tabs[3]:
        try:
            from SubTabs import Entry_Plan
            Entry_Plan.render(role)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")


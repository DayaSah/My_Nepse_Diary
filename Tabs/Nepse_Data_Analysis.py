import streamlit as st
import pandas as pd

def build_portfolio_context():
    """Fetches live DB data and turns it into a readable string for the AIs."""
    conn = st.connection("neon", type="sql")
    try:
        port_df = conn.query("SELECT * FROM portfolio")
        cache_df = conn.query("SELECT * FROM cache")
        wealth_df = conn.query("SELECT * FROM wealth ORDER BY snapshot_date DESC LIMIT 1")
    except Exception as e:
        return f"Error fetching database: {e}"

    if port_df.empty:
        return "The user currently has no active stocks in their portfolio."

    # Build a simple summary
    context = "Here is the user's current NEPSE stock portfolio data:\n\n"
    
    # Wealth Summary
    if not wealth_df.empty:
        context += f"Total Net Worth: Rs {wealth_df.iloc[0]['current_value']:,.2f}\n"
        context += f"Total Invested: Rs {wealth_df.iloc[0]['total_investment']:,.2f}\n\n"

    # Holdings Summary
    context += "Active Holdings:\n"
    for _, row in port_df.iterrows():
        context += f"- {row['symbol']}: {row['transaction_type']} {row['qty']} units at Rs {row['price']}\n"
        
    context += "\nLive Market LTP Cache:\n"
    if not cache_df.empty:
        for _, row in cache_df.iterrows():
            context += f"- {row['symbol']}: Rs {row['ltp']} (Daily Change: {row['change']})\n"

    context += "\nInstructions: Act as a professional quantitative wealth manager. Use the above data to answer the user's query."
    return context

def render_page(role):
    st.title("🤖 Multi-Model AI Analyst")
    st.caption("Consult with top-tier AI models using your live portfolio data as context.")

    # Fetch the portfolio context once so we don't spam the database
    with st.spinner("Fetching live portfolio context for the AIs..."):
        db_context = build_portfolio_context()

    # Create the SubTabs UI
    tabs = st.tabs(["🔵 Google Gemini", "🟢 OpenAI ChatGPT", "✖️ xAI Grok"])
    
    # Dynamically load each subtab, passing the portfolio context to them
    with tabs[0]:
        try:
            from SubTabs import AI_Gemini
            AI_Gemini.render(role, db_context)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")

    with tabs[1]:
        try:
            from SubTabs import AI_ChatGPT
            AI_ChatGPT.render(role, db_context)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")
            
    with tabs[2]:
        try:
            from SubTabs import AI_Grok
            AI_Grok.render(role, db_context)
        except Exception as e:
            st.error(f"🚧 SubTab Error: {e}")

import streamlit as st
import pandas as pd
# Import the advanced page function
from SubTabs.Advanced_Portfolio import render_advanced_view 

def render_page(role):
    # Initialize navigation state
    if 'portfolio_view' not in st.session_state:
        st.session_state.portfolio_view = 'basic'

    # Check if we should show Advanced View
    if st.session_state.portfolio_view == 'advanced':
        if st.button("⬅️ Back to Basic Portfolio"):
            st.session_state.portfolio_view = 'basic'
            st.rerun()
        render_advanced_view() # Call the advanced function
        return

    # --- BASIC VIEW STARTS HERE ---
    st.title("💼 My Portfolio")
    conn = st.connection("neon", type="sql")

    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache", ttl=600)
        port_df.columns = [c.lower() for c in port_df.columns]
    except:
        st.error("Database Connection Error"); return

    if port_df.empty:
        st.info("Portfolio is empty."); return

    # --- Calculation Engine (Fixed WACC) ---
    # Ensure net_amount is numeric
    port_df['net_amount'] = pd.to_numeric(port_df['net_amount'], errors='coerce').fillna(0)
    port_df['qty'] = pd.to_numeric(port_df['qty'], errors='coerce').fillna(0)

    buys = port_df[port_df['transaction_type'].str.upper() == 'BUY']
    sells = port_df[port_df['transaction_type'].str.upper() == 'SELL']

    # CRITICAL FIX: Use net_amount (which includes fees) for WACC
    buy_grouped = buys.groupby('symbol').apply(
        lambda x: pd.Series({
            'total_buy_qty': x['qty'].sum(), 
            'total_buy_cost': x['net_amount'].sum() # Corrected: Uses net_amount instead of price * qty
        })
    ).reset_index()
    
    # Calculate True WACC
    buy_grouped['wacc'] = buy_grouped['total_buy_cost'] / buy_grouped['total_buy_qty']

    # Calculate remaining shares
    sell_qty = sells.groupby('symbol')['qty'].sum().reset_index().rename(columns={'qty': 's_qty'})
    active = pd.merge(buy_grouped, sell_qty, on='symbol', how='left').fillna(0)
    active['net_qty'] = active['total_buy_qty'] - active['s_qty']
    active = active[active['net_qty'] > 0].copy()

    # Match with LTP from Cache
    if not cache_df.empty:
        cache_df.columns = [c.lower() for c in cache_df.columns]
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left').fillna(0)
    else: 
        active['ltp'] = active['wacc']

    # Final Metrics
    active['invested'] = active['net_qty'] * active['wacc']
    active['current_val'] = active['net_qty'] * active['ltp']
    active['pl_amt'] = active['current_val'] - active['invested']
    
    # NEW METRICS: Breakeven & Weightage
    total_val = active['current_val'].sum()
    active['weight'] = (active['current_val'] / total_val) * 100
    active['breakeven'] = (active['wacc'] * 1.005) + (25 / active['net_qty'])

    # --- Summary Row ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Invested", f"Rs {active['invested'].sum():,.0f}")
    c2.metric("Market Value", f"Rs {total_val:,.0f}")
    c3.metric("Unrealized P/L", f"Rs {active['pl_amt'].sum():,.0f}", f"{(active['pl_amt'].sum()/active['invested'].sum()*100):.2f}%")

    st.divider()
    
    # THE NAVIGATION BUTTON
    if st.button("🚀 Switch to Advanced Portfolio (Deep Analytics)", use_container_width=True, type="primary"):
        st.session_state.portfolio_view = 'advanced'
        st.rerun()

    st.subheader("📋 Active Holdings")
    st.dataframe(
        active[['symbol', 'net_qty', 'wacc', 'breakeven', 'ltp', 'weight', 'pl_amt']], 
        use_container_width=True, hide_index=True,
        column_config={
            "weight": st.column_config.ProgressColumn("Portfolio %", format="%.1f%%", min_value=0, max_value=100),
            "pl_amt": st.column_config.NumberColumn("Profit/Loss", format="Rs %.2f"),
            "breakeven": "Breakeven"
        }
    )

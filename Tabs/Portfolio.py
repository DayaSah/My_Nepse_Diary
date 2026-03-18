import streamlit as st
import pandas as pd
import plotly.express as px

def render_page(role):
    st.title("💼 My Portfolio")
    st.caption("Active holdings and current market standing.")

    conn = st.connection("neon", type="sql")

    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache", ttl=600)
        port_df.columns = [c.lower() for c in port_df.columns]
        if not cache_df.empty: cache_df.columns = [c.lower() for c in cache_df.columns]
    except:
        st.error("Connection Error"); return

    if port_df.empty:
        st.info("Portfolio is empty."); return

    # --- Calculation Engine ---
    buys = port_df[port_df['transaction_type'].str.upper() == 'BUY']
    sells = port_df[port_df['transaction_type'].str.upper() == 'SELL']

    # WACC Calculation
    buy_grouped = buys.groupby('symbol').apply(
        lambda x: pd.Series({'t_qty': x['qty'].sum(), 't_cost': (x['qty'] * x['price']).sum()})
    ).reset_index()
    buy_grouped['wacc'] = buy_grouped['t_cost'] / buy_grouped['t_qty']

    # Net Qty
    sell_qty = sells.groupby('symbol')['qty'].sum().reset_index().rename(columns={'qty': 's_qty'})
    holdings = pd.merge(buy_grouped, sell_qty, on='symbol', how='left').fillna(0)
    holdings['net_qty'] = holdings['t_qty'] - holdings['s_qty']
    active = holdings[holdings['net_qty'] > 0].copy()

    # Merge LTP
    if not cache_df.empty:
        active = pd.merge(active, cache_df[['symbol', 'ltp']], on='symbol', how='left').fillna(0)
    else: active['ltp'] = active['wacc']

    # Metrics
    active['invested'] = active['net_qty'] * active['wacc']
    active['current_val'] = active['net_qty'] * active['ltp']
    active['pl_amt'] = active['current_val'] - active['invested']
    active['pl_pct'] = (active['pl_amt'] / active['invested']) * 100
    
    # NEW: Breakeven & Weightage
    total_portfolio_value = active['current_val'].sum()
    active['weight_pct'] = (active['current_val'] / total_portfolio_value) * 100
    # Breakeven includes approx 0.5% sell side fees
    active['breakeven'] = (active['wacc'] * 1.005) + (25 / active['net_qty'])

    # --- UI: Summary Metrics ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invested", f"Rs {active['invested'].sum():,.0f}")
    m2.metric("Market Value", f"Rs {total_portfolio_value:,.0f}")
    pl_total = active['pl_amt'].sum()
    m3.metric("Unrealized P/L", f"Rs {pl_total:,.0f}", f"{(pl_total/active['invested'].sum()*100):.2f}%")
    m4.metric("Stocks", len(active))

    st.divider()

    # --- UI: Navigation Button to Advanced ---
    if st.button("🔍 View Advanced Portfolio Analytics", use_container_width=True, type="primary"):
        st.info("Go to 'SubTabs -> Advanced Portfolio' for deep metrics.")

    # --- UI: Tables ---
    st.subheader("📋 Current Holdings")
    display_df = active[['symbol', 'net_qty', 'wacc', 'breakeven', 'ltp', 'weight_pct', 'pl_amt', 'pl_pct']].copy()
    
    st.dataframe(
        display_df, use_container_width=True, hide_index=True,
        column_config={
            "wacc": "WACC", "ltp": "LTP", "breakeven": "BEP",
            "weight_pct": st.column_config.ProgressColumn("Weight %", format="%.1f%%", min_value=0, max_value=100),
            "pl_pct": st.column_config.NumberColumn("Return %", format="%.2f%%"),
            "pl_amt": st.column_config.NumberColumn("Profit/Loss", format="Rs %.2f")
        }
    )

import streamlit as st
import pandas as pd
import plotly.express as px

def render_page(role):
    st.title("💼 My Portfolio")
    st.caption("Real-time view of your active holdings, WACC, and Unrealized P/L.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 1. FETCH AND PROCESS DATA
    # ==========================================
    try:
        # Fetch raw transactions and market cache
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache",ttl=3600)
        
        # Standardize column names to lowercase for Postgres compatibility
        port_df.columns = [c.lower() for c in port_df.columns]
        if not cache_df.empty:
            cache_df.columns = [c.lower() for c in cache_df.columns]
            
    except Exception as e:
        st.error(f"Database error: {e}")
        port_df = pd.DataFrame()
        cache_df = pd.DataFrame()

    if port_df.empty:
        st.info("Your portfolio is currently empty. Go to 'Add Trade' to log your first transaction!")
        return

    # --- WACC & Net Holdings Calculation Engine ---
    # Ensure datatypes for math
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])

    # Separate Buys and Sells
    buys = port_df[port_df['transaction_type'].str.upper() == 'BUY']
    sells = port_df[port_df['transaction_type'].str.upper() == 'SELL']

    # Group Buys to calculate Total Buy Qty and WACC
    if not buys.empty:
        buy_grouped = buys.groupby('symbol').apply(
            lambda x: pd.Series({
                'total_buy_qty': x['qty'].sum(),
                'total_buy_cost': (x['qty'] * x['price']).sum()
            })
        ).reset_index()
        buy_grouped['wacc'] = buy_grouped['total_buy_cost'] / buy_grouped['total_buy_qty']
    else:
        buy_grouped = pd.DataFrame(columns=['symbol', 'total_buy_qty', 'total_buy_cost', 'wacc'])

    # Group Sells to calculate Total Sell Qty
    if not sells.empty:
        sell_grouped = sells.groupby('symbol').apply(
            lambda x: pd.Series({
                'total_sell_qty': x['qty'].sum()
            })
        ).reset_index()
    else:
        sell_grouped = pd.DataFrame(columns=['symbol', 'total_sell_qty'])

    # Merge Buys and Sells to find Net Qty
    holdings = pd.merge(buy_grouped, sell_grouped, on='symbol', how='left').fillna(0)
    holdings['net_qty'] = holdings['total_buy_qty'] - holdings['total_sell_qty']

    # Filter out stocks that have been completely sold (Net Qty <= 0)
    active_holdings = holdings[holdings['net_qty'] > 0].copy()

    if active_holdings.empty:
        st.info("You have sold all your active holdings. Check the 'History' tab for realized P/L.")
        return

    # --- Merge with Live Market Data ---
    if not cache_df.empty and 'ltp' in cache_df.columns:
        active_holdings = pd.merge(active_holdings, cache_df[['symbol', 'ltp', 'change']], on='symbol', how='left').fillna(0)
    else:
        active_holdings['ltp'] = active_holdings['wacc'] # Fallback if no market data
        active_holdings['change'] = 0

    # --- Calculate Financials ---
    active_holdings['total_invested'] = active_holdings['net_qty'] * active_holdings['wacc']
    active_holdings['current_value'] = active_holdings['net_qty'] * active_holdings['ltp']
    active_holdings['unrealized_pl'] = active_holdings['current_value'] - active_holdings['total_invested']
    active_holdings['return_pct'] = (active_holdings['unrealized_pl'] / active_holdings['total_invested']) * 100

    # ==========================================
    # 2. PORTFOLIO SUMMARY METRICS
    # ==========================================
    st.markdown("### 📈 Portfolio Summary")
    
    total_invested = active_holdings['total_invested'].sum()
    total_value = active_holdings['current_value'].sum()
    total_pl = active_holdings['unrealized_pl'].sum()
    total_return_pct = (total_pl / total_invested) * 100 if total_invested > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invested (WACC)", f"Rs {total_invested:,.2f}")
    c2.metric("Current Market Value", f"Rs {total_value:,.2f}")
    
    # Color code P/L
    pl_color = "normal" if total_pl >= 0 else "inverse"
    c3.metric("Unrealized P/L", f"Rs {total_pl:,.2f}", delta=f"{total_return_pct:.2f}%", delta_color=pl_color)
    
    active_tickers = len(active_holdings)
    c4.metric("Active Positions", f"{active_tickers} Stocks")

    st.divider()

    # ==========================================
    # 3. VISUALIZATIONS & DETAILED TABLE
    # ==========================================
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("#### Asset Allocation")
        # Pie chart showing how the portfolio is distributed
        fig = px.pie(active_holdings, values='current_value', names='symbol', hole=0.4)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=350, showlegend=False)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### 📋 Detailed Holdings")
        
        # Prepare table for display
        display_df = active_holdings[['symbol', 'net_qty', 'wacc', 'ltp', 'total_invested', 'current_value', 'unrealized_pl', 'return_pct']].copy()
        display_df.rename(columns={
            'symbol': 'Symbol',
            'net_qty': 'Qty',
            'wacc': 'WACC (Rs)',
            'ltp': 'LTP (Rs)',
            'total_invested': 'Invested (Rs)',
            'current_value': 'Value (Rs)',
            'unrealized_pl': 'P/L (Rs)',
            'return_pct': 'Return %'
        }, inplace=True)

        # Apply Streamlit's native dataframe formatting for beautiful UI
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "WACC (Rs)": st.column_config.NumberColumn(format="%.2f"),
                "LTP (Rs)": st.column_config.NumberColumn(format="%.2f"),
                "Invested (Rs)": st.column_config.NumberColumn(format="%.2f"),
                "Value (Rs)": st.column_config.NumberColumn(format="%.2f"),
                "P/L (Rs)": st.column_config.NumberColumn(format="%.2f"),
                "Return %": st.column_config.NumberColumn(format="%.2f %%"),
            }
        )

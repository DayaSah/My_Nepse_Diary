import streamlit as st
import pandas as pd

def render(role):
    st.subheader("🚑 Loss Recovery & Breakeven targets")
    st.write("Calculates the exact percentage a stock needs to rise just to recover your current unrealized losses.")

    conn = st.connection("neon", type="sql")
    try:
        port_df = conn.query("SELECT * FROM portfolio")
        cache_df = conn.query("SELECT * FROM cache")
    except:
        return

    # [Same holding calculation logic for brevity]
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])
    buys = port_df[port_df['transaction_type'] == 'BUY']
    sells = port_df[port_df['transaction_type'] == 'SELL'].groupby('symbol')['qty'].sum().reset_index()
    sells.rename(columns={'qty': 'sold_qty'}, inplace=True)
    holdings = buys.groupby('symbol').apply(lambda x: pd.Series({'total_qty': x['qty'].sum(), 'total_cost': (x['qty'] * x['price']).sum()})).reset_index()
    holdings = pd.merge(holdings, sells, on='symbol', how='left').fillna(0)
    holdings['net_qty'] = holdings['total_qty'] - holdings['sold_qty']
    active_holdings = holdings[holdings['net_qty'] > 0].copy()
    active_holdings['wacc'] = active_holdings['total_cost'] / active_holdings['total_qty']

    if active_holdings.empty or cache_df.empty:
        st.info("Insufficient data to calculate recoveries. Ensure you have active holdings and a synced market cache.")
        return

    # Merge with Live Data
    recovery_df = pd.merge(active_holdings, cache_df[['symbol', 'ltp']], on='symbol', how='inner')
    
    # Filter for stocks currently AT A LOSS
    loss_df = recovery_df[recovery_df['ltp'] < recovery_df['wacc']].copy()
    
    if loss_df.empty:
        st.success("🎉 Congratulations! None of your active holdings are currently at a loss.")
        st.balloons()
        return

    # Calculate Recovery Math
    loss_df['current_drop_pct'] = ((loss_df['wacc'] - loss_df['ltp']) / loss_df['wacc']) * 100
    loss_df['recovery_needed_pct'] = ((loss_df['wacc'] - loss_df['ltp']) / loss_df['ltp']) * 100
    
    # Formatting for display
    display_df = loss_df[['symbol', 'net_qty', 'wacc', 'ltp', 'current_drop_pct', 'recovery_needed_pct']].copy()
    display_df.rename(columns={
        'symbol': 'Stock', 'net_qty': 'Units', 'wacc': 'Your Cost (WACC)', 
        'ltp': 'Current LTP', 'current_drop_pct': 'Current Loss %', 
        'recovery_needed_pct': 'Gain Needed to Break Even %'
    }, inplace=True)

    st.warning(f"You currently have {len(loss_df)} positions sitting in a loss. Here is what is required to recover:")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Your Cost (WACC)": st.column_config.NumberColumn(format="Rs %.2f"),
            "Current LTP": st.column_config.NumberColumn(format="Rs %.2f"),
            "Current Loss %": st.column_config.NumberColumn(format="%.2f%%"),
            "Gain Needed to Break Even %": st.column_config.NumberColumn(format="%.2f%%"),
        }
    )
    st.caption("💡 *Notice how the 'Gain Needed' is always mathematically higher than the 'Current Loss'. For example, a 50% drop requires a 100% gain to recover.*")

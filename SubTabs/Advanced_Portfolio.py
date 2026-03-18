import streamlit as st
import pandas as pd
import plotly.express as px

def render_advanced_view():
    st.title("🚀 Advanced Portfolio Analytics")
    st.caption("Detailed Performance, Realized Profits, and Risk Metrics.")
    
    conn = st.connection("neon", type="sql")
    
    # Fetch Data
    df = conn.query("SELECT * FROM portfolio", ttl=0)
    df.columns = [c.lower() for c in df.columns]
    cache = conn.query("SELECT * FROM cache", ttl=600)
    
    # --- 1. REALIZED P/L ENGINE ---
    buys = df[df['transaction_type'] == 'BUY']
    sells = df[df['transaction_type'] == 'SELL']
    
    # Calculate WACC for every symbol ever bought
    wacc_db = buys.groupby('symbol').apply(lambda x: (x['qty']*x['price']).sum() / x['qty'].sum()).to_dict()
    
    # Realized P/L Calculation
    realized_df = sells.copy()
    realized_df['buy_cost_basis'] = realized_df['symbol'].map(wacc_db)
    realized_df['profit_amt'] = (realized_df['price'] - realized_df['buy_cost_basis']) * realized_df['qty']
    # Deduct approx 0.5% fees
    realized_df['net_realized'] = realized_df['profit_amt'] - (realized_df['price'] * realized_df['qty'] * 0.005)
    
    total_realized_cash = realized_df['net_realized'].sum()

    # --- 2. FRICTION COSTS (FEES) ---
    total_volume = (df['qty'] * df['price']).sum()
    total_fees_paid = total_volume * 0.005 # Total estimated broker/sebon/dp fees

    # --- 3. PERFORMANCE STATS ---
    total_trades = len(sells)
    winning_trades = len(realized_df[realized_df['net_realized'] > 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    # --- UI: MACRO METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Realized P/L (Cash)", f"Rs {total_realized_cash:,.2f}")
    m2.metric("Win Rate", f"{win_rate:.1f}%")
    m3.metric("Total Fees Paid", f"Rs {total_fees_paid:,.2f}", delta="Friction Cost", delta_color="inverse")
    
    avg_profit = total_realized_cash / total_trades if total_trades > 0 else 0
    m4.metric("Avg Profit/Trade", f"Rs {avg_profit:,.0f}")

    st.divider()

    # --- UI: CHARTS ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Profit Distribution")
        if not realized_df.empty:
            fig = px.bar(realized_df, x='symbol', y='net_realized', color='net_realized',
                         color_continuous_scale='RdYlGn', title="Cash Booked per Stock")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sell history to show charts.")

    with col2:
        st.subheader("🛡️ Tax & Risk Projection")
        # Projection of CGT on current profits
        # (Assuming current unrealized profit is passed or recalculated)
        st.info("💡 **Pro Tip:** Your win rate is based on closed trades. Focus on increasing your 'Avg Profit per Trade' to cover friction costs.")
        
    # --- 4. REALIZED HISTORY TABLE ---
    st.subheader("📜 Realized (Closed) Trades History")
    st.dataframe(
        realized_df[['date', 'symbol', 'qty', 'price', 'buy_cost_basis', 'net_realized']],
        use_container_width=True, hide_index=True,
        column_config={
            "buy_cost_basis": "Buy WACC",
            "net_realized": st.column_config.NumberColumn("Net Profit (After Fees)", format="Rs %.2f")
        }
    )

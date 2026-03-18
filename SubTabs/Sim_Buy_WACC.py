import streamlit as st
import pandas as pd
from sqlalchemy import text

def render(role):
    st.subheader("WACC Averaging Simulator")
    st.write("Calculate your new average cost before you buy more shares.")

    conn = st.connection("neon", type="sql")
    
    # Fetch Portfolio
    try:
        port_df = conn.query("SELECT * FROM portfolio", ttl=0)
        cache_df = conn.query("SELECT * FROM cache", ttl=3600)
    except:
        st.error("Failed to fetch database.")
        return

    if port_df.empty:
        st.info("Your portfolio is empty. Add transactions first.")
        return

    # Calculate current holdings and WACC
    port_df['qty'] = pd.to_numeric(port_df['qty'])
    port_df['price'] = pd.to_numeric(port_df['price'])
    
    buys = port_df[port_df['transaction_type'] == 'BUY']
    sells = port_df[port_df['transaction_type'] == 'SELL'].groupby('symbol')['qty'].sum().reset_index()
    sells.rename(columns={'qty': 'sold_qty'}, inplace=True)
    
    holdings = buys.groupby('symbol').apply(lambda x: pd.Series({
        'total_qty': x['qty'].sum(), 
        'total_cost': (x['qty'] * x['price']).sum()
    })).reset_index()
    
    holdings = pd.merge(holdings, sells, on='symbol', how='left').fillna(0)
    holdings['net_qty'] = holdings['total_qty'] - holdings['sold_qty']
    holdings = holdings[holdings['net_qty'] > 0]
    holdings['wacc'] = holdings['total_cost'] / holdings['total_qty']

    if holdings.empty:
        st.info("No active holdings found.")
        return

    # UI Controls
    col1, col2 = st.columns([1, 2])
    
    with col1:
        selected_stock = st.selectbox("Select Active Holding", holdings['symbol'].tolist())
        stock_data = holdings[holdings['symbol'] == selected_stock].iloc[0]
        
        ltp = 0.0
        if not cache_df.empty and selected_stock in cache_df['symbol'].values:
            ltp = cache_df[cache_df['symbol'] == selected_stock]['ltp'].values[0]

        st.info(f"**Current Status:**\n\nUnits: {stock_data['net_qty']:,.0f}\nWACC: Rs {stock_data['wacc']:,.2f}\nLTP: Rs {ltp:,.2f}")

    with col2:
        with st.form("wacc_sim_form"):
            sim_qty = st.number_input("How many NEW shares do you want to buy?", min_value=10, step=10, value=100)
            sim_price = st.number_input("At what price? (Rs)", min_value=1.0, step=1.0, value=float(ltp) if ltp > 0 else float(stock_data['wacc']))
            
            submitted = st.form_submit_button("Simulate Buy", type="primary")

            if submitted:
                current_value = stock_data['net_qty'] * stock_data['wacc']
                new_investment = sim_qty * sim_price
                
                final_qty = stock_data['net_qty'] + sim_qty
                final_wacc = (current_value + new_investment) / final_qty
                
                st.divider()
                st.markdown("### Simulation Results")
                c1, c2, c3 = st.columns(3)
                c1.metric("New Total Quantity", f"{final_qty:,.0f} units", f"+{sim_qty} units")
                
                wacc_diff = final_wacc - stock_data['wacc']
                c2.metric("New WACC", f"Rs {final_wacc:,.2f}", f"{wacc_diff:,.2f} Rs", delta_color="inverse")
                
                c3.metric("Capital Required", f"Rs {new_investment:,.2f}")

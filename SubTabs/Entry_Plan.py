import streamlit as st
import pandas as pd

def render_entry_plan():
    st.subheader("🎯 Trade Entry Planner")
    st.write("Plan your entry, targets, and exits with full fee calculations.")

    with st.form("entry_plan_form"):
        # --- Input Section ---
        c1, c2 = st.columns(2)
        with c1:
            symbol = st.text_input("Stock Symbol (Optional)", placeholder="e.g., NICA")
            entry_price = st.number_input("Entry Price (Rs)", min_value=1.0, value=500.0)
            qty = st.number_input("Quantity", min_value=1, value=100)
            cgt_rate = 7.5  # As requested

        with c2:
            st.caption("Profit Targets")
            t1 = st.number_input("Target 1", value=entry_price * 1.10)
            t2 = st.number_input("Target 2", value=entry_price * 1.20)
            
            st.caption("Risk Management")
            sl1 = st.number_input("Stop Loss 1", value=entry_price * 0.95)
            sl2 = st.number_input("Stop Loss 2", value=entry_price * 0.90)

        submit = st.form_submit_button("Calculate Risk/Reward", type="primary")

    if submit:
        # --- Helper Function for NEPSE Fees ---
        def calc_net(price, quantity, is_buy, wacc=0):
            amt = price * quantity
            # Standard Nepalese Charges
            broker_fee = amt * 0.004  # Avg
            sebon_fee = amt * 0.00015
            dp_fee = 25.0
            
            if is_buy:
                return amt + broker_fee + sebon_fee + dp_fee
            else:
                gross_profit = amt - (wacc * quantity)
                cgt = max(0, gross_profit * (cgt_rate / 100))
                return amt - broker_fee - sebon_fee - dp_fee - cgt

        # Calculations
        total_investment = calc_net(entry_price, qty, is_buy=True)
        effective_wacc = total_investment / qty

        # Outcome Logic
        outcomes = [
            {"label": "Target 1", "price": t1, "color": "normal"},
            {"label": "Target 2", "price": t2, "color": "normal"},
            {"label": "Stop Loss 1", "price": sl1, "color": "inverse"},
            {"label": "Stop Loss 2", "price": sl2, "color": "inverse"},
        ]

        # --- Display Results ---
        st.info(f"**Total Capital Required:** Rs {total_investment:,.2f} | **Effective WACC:** Rs {effective_wacc:,.2f}")
        
        cols = st.columns(4)
        for i, opt in enumerate(outcomes):
            net_payout = calc_net(opt['price'], qty, is_buy=False, wacc=effective_wacc)
            net_profit = net_payout - total_investment
            roi = (net_profit / total_investment) * 100
            rr_ratio = abs(net_profit / ( (sl1 * qty) - total_investment )) if i < 2 else 0
            
            with cols[i]:
                st.metric(opt['label'], f"Rs {net_profit:,.2f}", f"{roi:.2f}%", delta_color=opt['color'])
                if i < 2: st.caption(f"RR Ratio: 1:{rr_ratio:.2f}")

        with st.expander("📊 Essential Data for this Trade"):
            st.write(f"- **Break-even Price:** Rs {total_investment / qty:,.2f} (You need this price just to cover fees)")
            st.write(f"- **Total Fees (Buy + Sell):** Rs {(total_investment - (entry_price*qty)) + ( (opt['price']*qty) - net_payout):,.2f}")

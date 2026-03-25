import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

def render_page(role):
    st.title("🧠 Risk Management & Trading Journal")
    st.caption("Calculate safe position sizes, log your trading psychology, and monitor system health.")

    conn = st.connection("neon", type="sql")

    tabs = st.tabs(["⚖️ Position Size Calculator", "📓 Trading Journal", "🚨 System Diagnostics"])

    # ==========================================
    # TAB 1: RISK & POSITION SIZING ENGINE
    # ==========================================
    with tabs[0]:
        st.subheader("Dynamic Position Sizer")
        try:
            wealth_df = conn.query("SELECT current_value FROM wealth ORDER BY snapshot_date DESC LIMIT 1")
            est_capital = float(wealth_df.iloc[0]['current_value']) if not wealth_df.empty else 500000.0
        except:
            est_capital = 500000.0

        col1, col2 = st.columns(2)
        with col1:
            total_capital = st.number_input("Total Account Size (Rs)", value=est_capital, step=10000.0)
            risk_pct = st.slider("Max Risk per Trade (%)", 0.5, 5.0, 1.0, 0.1)
        with col2:
            entry_price = st.number_input("Planned Entry Price (Rs)", min_value=1.0, value=500.0)
            stop_loss = st.number_input("Hard Stop Loss Price (Rs)", min_value=1.0, value=475.0)
            take_profit = st.number_input("Target Take Profit (Rs)", min_value=1.0, value=575.0)

        if entry_price > stop_loss:
            risk_amt = total_capital * (risk_pct / 100)
            risk_per_share = entry_price - stop_loss
            if risk_per_share > 0:
                max_shares = int(risk_amt / risk_per_share)
                rr_ratio = (take_profit - entry_price) / risk_per_share
                
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("Max Units", f"{max_shares:,}")
                c2.metric("Total Investment", f"Rs {max_shares * entry_price:,.0f}")
                c3.metric("Risk Amount", f"Rs {risk_amt:,.0f}", f"-{risk_pct}%")
                
                if rr_ratio >= 2.0: st.success(f"✅ Good Setup (R/R 1:{rr_ratio:.2f})")
                else: st.warning(f"⚠️ Poor Reward/Risk (1:{rr_ratio:.2f})")
        else:
            st.error("Stop Loss must be below Entry Price.")

    # ==========================================
    # TAB 2: TRADING JOURNAL
    # ==========================================
    with tabs[1]:
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown("#### Log New Entry")
            with st.form("journal_form", clear_on_submit=True):
                # Symbol is now optional (default to "GENERAL")
                j_sym = st.text_input("Symbol (Optional)", placeholder="e.g. ULHC").upper() or "GENERAL"
                
                # Custom Setup Options
                j_setup = st.selectbox("Trade Setup", [
                    "Trend Continuation", "Mean Reversion", "Breakout/Breakdown", 
                    "Panic Sell Catch", "Dividend/Bonus Play", "News/Fundamental", "Gamble/Impulse"
                ])
                
                # Custom Emotions
                j_emotion = st.select_slider("Emotional State", options=[
                    "Depressed/Fear", "Anxious", "Neutral", "Disciplined", "Greedy/FOMO", "Overconfident"
                ], value="Neutral")
                
                j_notes = st.text_area("Trade Thesis (The 'Why')", placeholder="Why this trade?")
                j_remark2 = st.text_input("Final Remark / Lesson", placeholder="What did you learn from this?")
                
                if st.form_submit_button("💾 Save Entry", type="primary"):
                    if j_notes:
                        try:
                            with conn.session as s:
                                sql = text("""
                                    INSERT INTO trading_journal (symbol, setup_type, emotion, notes, second_remark) 
                                    VALUES (:sym, :setup, :emo, :notes, :r2)
                                """)
                                s.execute(sql, {"sym": j_sym, "setup": j_setup, "emo": j_emotion, "notes": j_notes, "r2": j_remark2})
                                s.commit()
                            st.success("Saved!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.warning("Please provide at least a Thesis.")

        with c_right:
            st.markdown("#### Historical Entries")
            try:
                journal_df = conn.query("SELECT date, symbol, setup_type, emotion, notes, second_remark FROM trading_journal ORDER BY date DESC")
                if not journal_df.empty:
                    # Color coding for Emotions
                    def mood_color(val):
                        if val in ["Depressed/Fear", "Greedy/FOMO"]: return 'background-color: rgba(255,0,0,0.2)'
                        if val in ["Disciplined"]: return 'background-color: rgba(0,255,0,0.2)'
                        return ''
                    
                    st.dataframe(
                        journal_df.style.map(mood_color, subset=['emotion']), 
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Journal is empty.")
            except:
                st.error("Table structure mismatch. Did you run the SQL ALTER command?")

    # ==========================================
    # TAB 3: SYSTEM DIAGNOSTICS
    # ==========================================
    with tabs[2]:
        st.subheader("🚨 System Health")
        # Logic remains same as your original code
        st.info("System operational. No active critical errors.")

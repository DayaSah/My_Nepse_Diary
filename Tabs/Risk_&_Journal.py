import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

def render_page(role):
    st.title("🧠 Risk Management & Trading Journal")
    st.caption("Calculate safe position sizes, log your trading psychology, and monitor system health.")

    conn = st.connection("neon", type="sql")

    # ==========================================
    # 0. UI TABS SETUP
    # ==========================================
    tabs = st.tabs(["⚖️ Position Size Calculator", "📓 Trading Journal", "🚨 System Diagnostics"])

    # ==========================================
    # TAB 1: RISK & POSITION SIZING ENGINE
    # ==========================================
    with tabs[0]:
        st.subheader("Dynamic Position Sizer")
        st.write("Never risk more than a set percentage of your total portfolio on a single trade.")

        # Try to fetch actual portfolio value for dynamic math
        try:
            wealth_df = conn.query("SELECT current_value FROM wealth ORDER BY snapshot_date DESC LIMIT 1")
            est_capital = float(wealth_df.iloc[0]['current_value']) if not wealth_df.empty else 500000.0
        except:
            est_capital = 500000.0

        col1, col2 = st.columns(2)
        
        with col1:
            total_capital = st.number_input("Total Account Size (Rs)", value=est_capital, step=10000.0)
            risk_pct = st.slider("Max Risk per Trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.1, help="Professional traders usually risk 1% to 2% per trade.")
            
        with col2:
            entry_price = st.number_input("Planned Entry Price (Rs)", min_value=1.0, value=500.0)
            stop_loss = st.number_input("Hard Stop Loss Price (Rs)", min_value=1.0, value=475.0)
            take_profit = st.number_input("Target Take Profit (Rs)", min_value=1.0, value=575.0)

        # Calculations
        if entry_price > stop_loss:
            risk_amount_rs = total_capital * (risk_pct / 100)
            risk_per_share = entry_price - stop_loss
            
            if risk_per_share > 0:
                max_shares = int(risk_amount_rs / risk_per_share)
                total_investment = max_shares * entry_price
                
                reward_per_share = take_profit - entry_price
                potential_profit = max_shares * reward_per_share
                rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0

                st.divider()
                st.markdown("### 🎯 Trade Blueprint")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Max Shares to Buy", f"{max_shares:,} Units")
                c2.metric("Total Capital Required", f"Rs {total_investment:,.2f}")
                c3.metric("Capital at Risk", f"Rs {risk_amount_rs:,.2f}", f"-{risk_pct}% of Acct", delta_color="inverse")
                
                st.markdown(f"**Risk/Reward Ratio:** 1 : {rr_ratio:.2f}")
                if rr_ratio >= 2.0:
                    st.success("✅ Good Setup: Your potential reward is at least twice your risk.")
                else:
                    st.warning("⚠️ Poor Setup: You are risking too much for too little reward (Aim for at least 1:2 R/R).")
        else:
            st.error("Stop Loss must be lower than the Entry Price for a long position.")

    # ==========================================
    # TAB 2: TRADING JOURNAL
    # ==========================================
    with tabs[1]:
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown("#### Log New Trade")
            with st.form("journal_form", clear_on_submit=True):
                j_sym = st.text_input("Symbol", placeholder="e.g. NABIL").upper()
                j_setup = st.selectbox("Trade Setup", ["Breakout", "Pullback Support", "Moving Average Bounce", "Dividend Capture", "News Catalyst", "Other"])
                j_emotion = st.select_slider("Emotional State", options=["Revenge/Angry", "FOMO", "Anxious", "Neutral", "Confident", "Systematic"])
                j_notes = st.text_area("Trade Thesis & Notes", placeholder="Why are you taking this trade? What is the invalidation point?")
                
                if st.form_submit_button("💾 Save Journal Entry", type="primary"):
                    if j_sym and j_notes:
                        try:
                            with conn.session as s:
                                sql = text("""
                                    INSERT INTO trading_journal (symbol, setup_type, emotion, notes) 
                                    VALUES (:sym, :setup, :emo, :notes)
                                """)
                                s.execute(sql, {"sym": j_sym, "setup": j_setup, "emo": j_emotion, "notes": j_notes})
                                s.commit()
                            st.success("Journal entry saved!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                    else:
                        st.warning("Please fill in the symbol and notes.")

        with c_right:
            st.markdown("#### Historical Entries")
            try:
                journal_df = conn.query("SELECT date, symbol, setup_type, emotion, notes, result, pnl FROM trading_journal ORDER BY date DESC")
                if not journal_df.empty:
                    journal_df['date'] = pd.to_datetime(journal_df['date']).dt.strftime('%Y-%m-%d %I:%M %p')
                    
                    # Add color coding for emotions
                    def mood_color(val):
                        if val in ['FOMO', 'Revenge/Angry']: return 'color: red'
                        elif val in ['Confident', 'Systematic']: return 'color: green'
                        return ''
                        
                    st.dataframe(
                        journal_df.style.map(mood_color, subset=['emotion']), 
                        use_container_width=True, 
                        hide_index=True,
                        height=400
                    )
                else:
                    st.info("Your journal is empty. Log your first trade on the left.")
            except Exception as e:
                st.error("Could not load journal table.")

    # ==========================================
    # TAB 3: SYSTEM DIAGNOSTICS & LOGS
    # ==========================================
    with tabs[2]:
        st.subheader("🚨 System Error Logs")
        st.caption("Background failures, API disconnects, and sync errors will appear here.")
        
        # Only Admins should ideally see system errors, but we will show it safely
        try:
            # Query the audit_log specifically for SYSTEM_ERROR
            error_df = conn.query("SELECT timestamp, details FROM audit_log WHERE action = 'SYSTEM_ERROR' ORDER BY timestamp DESC LIMIT 50")
        except Exception as e:
            error_df = pd.DataFrame()
            
        if error_df.empty:
            st.success("✅ All Systems Operational. No errors recorded.")
            st.balloons()
        else:
            # Convert Timezone to Nepal Time safely
            error_df['timestamp'] = pd.to_datetime(error_df['timestamp'])
            if error_df['timestamp'].dt.tz is None:
                error_df['nepal_time'] = error_df['timestamp'] + pd.Timedelta(hours=5, minutes=45)
            else:
                error_df['nepal_time'] = error_df['timestamp'].dt.tz_convert('Asia/Kathmandu')
                
            error_df['Time (NST)'] = error_df['nepal_time'].dt.strftime('%Y-%m-%d %I:%M:%S %p')
            
            st.warning(f"Found {len(error_df)} system warnings/errors.")
            st.dataframe(
                error_df[['Time (NST)', 'details']].rename(columns={'details': 'Error Message'}), 
                use_container_width=True, 
                hide_index=True
            )
            
            if st.button("🗑️ Clear Error Logs"):
                try:
                    with conn.session as s:
                        s.execute(text("DELETE FROM audit_log WHERE action = 'SYSTEM_ERROR'"))
                        s.commit()
                    st.success("Logs cleared!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to clear logs: {e}")

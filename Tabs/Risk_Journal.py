import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

def render_page(role):
    st.title("🧠 Risk & Psychology Journal")
    st.caption("Manage your risk, log your mindset, and monitor system health.")

    conn = st.connection("neon", type="sql")

    # TABS SETUP
    tabs = st.tabs(["⚖️ Position Sizer", "📓 Trading Journal", "🚨 System Diagnostics"])

    # ==========================================
    # TAB 1: POSITION SIZE CALCULATOR
    # ==========================================
    with tabs[0]:
        st.subheader("Position Sizing Engine")
        try:
            wealth_df = conn.query("SELECT current_value FROM wealth ORDER BY snapshot_date DESC LIMIT 1")
            est_capital = float(wealth_df.iloc[0]['current_value']) if not wealth_df.empty else 500000.0
        except:
            est_capital = 500000.0

        col1, col2 = st.columns(2)
        with col1:
            total_cap = st.number_input("Account Size (Rs)", value=est_capital, step=5000.0)
            risk_pct = st.slider("Risk per Trade (%)", 0.5, 5.0, 1.0, 0.1)
        with col2:
            entry = st.number_input("Entry Price", min_value=1.0, value=500.0)
            sl = st.number_input("Stop Loss", min_value=1.0, value=475.0)
            tp = st.number_input("Take Profit", min_value=1.0, value=575.0)

        if entry > sl:
            risk_rs = total_cap * (risk_pct / 100)
            risk_per_share = entry - sl
            units = int(risk_rs / risk_per_share)
            rr = (tp - entry) / risk_per_share
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Units to Buy", f"{units:,}")
            c2.metric("Total Investment", f"Rs {units * entry:,.0f}")
            c3.metric("Max Loss", f"Rs {risk_rs:,.0f}", f"-{risk_pct}%")
            
            if rr >= 2.0: st.success(f"✅ R/R Ratio: 1:{rr:.2f}")
            else: st.warning(f"⚠️ R/R Ratio: 1:{rr:.2f} (Target 1:2)")
        else:
            st.error("Stop Loss must be below Entry.")

    # ==========================================
    # TAB 2: MODIFIED TRADING JOURNAL
    # ==========================================
    with tabs[1]:
        c_form, c_view = st.columns([1, 2])
        
        with c_form:
            st.markdown("#### 🖊️ New Journal Entry")
            with st.form("journal_form", clear_on_submit=True):
                j_sym = st.text_input("Symbol (Optional)", placeholder="e.g. NHPC").upper() or "GENERAL"
                j_topic = st.text_input("Topic", placeholder="e.g. Mid-Day Reversal")
                
                j_feeling = st.selectbox("Feeling / Mindset", [
                    "Systematic", "Disciplined", "Neutral", "Anxious", "FOMO", "Revenge Trading", "Overconfident"
                ])
                
                j_star = st.slider("Star Rating (Setup Quality)", 1, 10, 5)
                
                j_thesis = st.text_area("Trade Thesis (Long Text)", placeholder="Logic behind the trade...")
                j_remark = st.text_area("Final Remark (Lessons)", placeholder="Outcome or lessons learned...")
                
                if st.form_submit_button("💾 Save to Database", type="primary"):
                    if j_topic and j_thesis:
                        try:
                            with conn.session as s:
                                sql = text("""
                                    INSERT INTO trading_journal (symbol, topic, feeling, star, trade_thesis, final_remark) 
                                    VALUES (:sym, :top, :feel, :star, :thes, :rem)
                                """)
                                s.execute(sql, {
                                    "sym": j_sym, "top": j_topic, "feel": j_feeling, 
                                    "star": j_star, "thes": j_thesis, "rem": j_remark
                                })
                                s.commit()
                            st.success("Entry Saved!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"DB Error: {e}")
                    else:
                        st.warning("Please fill in 'Topic' and 'Thesis'.")

        with c_view:
            st.markdown("#### 📜 Historical Logs")
            try:
                # Fetching the newly structured data
                df = conn.query("SELECT date_time_stamp, symbol, topic, feeling, star, trade_thesis, final_remark FROM trading_journal ORDER BY date_time_stamp DESC")
                if not df.empty:
                    # Styling Star Rating
                    def style_stars(val):
                        if val >= 8: return 'background-color: rgba(0,255,0,0.2); font-weight: bold;'
                        if val <= 3: return 'background-color: rgba(255,0,0,0.2); font-weight: bold;'
                        return ''
                    
                    st.dataframe(
                        df.style.map(style_stars, subset=['star']),
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.info("Journal is empty.")
            except:
                st.error("Table mismatch. Please run the SQL script provided.")

    # ==========================================
    # TAB 3: SYSTEM DIAGNOSTICS (RESTORED)
    # ==========================================
    with tabs[2]:
        st.subheader("🚨 System Logs & Diagnostics")
        st.caption("Monitoring background errors and database sync status.")
        
        try:
            # Querying the audit_log table for system failures
            error_df = conn.query("SELECT timestamp, details FROM audit_log WHERE action = 'SYSTEM_ERROR' ORDER BY timestamp DESC LIMIT 50")
            
            if error_df.empty:
                st.success("✅ All Systems Normal. No errors found.")
                if st.button("Simulate System Check"):
                    st.balloons()
            else:
                # Convert to Nepal Time
                error_df['timestamp'] = pd.to_datetime(error_df['timestamp'])
                error_df['Nepal Time'] = (error_df['timestamp'] + pd.Timedelta(hours=5, minutes=45)).dt.strftime('%Y-%m-%d %H:%M')
                
                st.warning(f"Critical Events Detected: {len(error_df)}")
                st.dataframe(
                    error_df[['Nepal Time', 'details']].rename(columns={'details': 'Log Message'}), 
                    use_container_width=True, 
                    hide_index=True
                )
                
                if st.button("🗑️ Clear System Logs"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM audit_log WHERE action = 'SYSTEM_ERROR'"))
                        s.commit()
                    st.rerun()
        except:
            st.info("Log table not accessible or empty.")

import streamlit as st
import pandas as pd
from sqlalchemy import text
import numpy as np

def render_page(role):
    st.set_page_config(layout="wide") # Use wide mode for better data visibility
    st.title("👀 NEPSE Command Center")
    st.caption("Live Radar, Entry/Exit Observers, and Portfolio Logic.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 0. SYSTEM LOGGING & DATA UTILITIES
    # ==========================================
    def log_system_error(error_msg):
        try:
            with conn.session as s:
                s.execute(text("INSERT INTO audit_log (action, details) VALUES ('DASHBOARD_ERROR', :msg)"), {"msg": str(error_msg)})
                s.commit()
        except: pass

    @st.cache_data(ttl=10) # Fast refresh for live data
    def get_data():
        try:
            wl = conn.query("SELECT * FROM watchlist", ttl=0)
            cache = conn.query("SELECT * FROM cache", ttl=0)
            wl.columns = [c.lower() for c in wl.columns]
            cache.columns = [c.lower() for c in cache.columns]
            return wl, cache
        except Exception as e:
            log_system_error(e)
            return pd.DataFrame(), pd.DataFrame()

    wl_df, cache_df = get_data()

    # ==========================================
    # 1. DATA PROCESSING (The "Brain")
    # ==========================================
    if not wl_df.empty and not cache_df.empty:
        # Merge Watchlist with Live Cache
        df = pd.merge(wl_df, cache_df[['symbol', 'ltp', 'change_percent', 'volume']], on='symbol', how='left')
        df['ltp'] = df['ltp'].fillna(0)

        # Logic for "Conditions Fulfilled" (The Observers)
        df['target_hit'] = (df['target_price'] > 0) & (df['ltp'] >= df['target_price'])
        df['hard_target_hit'] = (df['hard_target'] > 0) & (df['ltp'] >= df['hard_target'])
        df['sl_hit'] = (df['stop_loss'] > 0) & (df['ltp'] <= df['stop_loss'])
        df['hard_sl_hit'] = (df['hard_sl'] > 0) & (df['ltp'] <= df['hard_sl'])
        df['entry_1_hit'] = (df['entry_1'] > 0) & (df['ltp'] <= df['entry_1'])
        df['must_entry_hit'] = (df['entry_must'] > 0) & (df['ltp'] <= df['entry_must'])
    else:
        df = pd.DataFrame()

    # ==========================================
    # 2. DASHBOARD TABS
    # ==========================================
    tabs = st.tabs(["📡 Radar (Live View)", "🔎 Observers (Signals)", "🛠️ Management"])

    # --- TAB 1: RADAR (The Observation Place) ---
    with tabs[0]:
        if df.empty:
            st.info("No data available. Add symbols in the Management tab.")
        else:
            st.subheader("Market Observation Deck")
            
            # Metrics Overview
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Tracked", len(df))
            c2.metric("Entry Zones", df['entry_1_hit'].sum(), delta_color="normal")
            c3.metric("Exit Zones", (df['target_hit'] | df['sl_hit']).sum(), delta_color="inverse")

            # Main Radar Table
            radar_display = df[['symbol', 'ltp', 'change_percent', 'entry_1', 'entry_must', 'target_price', 'hard_target', 'stop_loss', 'hard_sl', 'notes']].copy()
            
            st.dataframe(
                radar_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "symbol": "Symbol",
                    "ltp": st.column_config.NumberColumn("LTP", format="Rs %.2f"),
                    "change_percent": st.column_config.NumberColumn("Change %", format="%.2f%%"),
                    "entry_1": "Entry 1",
                    "entry_must": "Must Entry",
                    "target_price": "Target",
                    "hard_target": "Hard Target",
                    "stop_loss": "SL",
                    "hard_sl": "Hard SL",
                    "notes": "Thesis"
                }
            )

    # --- TAB 2: OBSERVERS (Conditions Fulfilled) ---
    with tabs[1]:
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### 🛒 Entry Observer")
            entries = df[df['entry_1_hit'] | df['must_entry_hit']]
            if entries.empty:
                st.write("No symbols in entry zone.")
            for _, row in entries.iterrows():
                status = "🔥 MUST BUY" if row['must_entry_hit'] else "🛒 Entry 1"
                st.success(f"**{row['symbol']}**: {status} (LTP: {row['ltp']})")

        with col_right:
            st.markdown("### 🎯 SL & Target Observer")
            exits = df[df['target_hit'] | df['sl_hit'] | df['hard_target_hit'] | df['hard_sl_hit']]
            if exits.empty:
                st.write("No signals triggered.")
            for _, row in exits.iterrows():
                if row['hard_target_hit']: st.error(f"🚨 **{row['symbol']}**: HARD TARGET (LTP: {row['ltp']})")
                elif row['target_hit']: st.warning(f"🎯 **{row['symbol']}**: Target Reached (LTP: {row['ltp']})")
                if row['hard_sl_hit']: st.error(f"💀 **{row['symbol']}**: HARD STOP LOSS (LTP: {row['ltp']})")
                elif row['sl_hit']: st.warning(f"🛑 **{row['symbol']}**: SL Hit (LTP: {row['ltp']})")

    # --- TAB 3: MANAGEMENT (Editor) ---
    with tabs[2]:
        if role == "View Only":
            st.warning("🔒 Management is disabled in View Only mode.")
        else:
            # A. ADD/UPDATE FORM
            with st.expander("➕ Add or Update Symbol", expanded=True):
                with st.form("edit_form"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        sym = st.text_input("Symbol").upper().strip()
                        e1 = st.number_input("Entry 1", min_value=0.0)
                        em = st.number_input("Must Entry", min_value=0.0)
                    with c2:
                        tp = st.number_input("Target", min_value=0.0)
                        htp = st.number_input("Hard Target", min_value=0.0)
                    with c3:
                        sl = st.number_input("Stop Loss", min_value=0.0)
                        hsl = st.number_input("Hard SL", min_value=0.0)
                    
                    notes = st.text_area("Investment Notes")
                    if st.form_submit_button("Save to Watchlist", type="primary"):
                        if sym:
                            with conn.session as s:
                                s.execute(text("""
                                    INSERT INTO watchlist (symbol, target_price, stop_loss, hard_target, hard_sl, entry_1, entry_must, notes)
                                    VALUES (:s, :tp, :sl, :htp, :hsl, :e1, :em, :n)
                                    ON CONFLICT (symbol) DO UPDATE SET
                                        target_price=EXCLUDED.target_price, stop_loss=EXCLUDED.stop_loss,
                                        hard_target=EXCLUDED.hard_target, hard_sl=EXCLUDED.hard_sl,
                                        entry_1=EXCLUDED.entry_1, entry_must=EXCLUDED.entry_must, notes=EXCLUDED.notes
                                """), {"s":sym, "tp":tp, "sl":sl, "htp":htp, "hsl":hsl, "e1":e1, "em":em, "n":notes})
                                s.commit()
                            st.success(f"Updated {sym}")
                            st.rerun()

            # B. QUICK REMOVE
            st.markdown("### 🗑️ Remove from Watchlist")
            if not wl_df.empty:
                for _, row in wl_df.iterrows():
                    col_sym, col_btn = st.columns([4, 1])
                    col_sym.write(f"**{row['symbol']}**")
                    if col_btn.button("Delete", key=f"del_{row['symbol']}"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM watchlist WHERE symbol = :s"), {"s": row['symbol']})
                            s.commit()
                        st.rerun()

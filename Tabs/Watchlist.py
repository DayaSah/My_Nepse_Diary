import streamlit as st
import pandas as pd
from sqlalchemy import text

def render_page(role):
    st.title("👀 Market Watchlist")
    st.caption("Track potential trades, set price targets, and monitor stop-losses.")

    # Initialize Database Connection
    conn = st.connection("neon", type="sql")

    # ==========================================
    # 0. SYSTEM LOGGING UTILITY
    # ==========================================
    def log_system_error(error_msg):
        """Silently logs errors to the audit_log table so the app doesn't crash."""
        try:
            with conn.session as s:
                sql = text("INSERT INTO audit_log (action, details) VALUES ('SYSTEM_ERROR', :msg)")
                s.execute(sql, {"msg": str(error_msg)})
                s.commit()
        except:
            pass # If the logger fails, just fail silently

    # ==========================================
    # 1. FETCH AND PROCESS DATA
    # ==========================================
    try:
        wl_df = conn.query("SELECT * FROM watchlist ORDER BY added_date DESC")
        cache_df = conn.query("SELECT * FROM cache")
        
        # Standardize columns for Postgres
        wl_df.columns = [c.lower() for c in wl_df.columns]
        if not cache_df.empty:
            cache_df.columns = [c.lower() for c in cache_df.columns]
            
    except Exception as e:
        st.error("⚠️ Failed to load watchlist data. The engineering team has been notified.")
        log_system_error(f"Watchlist Load Error: {e}")
        wl_df = pd.DataFrame()
        cache_df = pd.DataFrame()

    # ==========================================
    # 2. UI TABS SETUP
    # ==========================================
    tabs = st.tabs(["📡 Radar (Live View)", "➕ Add to Watchlist", "🗑️ Manage"])

    # --- TAB 1: LIVE RADAR ---
    with tabs[0]:
        if wl_df.empty:
            st.info("Your watchlist is empty. Go to the next tab to add stocks.")
        else:
            # Merge with Live Market Data
            if not cache_df.empty and 'ltp' in cache_df.columns:
                radar_df = pd.merge(wl_df, cache_df[['symbol', 'ltp', 'change']], on='symbol', how='left').fillna(0)
            else:
                radar_df = wl_df.copy()
                radar_df['ltp'] = 0.0
                radar_df['change'] = 0.0

            # Calculate Distance to Targets
            radar_df['to_target_pct'] = radar_df.apply(
                lambda x: ((x['target_price'] - x['ltp']) / x['ltp'] * 100) if x['ltp'] > 0 and x['target_price'] > 0 else 0, axis=1
            )
            radar_df['to_stop_pct'] = radar_df.apply(
                lambda x: ((x['ltp'] - x['stop_loss']) / x['stop_loss'] * 100) if x['ltp'] > 0 and x['stop_loss'] > 0 else 0, axis=1
            )

            # Display formatting
            display_df = radar_df[['symbol', 'ltp', 'change', 'target_price', 'to_target_pct', 'stop_loss', 'to_stop_pct', 'notes']].copy()
            display_df.rename(columns={
                'symbol': 'Symbol',
                'ltp': 'Live Price',
                'change': 'Day Change',
                'target_price': 'Target (Rs)',
                'to_target_pct': 'Dist. to Target',
                'stop_loss': 'Stop Loss (Rs)',
                'to_stop_pct': 'Dist. to Stop',
                'notes': 'Investment Thesis'
            }, inplace=True)

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Live Price": st.column_config.NumberColumn(format="Rs %.2f"),
                    "Target (Rs)": st.column_config.NumberColumn(format="%.2f"),
                    "Stop Loss (Rs)": st.column_config.NumberColumn(format="%.2f"),
                    "Dist. to Target": st.column_config.ProgressColumn(
                        "Target Proximity", help="How close the stock is to your target price.", 
                        format="%.2f%%", min_value=0, max_value=20 # Max visual bar is 20% away
                    ),
                    "Dist. to Stop": st.column_config.NumberColumn(
                        format="%.2f%% buffer", help="Percentage buffer until Stop Loss is hit."
                    ),
                }
            )

    # --- TAB 2: ADD TO WATCHLIST ---
    with tabs[1]:
        if role == "View Only":
            st.warning("🔒 View Only mode: You cannot add to the watchlist.")
        else:
            with st.form("add_watchlist_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_sym = st.text_input("Stock Symbol", placeholder="e.g. NABIL").upper().strip()
                with col2:
                    new_target = st.number_input("Target Price (Rs)", min_value=0.0, format="%.2f")
                with col3:
                    new_stop = st.number_input("Stop Loss (Rs)", min_value=0.0, format="%.2f")
                
                new_notes = st.text_input("Notes / Investment Thesis", placeholder="Why are you watching this?")
                
                submitted = st.form_submit_button("📌 Add to Watchlist", type="primary")
                
                if submitted:
                    if not new_sym:
                        st.error("Symbol is required.")
                    else:
                        try:
                            with conn.session as s:
                                sql = text("""
                                    INSERT INTO watchlist (symbol, target_price, stop_loss, notes) 
                                    VALUES (:sym, :tgt, :sl, :notes)
                                    ON CONFLICT (symbol) DO UPDATE 
                                    SET target_price = EXCLUDED.target_price, 
                                        stop_loss = EXCLUDED.stop_loss, 
                                        notes = EXCLUDED.notes
                                """)
                                s.execute(sql, {"sym": new_sym, "tgt": new_target, "sl": new_stop, "notes": new_notes})
                                s.commit()
                                
                            # Log user action to Audit Log
                            with conn.session as s:
                                s.execute(text("INSERT INTO audit_log (action, symbol, details) VALUES ('WATCHLIST_ADD', :sym, 'Added/Updated Watchlist')"), {"sym": new_sym})
                                s.commit()
                                
                            st.success(f"✅ {new_sym} added to your watchlist!")
                            st.rerun()
                        except Exception as e:
                            st.error("Failed to add to watchlist.")
                            log_system_error(f"Watchlist Add Error ({new_sym}): {e}")

    # --- TAB 3: MANAGE / DELETE ---
    with tabs[2]:
        if role == "View Only":
            st.warning("🔒 View Only mode: You cannot modify the watchlist.")
        elif wl_df.empty:
            st.info("Nothing to manage.")
        else:
            st.write("Remove stocks from your watchlist below:")
            for idx, row in wl_df.iterrows():
                col_text, col_btn = st.columns([4, 1])
                with col_text:
                    st.write(f"**{row['symbol']}** — Target: {row['target_price']} | SL: {row['stop_loss']}")
                with col_btn:
                    if st.button("❌ Remove", key=f"del_{row['symbol']}"):
                        try:
                            with conn.session as s:
                                s.execute(text("DELETE FROM watchlist WHERE symbol = :sym"), {"sym": row['symbol']})
                                s.execute(text("INSERT INTO audit_log (action, symbol, details) VALUES ('WATCHLIST_REMOVE', :sym, 'Removed from Watchlist')"), {"sym": row['symbol']})
                                s.commit()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete {row['symbol']}.")
                            log_system_error(f"Watchlist Delete Error ({row['symbol']}): {e}")

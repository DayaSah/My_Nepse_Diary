import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
# This MUST be the first Streamlit command
st.set_page_config(
    page_title="NEPSE Terminal Pro",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. AUTHENTICATION SYSTEM
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None

def login():
    st.title("🔐 Login to NEPSE Terminal")
    st.markdown("Enter your credentials to access the system.")
    
    # Center the login box nicely
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", type="primary", use_container_width=True)
            
            if submit:
                # Update these credentials to your liking!
                if username == "admin" and password == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.role = "Admin"
                    st.rerun()
                elif username == "viewer" and password == "view123":
                    st.session_state.logged_in = True
                    st.session_state.role = "View Only"
                    st.rerun()
                else:
                    st.error("Invalid username or password")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.rerun()

# If not logged in, show login page and STOP the script here
if not st.session_state.logged_in:
    login()
    st.stop()

# ==========================================
# 3. DYNAMIC MODULE IMPORTS
# ==========================================
# We import these ONLY after successful login to save memory
try:
    from Tabs import Dashboard, Portfolio, Add_Transaction, My_TMS, Trade_Simulation
    from Tabs import Watchlist, Risk_Journal, History, Wealth_Graph, Nepse_Data_Analysis
    from Tabs import Manage_Data, Activity_Log
except ImportError as e:
    st.error(f"🚨 Initialization Error: {e}")
    st.info("Make sure all your files are correctly named inside the 'Tabs' folder.")
    st.stop()

# ==========================================
# 4. SIDEBAR & NAVIGATION MENU
# ==========================================
with st.sidebar:
    st.markdown("### 🦅 NEPSE Terminal Pro")
    
    # Status Indicator
    if st.session_state.role == "Admin":
        st.success(f"Logged in as: **{st.session_state.role}**")
    else:
        st.info(f"Logged in as: **{st.session_state.role}**")
        
    st.divider()
    
    # The New Attractive Menu
    menu_options = [
        "🏠 Dashboard Overview",
        "💼 Active Portfolio",
        "➕ Add Transaction",
        "🏦 My TMS (Cash & Margin)",
        "🧮 Trade Simulation",
        "🎯 Watchlist & Alerts",
        "🧠 Risk & Journal",
        "📜 Realized History",
        "📈 Wealth Trajectory",
        "🤖 AI Market Analyst",
        "⚙️ Admin: Manage Data",
        "📋 System Activity Log"
    ]
    
    selection = st.radio("Main Menu", menu_options, label_visibility="collapsed")
    
    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        logout()

# ==========================================
# 5. THE ROUTER ENGINE
# ==========================================
role = st.session_state.role

# Route the user to the correct file based on their click
if selection == "🏠 Dashboard Overview":
    Dashboard.render_page(role)
elif selection == "💼 Active Portfolio":
    Portfolio.render_page(role)
elif selection == "➕ Add Transaction":
    Add_Transaction.render_page(role)
elif selection == "🏦 My TMS (Cash & Margin)":
    My_TMS.render_page(role)
elif selection == "🧮 Trade Simulation":
    Trade_Simulation.render_page(role)
elif selection == "🎯 Watchlist & Alerts":
    Watchlist.render_page(role)
elif selection == "🧠 Risk & Journal":
    # Make sure your file in Tabs is named Risk_Journal.py exactly
    Risk_Journal.render_page(role) 
elif selection == "📜 Realized History":
    History.render_page(role)
elif selection == "📈 Wealth Trajectory":
    Wealth_Graph.render_page(role)
elif selection == "🤖 AI Market Analyst":
    Nepse_Data_Analysis.render_page(role)
elif selection == "⚙️ Admin: Manage Data":
    Manage_Data.render_page(role)
elif selection == "📋 System Activity Log":
    Activity_Log.render_page(role)

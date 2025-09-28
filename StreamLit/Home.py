# Import necessary libraries
import streamlit as st
import os
from modules.config import load_configuration
from modules.auth import get_authenticator
from streamlit_authenticator.utilities.exceptions import LoginError

# Set the title of the app
st.set_page_config(
    page_title="MyChart Explorer",
    layout="wide",
)

st.title("MyChart Explorer")

# --- Authentication ---
authenticator = get_authenticator()

# Initialize state
if "show_registration" not in st.session_state:
    st.session_state["show_registration"] = False
if "authentication_status" not in st.session_state:
    st.session_state["authentication_status"] = None

# --- Main Application Logic ---
# User is already logged in
if st.session_state.get("authentication_status"):
    user_data_dir = os.path.join("user_data", st.session_state["username"])
    os.makedirs(user_data_dir, exist_ok=True)
    
    st.session_state['db_path'] = os.path.join(user_data_dir, "mychart.db")
    st.session_state['config_path'] = os.path.join(user_data_dir, "config.json")

    # Retrieve and store the encryption key in the session
    username = st.session_state["username"]

    # Read from config.yaml to get per-user db_encryption_key (avoid accessing authenticator internals)
    try:
        import yaml
        from yaml.loader import SafeLoader
        with open('config.yaml') as f:
            cfg = yaml.load(f, Loader=SafeLoader) or {}
        user_creds = ((cfg.get('credentials') or {}).get('usernames') or {}).get(username, {})
        db_key = user_creds.get('db_encryption_key')
        if db_key:
            st.session_state['db_encryption_key'] = db_key
    except Exception:
        # Don't block the UI if config can't be read; encryption is optional
        pass
    
    authenticator.logout()
    st.sidebar.title(f"Welcome {st.session_state['name']}")
    
    load_configuration()
    
    db_path = st.session_state.get('db_path')
    if 'data_imported' not in st.session_state:
        if db_path and os.path.exists(db_path):
            st.session_state['data_imported'] = True
            st.toast(f"Found and loaded existing database: {os.path.basename(db_path)}", icon="✅")
        else:
            st.session_state['data_imported'] = False
    
    if st.session_state.get('data_imported', False):
        st.write("Your data is loaded and ready.")
        st.page_link("pages/01_MyChart_Explorer.py", label="Go to MyChart Explorer", icon="➡️")
    else:
        st.write("Welcome to MyChart Explorer! This app helps you explore your MyChart data and get health advice.")
        st.page_link("pages/03_Data_Importer.py", label="Get Started by Importing Your Data", icon="📥")
    
    st.sidebar.title("Navigation")
    st.sidebar.info("Use the pages to navigate the app. If you are starting for the first time, go to the Data Importer.")

# User is not logged in
else:
    try:
        authenticator.login(location='main')
    except LoginError as e:
        st.error(f"Login failed: {e}")
        st.switch_page("pages/05_Register.py")


    if st.session_state.get("authentication_status") is False:
        st.error('Username/password is incorrect. Please try again or register a new account.')
        st.page_link("pages/05_Register.py", label="Register a new user", icon="✍️")
    elif st.session_state.get("authentication_status") is None:
        st.warning('Please enter your username and password.')
        st.page_link("pages/05_Register.py", label="Register a new user", icon="✍️")

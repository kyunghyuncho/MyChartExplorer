# Import necessary libraries
import streamlit as st
import os
from modules.config import load_configuration

# Set the title of the app
st.set_page_config(
    page_title="MyChart Explorer",
    layout="wide",
)

st.title("MyChart Explorer")

# Load persisted configuration into session state
load_configuration()

# --- Auto-load database ---
# This section checks if a database file exists and pre-loads it into the session state.
# This avoids the need to re-import data every time the app is run.

# Use the db_path from session state if it exists, otherwise default to 'mychart.db'
db_path = st.session_state.get('db_path', 'mychart.db')

# Check if the data_imported flag is already set. If not, check for the database file.
if 'data_imported' not in st.session_state:
    # If the database file exists, set the session state to reflect that data is loaded.
    if os.path.exists(db_path):
        st.session_state['data_imported'] = True
        st.session_state['db_path'] = db_path
        # Show an info message to the user that an existing database was found.
        st.toast(f"Found and loaded existing database: {db_path}", icon="✅")
    else:
        # If no database is found, initialize the flag to False.
        st.session_state['data_imported'] = False

# --- Main Page Content ---

# If data is loaded, direct the user to the explorer. Otherwise, guide them to the importer.
if st.session_state.get('data_imported', False):
    st.write("Your data is loaded and ready.")
    st.page_link("pages/01_MyChart_Explorer.py", label="Go to MyChart Explorer", icon="➡️")
else:
    st.write("Welcome to MyChart Explorer! This app helps you explore your MyChart data and get health advice.")
    st.page_link("pages/03_Data_Importer.py", label="Get Started by Importing Your Data", icon="📥")


# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
st.sidebar.info("Use the pages to navigate the app. If you are starting for the first time, go to the Data Importer.")

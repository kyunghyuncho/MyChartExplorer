# This page allows users to directly explore the contents of the database.

import streamlit as st
import pandas as pd
from modules.database import get_db_engine
from sqlalchemy import inspect
from modules.config import load_configuration

st.set_page_config(
    page_title="Database Explorer",
    layout="wide",
)

st.title("Database Explorer")

# Load persisted configuration into session state
load_configuration()

# Check if data has been imported and a database path is available
if not st.session_state.get('data_imported', False):
    st.warning("No data imported yet. Please import your MyChart data first.")
    st.page_link("pages/03_Data_Importer.py", label="Go to Data Importer")
else:
    # Prefer user-specific db path set at login
    db_path = st.session_state.get('db_path', 'mychart.db')
    st.info(f"Exploring database: `{db_path}`")

    try:
        # Create the database engine
        engine = get_db_engine(db_path, key=st.session_state.get('db_encryption_key'))
        
        # Use SQLAlchemy's inspector to get table names
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        if not table_names:
            st.warning("No tables found in the database.")
        else:
            # Create a selectbox for the user to choose a table
            selected_table = st.selectbox("Select a table to view:", table_names)

            if selected_table:
                # Show a spinner while loading the data
                with st.spinner(f"Loading data from '{selected_table}'..."):
                    # Use pandas to read the entire table into a DataFrame
                    df = pd.read_sql_table(selected_table, engine)
                    
                    st.write(f"### Contents of `{selected_table}`")
                    # Display the DataFrame in an interactive table
                    st.dataframe(df)

    except Exception as e:
        st.error(f"An error occurred while connecting to the database: {e}")

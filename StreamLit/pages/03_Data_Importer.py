# This is the data importer page for the Streamlit app.
# It allows users to upload their MyChart XML data.

# Import necessary libraries
import streamlit as st
import os
from modules.database import get_db_engine, setup_database
from modules.importer import DataImporter
from modules.config import load_configuration

# Set the title of the page
st.title("Data Importer")

# Load persisted configuration into session state
load_configuration()

# Add an explanation of what to do
st.write("Upload your MyChart XML files to get started. This will parse the data and store it in a local SQLite database.")

# Add a text input for the database path
db_path = st.text_input("Database file path", value="mychart.db")

# Create a file uploader that accepts multiple files
uploaded_files = st.file_uploader("Choose your MyChart XML files", type="xml", accept_multiple_files=True)

# Check if files have been uploaded
if uploaded_files:
    # Create a button to start the import process
    if st.button("Import Data"):
        if not db_path:
            st.error("Database file path cannot be empty.")
        else:
            # Show a spinner while the data is being imported
            with st.spinner(f'Importing data into {db_path}... This may take a moment.'):
                try:
                    # Initialize the database
                    engine = get_db_engine(db_path)
                    setup_database(engine)
                    # Create an DataImporter instance
                    parser = DataImporter(engine)
                    
                    # Loop through each uploaded file
                    for uploaded_file in uploaded_files:
                        # Create a temporary path to save the uploaded file
                        temp_file_path = f"temp_{uploaded_file.name}"
                        # Write the uploaded file to the temporary path
                        with open(temp_file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        # Parse and import the data from the current file
                        parser.process_xml_file(temp_file_path)

                        # Clean up the temporary file
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)

                    # Show a success message
                    st.success("Data imported successfully!")
                    # Set a session state variable to indicate that the data has been imported
                    st.session_state['data_imported'] = True
                    st.session_state['db_path'] = db_path

                except Exception as e:
                    # Show an error message if something goes wrong
                    st.error(f"An error occurred during import: {e}")

# Add a button to navigate to the MyChart Explorer page
if st.session_state.get('data_imported', False):
    # If data has been imported, show a button to go to the explorer
    if st.button("Explore Your Data"):
        # This will switch to the MyChart Explorer page
        st.switch_page("pages/01_MyChart_Explorer.py")

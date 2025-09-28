# This is the data importer page for the Streamlit app.
# It allows users to upload their MyChart XML data.

# Import necessary libraries
import streamlit as st
import os
import traceback
from modules.database import get_db_engine, setup_database
from modules.importer import DataImporter
from modules.config import load_configuration
from modules.auth import check_auth

# Check user authentication
check_auth()

# Set the title of the page
st.title("Data Importer")

# Load persisted configuration into session state
load_configuration()

# Add an explanation of what to do
st.write("Upload your MyChart XML files to get started. This will parse the data and store it in a local SQLite database.")

# Initialize a persistent error log in session_state
st.session_state.setdefault('import_error_logs', [])

# Determine fixed per-user database path (set at login)
db_path = st.session_state.get('db_path', 'mychart.db')
st.info(f"Import will write to your private database: `{db_path}`")

# Create a file uploader that accepts multiple files
uploaded_files = st.file_uploader("Choose your MyChart XML files", type="xml", accept_multiple_files=True)

# Check if files have been uploaded
if uploaded_files:
    clear_db = False
    if os.path.exists(db_path):
        clear_db = st.checkbox(f"Clear existing database '{db_path}' before importing.")

    # Create a button to start the import process
    if st.button("Import Data"):
        if not db_path:
            st.error("Database file path cannot be empty.")
        else:
            # Progress + status containers
            prog_container = st.container()
            status_container = st.container()
            log_container = st.container()

            try:
                total = len(uploaded_files)
                progress = prog_container.progress(0, text=f"Starting import into {db_path}…")
                status_container.info("Preparing database…")

                # Ensure parent directory exists for user-specific paths
                os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
                if clear_db and os.path.exists(db_path):
                    os.remove(db_path)
                    st.toast(f"Removed existing database: {db_path}")

                # Initialize the database
                # Optional: support encryption if a passphrase exists in session
                db_key = st.session_state.get('db_encryption_key')
                engine = get_db_engine(db_path, key=db_key)
                setup_database(engine)
                # Create an DataImporter instance
                parser = DataImporter(engine)

                success_count = 0
                file_errors = []

                # Loop through each uploaded file
                for idx, uploaded_file in enumerate(uploaded_files):
                    fname = uploaded_file.name
                    # Create a temporary path to save the uploaded file
                    temp_file_path = f"temp_{fname}"
                    try:
                        # Write the uploaded file to the temporary path
                        with open(temp_file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                        # Parse and import the data from the current file
                        parser.process_xml_file(temp_file_path)
                        success_count += 1
                    except Exception as fe:
                        tb = traceback.format_exc()
                        msg = f"[FILE: {fname}] {fe}\n{tb}"
                        file_errors.append(msg)
                        st.session_state['import_error_logs'].append(msg)
                        status_container.error(f"Failed to import {fname}: {fe}")
                    finally:
                        # Clean up the temporary file
                        if os.path.exists(temp_file_path):
                            try:
                                os.remove(temp_file_path)
                            except Exception:
                                pass

                    # Update progress
                    progress.progress(int(((idx + 1) / total) * 100), text=f"Processed {idx + 1}/{total} file(s)")

                # Finalize
                if success_count > 0:
                    st.success(f"Imported {success_count} of {total} file(s) successfully.")
                    st.session_state['data_imported'] = True
                    st.session_state['db_path'] = db_path
                else:
                    st.error("No files were imported successfully. See the error log below.")

                # Show error log summary if any errors occurred this run
                if file_errors:
                    with st.expander("Error log (this run)", expanded=True):
                        st.code("\n\n".join(file_errors), language="text")
                # Also provide a persistent log viewer
                if st.session_state['import_error_logs']:
                    with st.expander("Persistent import error log", expanded=False):
                        st.code("\n\n".join(st.session_state['import_error_logs'][-100:]), language="text")
                        st.download_button(
                            label="Download full error log",
                            data="\n\n".join(st.session_state['import_error_logs']).encode("utf-8"),
                            file_name="import_error_log.txt",
                            mime="text/plain",
                        )
                        if st.button("Clear persistent error log"):
                            st.session_state['import_error_logs'] = []
                            st.toast("Cleared error log")
                            st.rerun()

            except Exception as e:
                # Unexpected top-level failure
                tb = traceback.format_exc()
                msg = f"[FATAL] {e}\n{tb}"
                st.session_state['import_error_logs'].append(msg)
                st.error(f"An unexpected error occurred during import: {e}")
                with st.expander("Error details", expanded=True):
                    st.code(tb, language="text")

# Add a button to navigate to the MyChart Explorer page
if st.session_state.get('data_imported', False):
    # If data has been imported, show a button to go to the explorer
    if st.button("Explore Your Data"):
        # This will switch to the MyChart Explorer page
        st.switch_page("pages/01_MyChart_Explorer.py")

# Always show persistent error log viewer at the bottom for user inspection
if st.session_state.get('import_error_logs'):
    st.markdown("---")
    with st.expander("Import error log (persistent)"):
        st.code("\n\n".join(st.session_state['import_error_logs'][-100:]), language="text")
        st.download_button(
            label="Download full error log",
            data="\n\n".join(st.session_state['import_error_logs']).encode("utf-8"),
            file_name="import_error_log.txt",
            mime="text/plain",
        )

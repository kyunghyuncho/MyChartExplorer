# This is the data importer page for the Streamlit app.
# It allows users to upload their MyChart XML data.

# Import necessary libraries
import streamlit as st
import os
import traceback
from modules.database import get_db_engine, setup_database
from modules.importer import DataImporter
from modules.config import load_configuration, get_db_size_limit_mb
from modules.auth import check_auth

# Check user authentication
check_auth()

st.title("Data Importer")

# Load persisted configuration into session state
load_configuration()

# Add an explanation of what to do
st.write("Import your health data either by uploading MyChart XML exports or by connecting directly via SMART on FHIR (Epic sandbox). Data is stored privately in your local SQLite database.")

# Initialize a persistent error log in session_state
st.session_state.setdefault('import_error_logs', [])

# Determine fixed per-user database path (set at login)
db_path = st.session_state.get('db_path', 'mychart.db')
st.info(f"Import will write to your private database: `{db_path}`")

# Storage threshold (MB) and helpers (admin-controlled)
db_size_limit_mb = int(get_db_size_limit_mb())

def _db_size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0.0

if os.path.exists(db_path):
    _cur = _db_size_mb(db_path)
    st.caption(f"Current DB size: {_cur:.1f} MB (limit {db_size_limit_mb} MB)")

tab_xml, tab_fhir = st.tabs(["MyChart XML Upload", "SMART on FHIR (beta)"])

with tab_xml:
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
                    # Pre-check current DB size after ensuring file exists
                    cur_mb = _db_size_mb(db_path)
                    if cur_mb >= db_size_limit_mb:
                        status_container.error(
                            f"Database size {cur_mb:.1f} MB exceeds the limit ({db_size_limit_mb} MB). Import blocked."
                        )
                        st.stop()
                    # Create an DataImporter instance
                    parser = DataImporter(engine)

                    success_count = 0
                    file_errors = []

                    # Loop through each uploaded file
                    import tempfile
                    for idx, uploaded_file in enumerate(uploaded_files):
                        fname = uploaded_file.name
                        # Create a secure temporary file to save the uploaded content
                        tmp = tempfile.NamedTemporaryFile(prefix="mychart_", suffix=".xml", delete=False)
                        temp_file_path = tmp.name
                        try:
                            # Write the uploaded file to the temporary path
                            with tmp:
                                tmp.write(uploaded_file.getbuffer())

                            # Parse and import the data from the current file
                            parser.process_xml_file(temp_file_path)
                            success_count += 1
                            # Mid-import size check
                            cur_mb = _db_size_mb(db_path)
                            if cur_mb >= db_size_limit_mb:
                                status_container.warning(
                                    f"Database reached {cur_mb:.1f} MB, exceeding the limit ({db_size_limit_mb} MB). Import has been stopped."
                                )
                                # Update progress to current point and stop processing more files
                                progress.progress(int(((idx + 1) / total) * 100), text=f"Processed {idx + 1}/{total} file(s)")
                                break
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

with tab_fhir:
    st.subheader("Connect to Epic via SMART on FHIR")
    st.caption("Beta: Authenticate with your Epic sandbox and sync clinical notes into your local database.")
    from modules.config import save_configuration
    from modules.fhir_client import generate_pkce, build_authorize_url, exchange_token, refresh_token as refresh_token_call, OAuthTokens, fetch_document_references, fetch_binary
    from modules.fhir_importer import ingest_document_references

    # Editable settings (persist per-user config)
    col1, col2 = st.columns(2)
    with col1:
        st.session_state['fhir_auth_url'] = st.text_input("Authorization URL", value=st.session_state.get('fhir_auth_url', ''))
        st.session_state['fhir_token_url'] = st.text_input("Token URL", value=st.session_state.get('fhir_token_url', ''))
        st.session_state['fhir_base_url'] = st.text_input("FHIR Base URL", value=st.session_state.get('fhir_base_url', ''))
    with col2:
        st.session_state['fhir_client_id'] = st.text_input("Client ID", value=st.session_state.get('fhir_client_id', ''))
        st.session_state['fhir_redirect_uri'] = st.text_input("Redirect URI", value=st.session_state.get('fhir_redirect_uri', 'http://localhost:8501'))
        st.session_state['fhir_scopes'] = st.text_input("Scopes", value=st.session_state.get('fhir_scopes', 'launch/patient patient/*.read offline_access openid profile'))
    if st.button("Save FHIR Settings"):
        save_configuration({
            "fhir_auth_url": st.session_state['fhir_auth_url'],
            "fhir_token_url": st.session_state['fhir_token_url'],
            "fhir_base_url": st.session_state['fhir_base_url'],
            "fhir_client_id": st.session_state['fhir_client_id'],
            "fhir_redirect_uri": st.session_state['fhir_redirect_uri'],
            "fhir_scopes": st.session_state['fhir_scopes'],
        })
        st.toast("Saved FHIR settings", icon="✅")

    # OAuth state
    st.session_state.setdefault('fhir_pkce_verifier', '')
    st.session_state.setdefault('fhir_state', '')
    st.session_state.setdefault('fhir_tokens', None)

    # Start auth
    if st.button("Start OAuth2 Authorization"):
        verifier, challenge = generate_pkce()
        st.session_state['fhir_pkce_verifier'] = verifier
        st.session_state['fhir_state'] = os.urandom(8).hex()
        url = build_authorize_url(
            st.session_state['fhir_auth_url'],
            st.session_state['fhir_client_id'],
            st.session_state['fhir_redirect_uri'],
            st.session_state['fhir_scopes'],
            challenge,
            st.session_state['fhir_state'],
        )
        st.link_button("Open Authorization URL", url)
        st.info("After logging in and approving, copy the 'code' parameter from the redirected URL and paste it below.")

    # Code exchange
    code = st.text_input("Authorization Code", value="")
    if st.button("Exchange Code for Tokens"):
        if not code:
            st.error("Please paste the authorization code from the redirect URL.")
        else:
            try:
                tokens = exchange_token(
                    st.session_state['fhir_token_url'],
                    code,
                    st.session_state['fhir_client_id'],
                    st.session_state['fhir_redirect_uri'],
                    st.session_state['fhir_pkce_verifier'],
                )
                st.session_state['fhir_tokens'] = tokens
                st.success("Received access token.")
            except Exception as e:
                st.error(f"Token exchange failed: {e}")

    # Refresh
    if st.session_state.get('fhir_tokens') and getattr(st.session_state['fhir_tokens'], 'refresh_token', None):
        if st.button("Refresh Access Token"):
            try:
                st.session_state['fhir_tokens'] = refresh_token_call(
                    st.session_state['fhir_token_url'],
                    st.session_state['fhir_tokens'].refresh_token,
                    st.session_state['fhir_client_id'],
                )
                st.toast("Refreshed access token.", icon="🔁")
            except Exception as e:
                st.error(f"Refresh failed: {e}")

    # Sync notes
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Sync Clinical Notes (DocumentReference)")
        since = st.text_input("Sync since (ISO 8601, optional)", value=st.session_state.get('last_fhir_sync', ''))
        if st.button("Fetch and Import Notes"):
            try:
                # Prepare DB
                db_key = st.session_state.get('db_encryption_key')
                engine = get_db_engine(db_path, key=db_key)
                setup_database(engine)

                prog = st.empty()
                prog.write("Fetching DocumentReference…")
                docs = fetch_document_references(
                    st.session_state['fhir_base_url'],
                    st.session_state['fhir_tokens'],
                    patient_id=None,
                    since=since or None,
                )
                prog.write(f"Fetched {len(docs)} DocumentReference(s). Resolving Binary attachments…")

                def _bin_loader(bid: str) -> bytes:
                    return fetch_binary(st.session_state['fhir_base_url'], st.session_state['fhir_tokens'], bid)

                new_rows = ingest_document_references(engine, docs, _bin_loader)
                st.success(f"Imported {new_rows} new note(s) from FHIR.")
                if new_rows > 0:
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    st.session_state['last_fhir_sync'] = now_iso
                    save_configuration({"last_fhir_sync": now_iso})
                st.session_state['data_imported'] = True
            except Exception as e:
                tb = traceback.format_exc()
                st.error(f"FHIR import failed: {e}")
                with st.expander("Error details"):
                    st.code(tb)
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
                # Pre-check current DB size after ensuring file exists
                cur_mb = _db_size_mb(db_path)
                if cur_mb >= db_size_limit_mb:
                    status_container.error(
                        f"Database size {cur_mb:.1f} MB exceeds the limit ({db_size_limit_mb} MB). Import blocked."
                    )
                    st.stop()
                # Create an DataImporter instance
                parser = DataImporter(engine)

                success_count = 0
                file_errors = []

                # Loop through each uploaded file
                import tempfile
                for idx, uploaded_file in enumerate(uploaded_files):
                    fname = uploaded_file.name
                    # Create a secure temporary file to save the uploaded content
                    tmp = tempfile.NamedTemporaryFile(prefix="mychart_", suffix=".xml", delete=False)
                    temp_file_path = tmp.name
                    try:
                        # Write the uploaded file to the temporary path
                        with tmp:
                            tmp.write(uploaded_file.getbuffer())

                        # Parse and import the data from the current file
                        parser.process_xml_file(temp_file_path)
                        success_count += 1
                        # Mid-import size check
                        cur_mb = _db_size_mb(db_path)
                        if cur_mb >= db_size_limit_mb:
                            status_container.warning(
                                f"Database reached {cur_mb:.1f} MB, exceeding the limit ({db_size_limit_mb} MB). Import has been stopped."
                            )
                            # Update progress to current point and stop processing more files
                            progress.progress(int(((idx + 1) / total) * 100), text=f"Processed {idx + 1}/{total} file(s)")
                            break
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

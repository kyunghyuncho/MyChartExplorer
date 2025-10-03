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

# Capture OAuth callback params early so we don't lose them if auth guard redirects
try:
    try:
        params = st.query_params  # type: ignore[attr-defined]
    except Exception:
        params = st.experimental_get_query_params()  # type: ignore[attr-defined]

    raw_code = params.get('code')
    raw_state = params.get('state')
    code_val = raw_code[0] if isinstance(raw_code, list) else raw_code
    state_val = raw_state[0] if isinstance(raw_state, list) else raw_state
    if isinstance(code_val, str) and code_val:
        st.session_state['pending_fhir_code'] = code_val
        if isinstance(state_val, str) and state_val:
            st.session_state['pending_fhir_state'] = state_val
        st.info("Received an authorization code from FHIR login. Continue on the Data Importer → SMART tab to exchange it.")
except Exception:
    pass

# Check user authentication (after persisting any pending code)
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
    if st.button("Import Data", key="xml_import_data"):
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

                    # Preflight: ensure the XML parser (lxml-xml) is available
                    try:
                        from bs4 import BeautifulSoup as _BS  # type: ignore
                        _ = _BS("<root/>", "lxml-xml")
                    except Exception as pe:
                        status_container.error(
                            "XML parser 'lxml-xml' is not available. Please install 'lxml' (and 'beautifulsoup4'). "
                            f"Details: {pe}"
                        )
                        st.stop()

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
                        if not file_errors:
                            st.info("Tip: Make sure you selected valid MyChart XML files. If you exported a ZIP, unzip it first and upload the .xml file(s).")

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
                            if st.button("Clear persistent error log", key="clear_error_log_run"):
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
    else:
        st.caption("No files selected yet. Upload one or more MyChart .xml exports to enable 'Import Data'.")

with tab_fhir:
    st.subheader("Connect to Epic via SMART on FHIR")
    st.caption("Beta: Authenticate with your Epic sandbox and sync clinical notes into your local database.")
    from modules.config import save_configuration
    from modules.fhir_client import (
        generate_pkce,
        build_authorize_url,
        exchange_token,
        refresh_token as refresh_token_call,
        OAuthTokens,
        fetch_document_references,
        fetch_binary,
        discover_smart_configuration,
        fetch_patient,
        fetch_allergy_intolerances,
        fetch_conditions,
        fetch_medication_statements,
        fetch_medication_requests,
        fetch_immunizations,
        fetch_observations,
        fetch_procedures,
        fetch_diagnostic_reports,
    )
    from modules.oauth_state import save_verifier as save_pkce_verifier, pop_verifier as pop_pkce_verifier
    from modules.fhir_importer import (
        ingest_document_references,
        upsert_patient,
        ingest_allergies,
        ingest_conditions,
        ingest_medications,
        ingest_immunizations,
        ingest_observations,
        ingest_procedures,
        ingest_diagnostic_reports_as_notes,
    )
    from modules.database import (
        get_session,
        Patient as DBPatient,
        Allergy as DBAllergy,
        Problem as DBProblem,
        Medication as DBMedication,
        Immunization as DBImmunization,
        Vital as DBVital,
        Result as DBResult,
        Procedure as DBProcedure,
        Note as DBNote,
    )

    # SMART settings: Admin-controlled fields become read-only here if set globally
    from modules.config import get_fhir_admin_settings
    admin_smart = get_fhir_admin_settings()
    admin_client_id = (admin_smart or {}).get('client_id') or ''
    admin_redirect = (admin_smart or {}).get('redirect_uri') or ''
    admin_scopes = (admin_smart or {}).get('scopes') or ''
    readonly_client = bool(admin_client_id)
    readonly_redirect = bool(admin_redirect)
    readonly_scopes = bool(admin_scopes)

    # Epic Open Endpoints directory (JSON) search and select — placed at top for natural flow
    st.markdown("### Epic endpoints (from open.epic.com)")
    epic_q = st.text_input("Search organization or URL", key="epic_json_query", value="")
    # Auto-load list if not already loaded
    if not st.session_state.get('epic_json_all'):
        try:
            with st.spinner("Loading Epic endpoints…"):
                from modules.hospital_directory import fetch_epic_open_endpoints_json
                items_all = fetch_epic_open_endpoints_json("https://open.epic.com/Endpoints/R4")
                # Inject Epic Public R4 Sandbox as a curated option if not present
                epic_public = {
                    "name": "Epic Public R4 Sandbox",
                    "vendor": "Epic",
                    "base_url": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
                    "auth_url": "",
                    "token_url": "",
                }
                if all((it.get('base_url') or '').rstrip('/') != epic_public['base_url'] for it in (items_all or [])):
                    items_all = (items_all or []) + [epic_public]
                st.session_state['epic_json_all'] = items_all or []
        except Exception as e:
            st.warning(f"Could not auto-load Epic endpoints: {e}")
    items_cached = st.session_state.get('epic_json_all') or []
    # Filter in-memory for responsiveness
    if items_cached:
        q = (epic_q or "").strip().lower()
        items = [it for it in items_cached if (q in (it.get('name','').lower()) or q in (it.get('base_url','').lower()))] if q else items_cached
        labels = [f"{it.get('name','?')} — {it.get('base_url','')}" for it in items[:500]]
        sel = st.selectbox("Select a site", options=["—"] + labels, index=0, key="sel_epic_json")
        if sel and sel != "—":
            idx = labels.index(sel)
            ent = items[idx]
            selected_base = ent.get('base_url','').strip()
            # Only apply and rerun if selection changed
            previously_applied = st.session_state.get('epic_applied_base', '')
            if selected_base and selected_base != previously_applied:
                st.session_state['fhir_base_url'] = selected_base
                # If JSON provided auth/token URLs, use them; else try SMART discovery lazily
                auth_url = ent.get('auth_url') or ''
                token_url = ent.get('token_url') or ''
                if auth_url:
                    st.session_state['fhir_auth_url'] = auth_url
                if token_url:
                    st.session_state['fhir_token_url'] = token_url
                if not auth_url or not token_url:
                    try:
                        with st.spinner("Discovering OAuth endpoints from SMART config…"):
                            cfg = discover_smart_configuration(st.session_state['fhir_base_url'])
                            st.session_state['fhir_auth_url'] = cfg.get('authorization_endpoint', st.session_state.get('fhir_auth_url', ''))
                            st.session_state['fhir_token_url'] = cfg.get('token_endpoint', st.session_state.get('fhir_token_url', ''))
                        st.info("Filled missing OAuth URLs via SMART discovery.")
                    except Exception as e:
                        st.warning(f"SMART discovery failed for this site: {e}")
                # Persist and mark applied, then rerun to refresh inputs immediately
                save_configuration({
                    "fhir_base_url": st.session_state['fhir_base_url'],
                    "fhir_auth_url": st.session_state.get('fhir_auth_url',''),
                    "fhir_token_url": st.session_state.get('fhir_token_url',''),
                })
                st.session_state['epic_applied_base'] = selected_base
                try:
                    st.rerun()
                except Exception:
                    try:
                        st.experimental_rerun()  # Streamlit <1.25
                    except Exception:
                        pass
        # Show current URLs in small text right under the list
        if st.session_state.get('fhir_base_url'):
            st.caption(f"FHIR Base: {st.session_state.get('fhir_base_url')}")
        if st.session_state.get('fhir_auth_url'):
            st.caption(f"Auth URL: {st.session_state.get('fhir_auth_url')}")
        if st.session_state.get('fhir_token_url'):
            st.caption(f"Token URL: {st.session_state.get('fhir_token_url')}")

    # Editable settings (auto-saved on list selection; manual save button removed per request)
    col1, col2 = st.columns(2)
    with col1:
        st.session_state['fhir_auth_url'] = st.text_input("Authorization URL", value=st.session_state.get('fhir_auth_url', ''))
        st.session_state['fhir_token_url'] = st.text_input("Token URL", value=st.session_state.get('fhir_token_url', ''))
        st.session_state['fhir_base_url'] = st.text_input("FHIR Base URL", value=st.session_state.get('fhir_base_url', ''))
    with col2:
        # Client ID: mask in UI. If admin-set, do NOT send real value to browser.
        if readonly_client:
            # Keep the real value server-side for use in OAuth; show masked placeholder in a separate widget key
            st.session_state['fhir_client_id'] = admin_client_id
            st.text_input(
                "Client ID",
                value="********",
                disabled=True,
                type="password",
                help="Admin-controlled",
                key="fhir_client_id_mask",
            )
        else:
            st.session_state['fhir_client_id'] = st.text_input(
                "Client ID",
                value=st.session_state.get('fhir_client_id', ''),
                type="password",
                help=None,
            )
        st.session_state['fhir_redirect_uri'] = st.text_input(
            "Redirect URI",
            value=admin_redirect or st.session_state.get('fhir_redirect_uri', 'http://localhost:8501'),
            disabled=readonly_redirect,
            help="Admin-controlled" if readonly_redirect else None,
        )
        st.session_state['fhir_scopes'] = st.text_input(
            "Scopes",
            value=admin_scopes or st.session_state.get('fhir_scopes', 'launch/patient patient/*.read offline_access openid profile'),
            disabled=readonly_scopes,
            help="Admin-controlled" if readonly_scopes else None,
        )
    # Removed explicit "Save FHIR Settings" button — selection auto-saves

    # Removed Epic defaults button — Epic Public R4 appears as an item in the list above

    # (List moved above; old expander removed)

    # Removed manual discovery button — handled automatically on selection

    # OAuth state
    st.session_state.setdefault('fhir_pkce_verifier', '')
    st.session_state.setdefault('fhir_state', '')
    st.session_state.setdefault('fhir_tokens', None)
    st.session_state.setdefault('fhir_pkce_verifier_map', {})  # state -> verifier

    # Start auth
    if st.button("Start OAuth2 Authorization", key="start_oauth"):
        verifier, challenge = generate_pkce()
        st.session_state['fhir_pkce_verifier'] = verifier
        st.session_state['fhir_state'] = os.urandom(8).hex()
        # Track verifier per state to avoid mismatches if user starts multiple auth attempts
        try:
            vmap = st.session_state.get('fhir_pkce_verifier_map') or {}
            vmap[st.session_state['fhir_state']] = verifier
            st.session_state['fhir_pkce_verifier_map'] = vmap
        except Exception:
            pass
        # Persist to disk for resilience across reruns/refreshes
        try:
            if st.session_state.get('username'):
                save_pkce_verifier(st.session_state['username'], st.session_state['fhir_state'], verifier)
        except Exception:
            pass
        url = build_authorize_url(
            st.session_state['fhir_auth_url'],
            st.session_state['fhir_client_id'],
            st.session_state['fhir_redirect_uri'],
            st.session_state['fhir_scopes'],
            challenge,
            st.session_state['fhir_state'],
            aud=st.session_state.get('fhir_base_url') or None,
            response_mode="query",
        )
        # Explain why user needs to click; open in same tab so the browser navigates away and returns via Redirect URI
        st.markdown("To connect your Epic account, continue to Epic to sign in and grant this app read access to your records.")
        st.markdown(f"<a href='{url}' target='_self' class='st-button st-primary'>Continue to Epic sign-in and authorize access</a>", unsafe_allow_html=True)
        st.caption("After authorizing, you'll be redirected back here. We'll automatically capture the authorization code and exchange it for tokens.")

    # Code exchange
    # Try to auto-capture code from query params if user was redirected back to this page
    code_default = ""
    try:
        # Streamlit 1.32+ exposes st.query_params as a dict-like
        try:
            params = st.query_params  # type: ignore[attr-defined]
        except Exception:
            params = st.experimental_get_query_params()  # type: ignore[attr-defined]
        if isinstance(params, dict):
            raw = params.get('code')
            if isinstance(raw, list):
                code_default = raw[0] if raw else ""
            elif isinstance(raw, str):
                code_default = raw
            # Also capture state for verifier lookup
            raw_state = params.get('state')
            if isinstance(raw_state, list):
                st.session_state['pending_fhir_state'] = raw_state[0] if raw_state else st.session_state.get('pending_fhir_state', '')
            elif isinstance(raw_state, str):
                st.session_state['pending_fhir_state'] = raw_state
    except Exception:
        pass
    if not code_default:
        code_default = st.session_state.get('pending_fhir_code', "")
    code = st.text_input("Authorization Code", value=code_default)
    # Helpful hint if state suggests a different in-flight verifier
    if st.session_state.get('pending_fhir_state') and st.session_state.get('fhir_state') and st.session_state['pending_fhir_state'] != st.session_state['fhir_state']:
        st.caption("Note: Returned state differs from the last started auth. Selecting the correct verifier automatically.")

    # Optional: Auto-exchange when code is present and no tokens yet
    if (not st.session_state.get('fhir_tokens')) and code:
        # Pre-flight checks
        missing = []
        if not (st.session_state.get('fhir_token_url')):
            missing.append('Token URL')
        if not (st.session_state.get('fhir_client_id')):
            missing.append('Client ID')
        if not (st.session_state.get('fhir_redirect_uri')):
            missing.append('Redirect URI')
        # Determine which verifier to use (match returned state first)
        verifier_to_use = None
        try:
            if st.session_state.get('pending_fhir_state') and st.session_state.get('fhir_pkce_verifier_map'):
                verifier_to_use = (st.session_state['fhir_pkce_verifier_map'] or {}).get(st.session_state['pending_fhir_state'])
        except Exception:
            verifier_to_use = None
        if not verifier_to_use:
            # Try persistent store next
            try:
                if st.session_state.get('username') and st.session_state.get('pending_fhir_state'):
                    verifier_to_use = pop_pkce_verifier(st.session_state['username'], st.session_state['pending_fhir_state']) or None
            except Exception:
                verifier_to_use = None
        if not verifier_to_use:
            verifier_to_use = st.session_state.get('fhir_pkce_verifier')
        if not verifier_to_use:
            missing.append('PKCE verifier (start auth first)')
        if missing:
            st.info("Cannot auto-exchange yet. Missing: " + ", ".join(missing))
        else:
            with st.spinner("Exchanging authorization code…"):
                try:
                    tokens = exchange_token(
                        st.session_state['fhir_token_url'],
                        code,
                        st.session_state['fhir_client_id'],
                        st.session_state['fhir_redirect_uri'],
                        verifier_to_use,
                    )
                    st.session_state['fhir_tokens'] = tokens
                    st.success("Received access token.")
                    # Clear pending code after successful exchange
                    st.session_state.pop('pending_fhir_code', None)
                    st.session_state.pop('pending_fhir_state', None)
                    # Remove the consumed verifier entry
                    try:
                        if st.session_state.get('fhir_pkce_verifier_map') and st.session_state.get('fhir_state'):
                            st.session_state['fhir_pkce_verifier_map'].pop(st.session_state.get('fhir_state'), None)
                    except Exception:
                        pass
                except Exception as e:
                    st.warning(f"Auto-exchange failed: {e}")
                    with st.expander("Troubleshoot 400 Bad Request"):
                        st.markdown(
                            "- Ensure the Redirect URI here exactly matches what you registered in Epic (including path and trailing slash).\n"
                            "- Click 'Start OAuth2 Authorization' again to generate a fresh PKCE verifier before attempting another exchange.\n"
                            "- Confirm scopes and that aud is set to your FHIR Base.\n"
                            "- If discovery didn’t run, try 'Discover OAuth Endpoints' or the Epic preset."
                        )
    # Removed manual "Exchange Code for Tokens" — auto-exchange handles this when code is present

    # Synchronize all clinical data (appears after token exchange)
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Synchronize all clinical data")
        colS1, colS2 = st.columns(2)
        with colS1:
            since_all = st.text_input("Sync since (ISO 8601, optional)", key="sync_all_since", value="")
        with colS2:
            skip_bin_all = st.checkbox("Skip Binary attachments for notes", key="sync_all_skip_binary", value=False)
        if st.button("Synchronize all", key="sync_all_button"):
            try:
                # Prepare DB
                db_key = st.session_state.get('db_encryption_key')
                engine = get_db_engine(db_path, key=db_key)
                setup_database(engine)

                base = st.session_state['fhir_base_url']
                tokens = st.session_state['fhir_tokens']
                pid = getattr(tokens, 'patient_id', None)

                summary = {
                    'patient_upserted': False,
                    'allergies': 0,
                    'problems': 0,
                    'medications': 0,
                    'immunizations': 0,
                    'vitals': 0,
                    'lab_results': 0,
                    'procedures': 0,
                    'notes_docref': 0,
                    'notes_docref_skipped': 0,
                    'notes_diagnostic': 0,
                    'notes_diagnostic_skipped': 0,
                    'errors': [],
                }

                prog = st.progress(0, text="Starting synchronization…")
                step = 0
                total_steps = 9

                # 1. Patient demographics
                try:
                    if pid:
                        pres = fetch_patient(base, tokens, pid)
                        upsert_patient(engine, pres)
                        summary['patient_upserted'] = True
                except Exception as e:
                    summary['errors'].append(f"Patient: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Patient")

                # 2. Allergies
                try:
                    items = fetch_allergy_intolerances(base, tokens, patient_id=pid, since=since_all or None)
                    summary['allergies'] = ingest_allergies(engine, items)
                except Exception as e:
                    summary['errors'].append(f"Allergies: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Allergies")

                # 3. Problems (Conditions)
                try:
                    items = fetch_conditions(base, tokens, patient_id=pid, since=since_all or None)
                    summary['problems'] = ingest_conditions(engine, items)
                except Exception as e:
                    summary['errors'].append(f"Problems: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Problems")

                # 4. Medications (Statements + Requests)
                try:
                    stmts = fetch_medication_statements(base, tokens, patient_id=pid, since=since_all or None)
                    reqs = fetch_medication_requests(base, tokens, patient_id=pid, since=since_all or None)
                    summary['medications'] = ingest_medications(engine, stmts, reqs)
                except Exception as e:
                    summary['errors'].append(f"Medications: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Medications")

                # 5. Immunizations
                try:
                    items = fetch_immunizations(base, tokens, patient_id=pid, since=since_all or None)
                    summary['immunizations'] = ingest_immunizations(engine, items)
                except Exception as e:
                    summary['errors'].append(f"Immunizations: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Immunizations")

                # 6. Observations (Vitals + Labs)
                try:
                    vitals = fetch_observations(base, tokens, patient_id=pid, category="vital-signs", since=since_all or None)
                    labs = fetch_observations(base, tokens, patient_id=pid, category="laboratory", since=since_all or None)
                    nv, nr = ingest_observations(engine, vitals + labs)
                    summary['vitals'] = nv
                    summary['lab_results'] = nr
                except Exception as e:
                    summary['errors'].append(f"Observations: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Observations")

                # 7. Procedures
                try:
                    items = fetch_procedures(base, tokens, patient_id=pid, since=since_all or None)
                    summary['procedures'] = ingest_procedures(engine, items)
                except Exception as e:
                    summary['errors'].append(f"Procedures: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced Procedures")

                # Helper: Binary loader honoring skip flag
                def _bin_loader(bid: str) -> bytes:
                    if skip_bin_all:
                        raise RuntimeError("Binary fetching disabled")
                    return fetch_binary(base, tokens, bid)

                # 8. Notes via DocumentReference
                try:
                    docs = fetch_document_references(base, tokens, patient_id=pid, since=since_all or None)
                    new_rows, skipped = ingest_document_references(engine, docs, _bin_loader)
                    summary['notes_docref'] = new_rows
                    summary['notes_docref_skipped'] = skipped
                except Exception as e:
                    summary['errors'].append(f"DocumentReference: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Synced DocumentReference Notes")

                # 9. Notes via DiagnosticReport.presentedForm
                try:
                    reports = fetch_diagnostic_reports(base, tokens, patient_id=pid, since=since_all or None)
                    new_rows, skipped = ingest_diagnostic_reports_as_notes(engine, reports, _bin_loader)
                    summary['notes_diagnostic'] = new_rows
                    summary['notes_diagnostic_skipped'] = skipped
                except Exception as e:
                    summary['errors'].append(f"DiagnosticReport: {e}")
                step += 1; prog.progress(int(step/total_steps*100), text="Finished synchronization")

                # Update last sync if anything was added
                if any([
                    summary['allergies'], summary['problems'], summary['medications'],
                    summary['immunizations'], summary['vitals'], summary['lab_results'],
                    summary['procedures'], summary['notes_docref'], summary['notes_diagnostic'],
                ]):
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    st.session_state['last_fhir_sync'] = now_iso
                    try:
                        save_configuration({"last_fhir_sync": now_iso})
                    except Exception:
                        pass

                # Show summary
                st.success("Synchronization complete")
                st.json({
                    "patient_upserted": summary['patient_upserted'],
                    "allergies_imported": summary['allergies'],
                    "problems_imported": summary['problems'],
                    "medications_imported": summary['medications'],
                    "immunizations_imported": summary['immunizations'],
                    "vitals_imported": summary['vitals'],
                    "lab_results_imported": summary['lab_results'],
                    "procedures_imported": summary['procedures'],
                    "notes_docref_imported": summary['notes_docref'],
                    "notes_docref_skipped_no_content": summary['notes_docref_skipped'],
                    "notes_diagnostic_imported": summary['notes_diagnostic'],
                    "notes_diagnostic_skipped_no_content": summary['notes_diagnostic_skipped'],
                    "errors": summary['errors'],
                })
                st.session_state['data_imported'] = True
            except Exception as e:
                tb = traceback.format_exc()
                st.error(f"Synchronize all failed: {e}")
                with st.expander("Error details"):
                    st.code(tb)

    # Refresh
    if st.session_state.get('fhir_tokens') and getattr(st.session_state['fhir_tokens'], 'refresh_token', None):
        if st.button("Refresh Access Token", key="refresh_access_token"):
            try:
                st.session_state['fhir_tokens'] = refresh_token_call(
                    st.session_state['fhir_token_url'],
                    st.session_state['fhir_tokens'].refresh_token,
                    st.session_state['fhir_client_id'],
                )
                st.toast("Refreshed access token.", icon="🔁")
            except Exception as e:
                st.error(f"Refresh failed: {e}")

    # Token debug panel: show granted scopes and context
    if st.session_state.get('fhir_tokens'):
        t = st.session_state['fhir_tokens']
        with st.expander("Token details (granted scopes)", expanded=False):
            st.write({
                "patient_id": getattr(t, 'patient_id', None),
                "scope": getattr(t, 'scope', None),
                "token_type": getattr(t, 'token_type', None),
            })

    # Patient demographics
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Patient Demographics")
        pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
        st.caption(f"Patient ID from token: {pid or '(not provided)'}")
        colp1, colp2 = st.columns(2)
        with colp1:
            if st.button("Fetch Patient Info", key="fetch_patient_info"):
                if not pid:
                    st.warning("No patient_id in token. Ensure your Epic app returns 'patient' in token response and scope includes patient/Patient.read.")
                else:
                    try:
                        db_key = st.session_state.get('db_encryption_key')
                        engine = get_db_engine(db_path, key=db_key)
                        setup_database(engine)
                        pres = fetch_patient(st.session_state['fhir_base_url'], st.session_state['fhir_tokens'], pid)
                        upsert_patient(engine, pres)
                        st.success("Saved patient demographics to database.")
                        with st.expander("FHIR Patient (raw)", expanded=False):
                            st.json(pres)
                    except Exception as e:
                        st.error(f"Failed to fetch/save Patient: {e}")
        with colp2:
            if st.button("Preview Patient from DB", key="preview_patient_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        row = session.query(DBPatient).first()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if row:
                        st.json({
                            "mrn": row.mrn,
                            "full_name": row.full_name,
                            "dob": row.dob,
                            "gender": row.gender,
                            "marital_status": row.marital_status,
                            "race": row.race,
                            "ethnicity": row.ethnicity,
                            "deceased": row.deceased,
                            "deceased_date": row.deceased_date,
                        })
                    else:
                        st.info("No patient row found yet. Click 'Fetch Patient Info' first or run a notes sync (which creates a placeholder).")
                except Exception as e:
                    st.error(f"Failed to read Patient from DB: {e}")

    # Allergies
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Allergies")
        colA1, colA2 = st.columns(2)
        with colA1:
            since_all = st.text_input("Sync since (ISO 8601, optional)", key="allergies_since", value="")
            if st.button("Fetch and Import Allergies", key="fetch_import_allergies"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    items = fetch_allergy_intolerances(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_all or None,
                    )
                    new_count = ingest_allergies(engine, items)
                    if new_count > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_count} allergy record(s).")
                    else:
                        st.info("No new allergy records imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Allergy import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colA2:
            if st.button("Preview Allergies from DB", key="preview_allergies_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        rows = session.query(DBAllergy).order_by(DBAllergy.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if rows:
                        st.dataframe([
                            {
                                "substance": r.substance,
                                "reaction": r.reaction,
                                "status": r.status,
                                "effective_date": r.effective_date,
                            }
                            for r in rows
                        ])
                    else:
                        st.info("No allergies in database yet.")
                except Exception as e:
                    st.error(f"Failed to read allergies from DB: {e}")

    # Problems (Conditions)
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Problems (Conditions)")
        colC1, colC2 = st.columns(2)
        with colC1:
            since_cond = st.text_input("Sync since (ISO 8601, optional)", key="conditions_since", value="")
            if st.button("Fetch and Import Problems", key="fetch_import_conditions"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    items = fetch_conditions(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_cond or None,
                    )
                    new_count = ingest_conditions(engine, items)
                    if new_count > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_count} problem record(s).")
                    else:
                        st.info("No new problem records imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Problems import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colC2:
            if st.button("Preview Problems from DB", key="preview_problems_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        rows = session.query(DBProblem).order_by(DBProblem.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if rows:
                        st.dataframe([
                            {
                                "problem_name": r.problem_name,
                                "status": r.status,
                                "onset_date": r.onset_date,
                                "resolved_date": r.resolved_date,
                            }
                            for r in rows
                        ])
                    else:
                        st.info("No problems in database yet.")
                except Exception as e:
                    st.error(f"Failed to read problems from DB: {e}")

    # Medications
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Medications")
        colM1, colM2 = st.columns(2)
        with colM1:
            since_med = st.text_input("Sync since (ISO 8601, optional)", key="medications_since", value="")
            if st.button("Fetch and Import Medications", key="fetch_import_medications"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    statements = fetch_medication_statements(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_med or None,
                    )
                    requests = fetch_medication_requests(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_med or None,
                    )
                    new_count = ingest_medications(engine, statements, requests)
                    if new_count > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_count} medication record(s).")
                    else:
                        st.info("No new medication records imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Medications import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colM2:
            if st.button("Preview Medications from DB", key="preview_medications_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        rows = session.query(DBMedication).order_by(DBMedication.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if rows:
                        st.dataframe([
                            {
                                "medication_name": r.medication_name,
                                "instructions": r.instructions,
                                "status": r.status,
                                "start_date": r.start_date,
                                "end_date": r.end_date,
                            }
                            for r in rows
                        ])
                    else:
                        st.info("No medications in database yet.")
                except Exception as e:
                    st.error(f"Failed to read medications from DB: {e}")

    # Immunizations
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Immunizations")
        colI1, colI2 = st.columns(2)
        with colI1:
            since_imm = st.text_input("Sync since (ISO 8601, optional)", key="immunizations_since", value="")
            if st.button("Fetch and Import Immunizations", key="fetch_import_immunizations"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    # Pre-check scopes and patient context to avoid 403s
                    scopes = (getattr(st.session_state['fhir_tokens'], 'scope', '') or '').split()
                    has_immun_scope = any(s in scopes for s in [
                        'patient/Immunization.read',
                        'patient/*.read',
                        'user/Immunization.read',
                        'user/*.read',
                    ])
                    if not pid:
                        st.warning("Token is missing patient context. Ensure your app requests 'launch/patient' and Epic returns 'patient' in token response.")
                        st.stop()
                    if not has_immun_scope:
                        st.warning("Scope missing for Immunization. Add 'patient/Immunization.read' (or 'patient/*.read') to requested scopes and re-authenticate.")
                        st.stop()
                    items = fetch_immunizations(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_imm or None,
                    )
                    new_count = ingest_immunizations(engine, items)
                    if new_count > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_count} immunization record(s).")
                    else:
                        st.info("No new immunization records imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Immunizations import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colI2:
            if st.button("Preview Immunizations from DB", key="preview_immunizations_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        rows = session.query(DBImmunization).order_by(DBImmunization.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if rows:
                        st.dataframe([
                            {
                                "vaccine_name": r.vaccine_name,
                                "date_administered": r.date_administered,
                            }
                            for r in rows
                        ])
                    else:
                        st.info("No immunizations in database yet.")
                except Exception as e:
                    st.error(f"Failed to read immunizations from DB: {e}")

    # Observations (Vitals & Labs)
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Observations: Vitals and Labs")
        colO1, colO2 = st.columns(2)
        with colO1:
            since_obs = st.text_input("Sync since (ISO 8601, optional)", key="observations_since", value="")
            if st.button("Fetch and Import Vitals + Labs", key="fetch_import_observations"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    # Fetch vitals and labs separately then combine
                    vitals = fetch_observations(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        category="vital-signs",
                        since=since_obs or None,
                    )
                    labs = fetch_observations(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        category="laboratory",
                        since=since_obs or None,
                    )
                    new_vitals, new_results = ingest_observations(engine, vitals + labs)
                    if (new_vitals + new_results) > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_vitals} vital(s) and {new_results} lab result(s).")
                    else:
                        st.info("No new vitals or lab results imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Observations import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colO2:
            if st.button("Preview Vitals and Labs from DB", key="preview_observations_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        vit_rows = session.query(DBVital).order_by(DBVital.id.desc()).limit(20).all()
                        res_rows = session.query(DBResult).order_by(DBResult.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    st.markdown("Latest Vitals")
                    if vit_rows:
                        st.dataframe([
                            {
                                "vital_sign": r.vital_sign,
                                "value": r.value,
                                "unit": r.unit,
                                "effective_date": r.effective_date,
                            }
                            for r in vit_rows
                        ])
                    else:
                        st.info("No vitals in database yet.")
                    st.markdown("Latest Lab Results")
                    if res_rows:
                        st.dataframe([
                            {
                                "test_name": r.test_name,
                                "value": r.value,
                                "unit": r.unit,
                                "reference_range": r.reference_range,
                                "interpretation": r.interpretation,
                                "effective_date": r.effective_date,
                            }
                            for r in res_rows
                        ])
                    else:
                        st.info("No lab results in database yet.")
                except Exception as e:
                    st.error(f"Failed to read observations from DB: {e}")

    # Procedures
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Procedures")
        colP1, colP2 = st.columns(2)
        with colP1:
            since_proc = st.text_input("Sync since (ISO 8601, optional)", key="procedures_since", value="")
            if st.button("Fetch and Import Procedures", key="fetch_import_procedures"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                    items = fetch_procedures(
                        st.session_state['fhir_base_url'],
                        st.session_state['fhir_tokens'],
                        patient_id=pid,
                        since=since_proc or None,
                    )
                    new_count = ingest_procedures(engine, items)
                    if new_count > 0:
                        from datetime import datetime, timezone
                        now_iso = datetime.now(timezone.utc).isoformat()
                        st.session_state['last_fhir_sync'] = now_iso
                        save_configuration({"last_fhir_sync": now_iso})
                        st.success(f"Imported {new_count} procedure record(s).")
                    else:
                        st.info("No new procedure records imported.")
                except Exception as e:
                    tb = traceback.format_exc()
                    st.error(f"Procedures import failed: {e}")
                    with st.expander("Error details"):
                        st.code(tb)
        with colP2:
            if st.button("Preview Procedures from DB", key="preview_procedures_db"):
                try:
                    db_key = st.session_state.get('db_encryption_key')
                    engine = get_db_engine(db_path, key=db_key)
                    setup_database(engine)
                    session = get_session(engine)
                    try:
                        rows = session.query(DBProcedure).order_by(DBProcedure.id.desc()).limit(20).all()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                    if rows:
                        st.dataframe([
                            {
                                "procedure_name": r.procedure_name,
                                "date": r.date,
                                "provider": r.provider,
                            }
                            for r in rows
                        ])
                    else:
                        st.info("No procedures in database yet.")
                except Exception as e:
                    st.error(f"Failed to read procedures from DB: {e}")

    # Diagnostic Reports → Notes
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Diagnostic Reports (as Notes)")
        since_dr = st.text_input("Sync since (ISO 8601, optional)", key="diagreports_since", value="")
        skip_binary_dr = st.checkbox(
            "Skip fetching Binary attachments for Diagnostic Reports",
            value=False,
            key="skip_binary_diagreports",
            help="Use inline data in presentedForm only; skip Binary fetch to avoid 403s.",
        )
        if st.button("Fetch and Import Diagnostic Reports", key="fetch_import_diagreports"):
            try:
                db_key = st.session_state.get('db_encryption_key')
                engine = get_db_engine(db_path, key=db_key)
                setup_database(engine)
                pid = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                reports = fetch_diagnostic_reports(
                    st.session_state['fhir_base_url'],
                    st.session_state['fhir_tokens'],
                    patient_id=pid,
                    since=since_dr or None,
                )
                def _bin_loader_dr(bid: str) -> bytes:
                    if skip_binary_dr:
                        raise RuntimeError("Binary fetching disabled")
                    return fetch_binary(st.session_state['fhir_base_url'], st.session_state['fhir_tokens'], bid)
                new_rows, skipped = ingest_diagnostic_reports_as_notes(engine, reports, _bin_loader_dr)
                if new_rows > 0:
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    st.session_state['last_fhir_sync'] = now_iso
                    save_configuration({"last_fhir_sync": now_iso})
                    st.success(f"Imported {new_rows} diagnostic report note(s). Skipped {skipped} without accessible content.")
                else:
                    st.info(f"No new diagnostic report notes imported. Retrieved {len(reports)} reports; skipped {skipped} without accessible content.")
            except Exception as e:
                tb = traceback.format_exc()
                st.error(f"Diagnostic Reports import failed: {e}")
                with st.expander("Error details"):
                    st.code(tb)

    # Sync notes
    if st.session_state.get('fhir_tokens'):
        st.divider()
        st.subheader("Sync Clinical Notes (DocumentReference)")
        since = st.text_input("Sync since (ISO 8601, optional)", value="")
        skip_binary = st.checkbox("Skip fetching Binary attachments (use inline data only)", value=False, help="Avoids 403s for direct Binary access. Uses content.attachment.data when present; otherwise skips the note.")
        if st.button("Fetch and Import Notes", key="fetch_import_notes"):
            try:
                # Prepare DB
                db_key = st.session_state.get('db_encryption_key')
                engine = get_db_engine(db_path, key=db_key)
                setup_database(engine)
                # Ensure patient demographics are saved if we have a patient_id
                patient_hint = getattr(st.session_state['fhir_tokens'], 'patient_id', None)
                if patient_hint:
                    try:
                        pres = fetch_patient(st.session_state['fhir_base_url'], st.session_state['fhir_tokens'], patient_hint)
                        upsert_patient(engine, pres)
                    except Exception:
                        pass

                prog = st.empty()
                prog.write("Fetching DocumentReference…")
                # Prefer patient-scoped query if Epic returned a patient in token response
                docs = fetch_document_references(
                    st.session_state['fhir_base_url'],
                    st.session_state['fhir_tokens'],
                    patient_id=patient_hint,
                    since=since or None,
                )
                prog.write(f"Fetched {len(docs)} DocumentReference(s). Resolving Binary attachments…")
                # Quick preview to help debug when nothing is imported
                if len(docs) == 0:
                    st.info("No DocumentReference resources returned. Check scopes, patient context, and the 'since' filter.")
                else:
                    with st.expander("Preview retrieved DocumentReference(s)"):
                        preview = []
                        for doc in docs[:10]:
                            atts = []
                            for c in (doc.get("content") or []):
                                a = c.get("attachment") or {}
                                url_val = a.get("url")
                                if isinstance(url_val, str) and len(url_val) > 120:
                                    url_val = url_val[:120] + "…"
                                atts.append({
                                    "contentType": a.get("contentType"),
                                    "has_data": bool(a.get("data")),
                                    "has_url": bool(a.get("url")),
                                    "url": url_val,
                                })
                            preview.append({
                                "id": doc.get("id"),
                                "description": doc.get("description") or (doc.get("type") or {}).get("text"),
                                "date": doc.get("date") or doc.get("indexed"),
                                "attachments": atts,
                            })
                        st.json(preview)

                def _bin_loader(bid: str) -> bytes:
                    if skip_binary:
                        raise RuntimeError("Binary fetching disabled")
                    return fetch_binary(st.session_state['fhir_base_url'], st.session_state['fhir_tokens'], bid)

                new_rows, skipped_no_content = ingest_document_references(engine, docs, _bin_loader)
                if new_rows > 0:
                    st.success(f"Imported {new_rows} new note(s) from FHIR. Skipped {skipped_no_content} item(s) with no accessible content.")
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    st.session_state['last_fhir_sync'] = now_iso
                    save_configuration({"last_fhir_sync": now_iso})
                else:
                    st.info(f"No new notes imported. Retrieved {len(docs)} DocumentReference(s); skipped {skipped_no_content} without accessible content.")
                    with st.expander("Debug details"):
                        st.json({
                            "patient_id": patient_hint,
                            "base_url": st.session_state.get('fhir_base_url'),
                            "since": since or None,
                            "skip_binary": skip_binary,
                            "scopes": st.session_state.get('fhir_scopes'),
                            "doc_count": len(docs),
                        })
                st.session_state['data_imported'] = True
            except Exception as e:
                tb = traceback.format_exc()
                st.error(f"FHIR import failed: {e}")
                with st.expander("Error details"):
                    st.code(tb)
    

# Add a button to navigate to the MyChart Explorer page
if st.session_state.get('data_imported', False):
    # If data has been imported, show a button to go to the explorer
    if st.button("Explore Your Data", key="explore_data_button"):
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
            key="persistent_error_log_dl",
        )

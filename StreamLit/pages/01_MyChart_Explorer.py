# This is the main page of the MyChart Explorer app.
# It allows users to ask questions about their health data.

# Import necessary libraries
import streamlit as st
import re
st.set_page_config(page_title="MyChart Explorer", layout="wide")
from modules.database import get_session, get_db_engine
from modules.llm_service import LLMService
from modules.conversations import list_conversations, save_conversation, load_conversation, delete_conversation
from modules.config import load_configuration, save_configuration
from modules.auth import check_auth

# Check user authentication
check_auth()

# Set the title of the page
st.title("MyChart Explorer")

# Load persisted configuration into session state
load_configuration()

# Check if data has been imported
if not st.session_state.get('data_imported', False):
    # If data has not been imported, show a warning and a link to the importer page
    st.warning("No data imported yet. Please import your MyChart data first.")
    st.page_link("pages/03_Data_Importer.py", label="Go to Data Importer")
else:
    # If data has been imported, show the conversational explorer
    db_path = st.session_state.get('db_path', 'mychart.db')
    engine = get_db_engine(db_path, key=st.session_state.get('db_encryption_key'))
    session = get_session(engine)
    llm_service = LLMService(db_engine=engine)

    # Initialize chat history and last retrieval in session_state
    st.session_state.setdefault('chat_history', [])  # list of {role, content}
    st.session_state.setdefault('last_sql', None)
    st.session_state.setdefault('last_rows', None)
    st.session_state.setdefault('last_batch', None)  # list of {sql, rows, error}
    st.session_state.setdefault('pending_question', None)
    st.session_state.setdefault('consult_ready', False)
    st.session_state.setdefault('should_start_retrieval', False)
    st.session_state.setdefault('retrieval_in_progress', False)

    # Sidebar: conversation management and backend selection
    with st.sidebar:
        st.subheader("LLM Backend")

        # Ensure llm_provider exists in session_state before rendering widget
        if "llm_provider" not in st.session_state:
            st.session_state["llm_provider"] = "ollama"

        # Determine configuration status for each backend from current session config
        ollama_ok = bool(st.session_state.get("ollama_url")) and bool(st.session_state.get("ollama_model"))
        gemini_ok = bool(st.session_state.get("gemini_api_key")) and bool(st.session_state.get("gemini_model"))

        # If current selection isn't configured, fall back to the first configured option
        if st.session_state["llm_provider"] == "ollama" and not ollama_ok:
            st.session_state["llm_provider"] = "gemini" if gemini_ok else "ollama"
        if st.session_state["llm_provider"] == "gemini" and not gemini_ok:
            st.session_state["llm_provider"] = "ollama" if ollama_ok else "gemini"

        # Remember previous (valid) selection to restore if user clicks an unavailable option
        st.session_state["_prev_llm_provider"] = st.session_state.get("llm_provider", "ollama")

        # Callback to persist selection without touching widget keys
        def _persist_backend_choice():
            sel = st.session_state.get("llm_provider")
            # If user selected an unconfigured backend, revert and notify
            if sel == "ollama" and not ollama_ok:
                st.session_state["llm_provider"] = st.session_state.get("_prev_llm_provider", "gemini" if gemini_ok else "ollama")
                st.warning("Ollama isn't configured yet. Set it up in Settings.")
                return
            if sel == "gemini" and not gemini_ok:
                st.session_state["llm_provider"] = st.session_state.get("_prev_llm_provider", "ollama" if ollama_ok else "gemini")
                st.warning("Gemini isn't configured yet. Add your API key in Settings.")
                return
            # Persist only the valid provider; avoid mutating unrelated widget state
            save_configuration({"llm_provider": st.session_state["llm_provider"]})
            st.session_state["_prev_llm_provider"] = st.session_state["llm_provider"]
            # A toast is fine; Streamlit reruns after callbacks automatically
            st.toast(f"Backend: {st.session_state['llm_provider'].capitalize()}")

        # Bind widget directly to session_state key to avoid index/default clashes
        disabled_all = not (ollama_ok or gemini_ok)
        st.radio(
            "Choose a backend:",
            ("ollama", "gemini"),
            key="llm_provider",
            format_func=lambda x: (
                "Ollama (configured)" if x == "ollama" and ollama_ok else
                "Ollama (needs setup)" if x == "ollama" else
                "Gemini (configured)" if x == "gemini" and gemini_ok else
                "Gemini (needs setup)"
            ),
            on_change=_persist_backend_choice,
            disabled=disabled_all,
            help=(
                "Configure backends on the Settings page. "
                "Options marked 'needs setup' can't be selected until configured."
            ),
        )

        if disabled_all:
            st.info("No LLM backends are configured yet. Please configure one in Settings.")
            st.page_link("pages/04_Settings.py", label="Open Settings")

        st.markdown("---")

        st.subheader("Conversations")
        
        username = st.session_state.get("username")
        key = st.session_state.get("db_encryption_key")

        if not (username and key):
            st.warning("Login required to manage conversations.")
            convs = []
        else:
            convs = list_conversations(username, key)

        options = [f"{c['title']} ({c['id']})" for c in convs]
        selected = st.selectbox("Load a conversation", options=options, index=None, placeholder="Select…")
        
        if selected:
            # Extract id from trailing parentheses
            sel_id = selected.split("(")[-1].rstrip(")")
            data = load_conversation(sel_id, username, key)
            if data and data.get("messages"):
                st.session_state['chat_history'] = data["messages"]
                st.session_state['last_sql'] = None
                st.session_state['last_rows'] = None
                st.session_state['pending_question'] = None
                st.session_state['consult_ready'] = False
                st.success("Conversation loaded.")
        
        with st.form("save_conv_form", clear_on_submit=True):
            title = st.text_input("Title", value="")
            save_clicked = st.form_submit_button("Save conversation")
            if save_clicked:
                if st.session_state['chat_history'] and username and key:
                    conv_id = save_conversation(st.session_state['chat_history'], username, key, title=title or None)
                    st.success(f"Saved as {conv_id}")
                    st.rerun()
                elif not (username and key):
                    st.error("You must be logged in to save conversations.")
                else:
                    st.info("Nothing to save yet.")
        
        # Delete helper
        if convs:
            del_choice = st.selectbox("Delete conversation", options=["—"] + [c['id'] for c in convs], index=0)
            if del_choice and del_choice != "—":
                if st.button("Delete selected"):
                    if username:
                        delete_conversation(del_choice, username)
                        st.rerun()
                    else:
                        st.error("You must be logged in to delete conversations.")

    # Defer retrieval to the next rerun so the just-typed user message is visible immediately
    if (st.session_state.get('should_start_retrieval') and
        st.session_state.get('pending_question') and
        not st.session_state.get('retrieval_in_progress')):
        st.session_state['retrieval_in_progress'] = True
        st.session_state['should_start_retrieval'] = False
        try:
            with st.spinner("Retrieving data…"):
                batch = llm_service.retrieve_batch(st.session_state['pending_question'], max_queries=4, max_retries=1)
                st.session_state['last_batch'] = batch
                first_ok = next((r for r in batch if r.get('rows')), None) if batch else None
                st.session_state['last_sql'] = first_ok.get('sql') if first_ok else None
                st.session_state['last_rows'] = first_ok.get('rows') if first_ok else None
                st.session_state['consult_ready'] = True
        except Exception as e:
            st.error(f"An error occurred while retrieving data: {e}")
        finally:
            st.session_state['retrieval_in_progress'] = False

    # Two-tab layout: Conversation and Retrieved Data
    tab_conv, tab_data = st.tabs(["Conversation", "Retrieved Data"])

    with tab_conv:
        st.subheader("Conversation")
        # Render history
        for msg in st.session_state['chat_history']:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])

        # Input
        user_input = st.chat_input("Ask about your health data…")
        if user_input:
            # Stage the question and rerun so the message is visible before retrieval starts
            st.session_state['pending_question'] = user_input
            st.session_state['last_sql'] = None
            st.session_state['last_rows'] = None
            st.session_state['last_batch'] = None
            st.session_state['consult_ready'] = False
            st.session_state['chat_history'].append({"role": "user", "content": user_input})
            st.session_state['should_start_retrieval'] = True
            st.rerun()

        # Controls
        col1_a, col1_b = st.columns(2)
        with col1_a:
            if st.button("Reset conversation"):
                st.session_state['chat_history'] = []
                st.session_state['last_sql'] = None
                st.session_state['last_rows'] = None
                st.session_state['last_batch'] = None
                st.session_state['pending_question'] = None
                st.session_state['consult_ready'] = False
                st.rerun()

        with col1_b:
            # Offer Consult action when rows are ready
            if st.session_state.get('consult_ready') and st.session_state.get('pending_question'):
                if st.button("Consult", type="primary", key="consult_btn"):
                    try:
                        with st.spinner("Consulting…"):
                            rows_list = []
                            if st.session_state.get('last_batch'):
                                rows_list = [item.get('rows', []) for item in st.session_state['last_batch']]
                            else:
                                rows_list = [st.session_state.get('last_rows') or []]
                            answer = llm_service.consult_multi(st.session_state['pending_question'], rows_list)
                        st.session_state['chat_history'].append({"role": "assistant", "content": answer})
                        # Clear pending state but keep last retrieval visible in the other tab
                        st.session_state['pending_question'] = None
                        st.session_state['consult_ready'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred during consultation: {e}")

    with tab_data:
        # Patient context
        with st.container(border=True):
            st.subheader("Patient Context")
            ctx = llm_service.get_patient_context()
            if ctx:
                info_col1, info_col2 = st.columns(2)
                info_col1.metric("Age", ctx.get("age", "—"))
                info_col2.metric("Gender", ctx.get("gender", "—"))
                info_col1.metric("Race", ctx.get("race", "—"))
                info_col2.metric("Ethnicity", ctx.get("ethnicity", "—"))
                st.metric("DOB", ctx.get("dob", "—"))
            else:
                st.caption("No demographics available.")

        st.markdown("---")
        st.subheader("Retrieved Data")
        batch = st.session_state.get('last_batch')

        if batch:
            tab_labels = []
            for idx, item in enumerate(batch):
                rows = item.get('rows', [])
                error = item.get('error')
                table_name = "Data"
                if item.get('sql'):
                    match = re.search(r"FROM\s+(\w+)", item['sql'], re.IGNORECASE)
                    if match:
                        table_name = match.group(1).capitalize()
                label = f"{table_name} (Error)" if error else f"{table_name} ({len(rows)})"
                tab_labels.append(label)

            tabs = st.tabs(tab_labels)
            for i, tab in enumerate(tabs):
                with tab:
                    item = batch[i]
                    sql = item.get('sql')
                    rows = item.get('rows') or []
                    error = item.get('error')

                    if error:
                        st.error(f"An error occurred in this query:\n\n{error}")
                    elif rows:
                        try:
                            import pandas as pd
                            if hasattr(rows[0], "_mapping"):
                                cols = list(rows[0]._mapping.keys())
                                data = [tuple(r) for r in rows]
                                df = pd.DataFrame(data, columns=cols)
                            else:
                                df = pd.DataFrame([tuple(r) for r in rows])
                            st.dataframe(df, use_container_width=True)
                        except Exception as e:
                            st.text("\n".join(str(r) for r in rows[:50]))
                            st.error(f"Could not render DataFrame: {e}")
                    else:
                        st.caption("No rows returned for this query.")

                    if sql:
                        with st.expander("View SQL Query"):
                            st.code(sql, language="sql")
        else:
            st.info("No data retrieved yet. Ask a question to see relevant records.")

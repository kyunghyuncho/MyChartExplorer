# This is the main page of the MyChart Explorer app.
# It allows users to ask questions about their health data.

# Import necessary libraries
import streamlit as st
import streamlit.components.v1 as components
import re
import time
st.set_page_config(page_title="MyChart Explorer", layout="wide")
from modules.database import get_session, get_db_engine
from modules.llm_service import LLMService
from modules.conversations import list_conversations, save_conversation, load_conversation, delete_conversation
from modules.config import load_configuration, save_configuration
from modules.auth import check_auth
from modules.ui import render_footer

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
    # Keep a cumulative history of retrieved rows across the conversation
    st.session_state.setdefault('rows_history', [])  # list[list[row]]
    # Persist successful SQL statements to allow reconstruction when loading a saved conversation
    st.session_state.setdefault('sql_history', [])  # list[str]
    # Retrieval progress messages for the current question
    st.session_state.setdefault('progress_msgs', [])
    # Per-turn retrieval token guard
    st.session_state.setdefault('retrieval_token', 0)
    st.session_state.setdefault('retrieval_processed_token', 0)
    # UI: whether to scroll to the last assistant message on rerun
    st.session_state.setdefault('scroll_to_last_assistant', False)

    # Sidebar: conversation management and backend selection
    with st.sidebar:
        st.subheader("LLM Backend")

        # Ensure llm_provider exists in session_state before rendering widget
        if "llm_provider" not in st.session_state:
            st.session_state["llm_provider"] = "gemini"

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

        # Auto-consult toggle (persisted)
        st.subheader("Behavior")
        st.session_state.setdefault("auto_consult", st.session_state.get("auto_consult", True))
        prev_auto = bool(st.session_state.get("auto_consult", True))
        auto_on = st.checkbox("Automatically consult after retrieval", value=prev_auto, help="When enabled, the assistant will respond immediately after data is retrieved.")
        if auto_on != prev_auto:
            st.session_state["auto_consult"] = auto_on
            # Persist to config
            save_configuration({"auto_consult": auto_on})

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
                st.session_state['last_batch'] = None
                st.session_state['rows_history'] = []
                # Restore saved SQL history (if available) and rebuild rows for context
                st.session_state['sql_history'] = data.get('sql_history', [])
                rebuilt = 0
                if st.session_state['sql_history']:
                    with st.spinner("Rebuilding retrieved data from saved SQL…"):
                        for _sql in st.session_state['sql_history']:
                            try:
                                clean = llm_service._sanitize_sql(_sql)
                                clean = llm_service._inline_patient_id(clean)
                                if not clean:
                                    continue
                                rows = llm_service.execute_sql(clean)
                                if rows:
                                    st.session_state['rows_history'].append(rows)
                                    rebuilt += 1
                            except Exception:
                                continue
                st.success("Conversation loaded.")
                if rebuilt:
                    st.caption(f"Restored {rebuilt} data set(s) for context.")
                # After loading, position the view at the last assistant message (if any)
                st.session_state['scroll_to_last_assistant'] = True
        
        with st.form("save_conv_form", clear_on_submit=True):
            title = st.text_input("Title", value="")
            save_clicked = st.form_submit_button("Save conversation")
            if save_clicked:
                if st.session_state['chat_history'] and username and key:
                    conv_id = save_conversation(
                        st.session_state['chat_history'],
                        username,
                        key,
                        title=title or None,
                        sql_history=st.session_state.get('sql_history') or [],
                    )
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

    # Note: Retrieval is now executed inline under the last user message in the Conversation tab

    # Two-tab layout: Conversation and Retrieved Data
    tab_conv, tab_data = st.tabs(["Conversation", "Retrieved Data"])

    with tab_conv:
        st.subheader("Conversation")
        # Render history with anchor ids for assistant messages
        last_assistant_anchor = None
        chat_hist = st.session_state['chat_history']
        # Determine the latest user message index (to attach progress under it)
        last_user_idx = None
        for _i in range(len(chat_hist) - 1, -1, -1):
            if chat_hist[_i].get('role') == 'user':
                last_user_idx = _i
                break

        prog = st.session_state.get('progress_msgs') or []

        for i, msg in enumerate(chat_hist):
            role = msg.get('role', 'user')
            # Inject a small anchor before assistant messages to allow scrolling
            if role == 'assistant':
                anchor_id = f"assistant-msg-{i}"
                # invisible anchor
                st.markdown(f'<a id="{anchor_id}"></a>', unsafe_allow_html=True)
                last_assistant_anchor = anchor_id
            with st.chat_message(role):
                # Prepend a small, styled disclaimer for assistant responses
                if role == 'assistant':
                    st.markdown(
                        (
                            "<div style=\"font-size:0.85rem; line-height:1.25rem; color:#7c2d12; "
                            "background:#fff7ed; border:1px solid #fdba74; padding:8px 10px; "
                            "border-radius:8px; margin:0 0 6px 0;\">"
                            "<strong>Not medical advice:</strong> The assistant's response is for informational purposes only. "
                            "Always consult a qualified clinician for medical advice."
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
                st.markdown(msg.get('content', ''))
                # If this is the most recent user message, show the current progress right after it
                if last_user_idx is not None and i == last_user_idx:
                    # Create a live placeholder for progress messages directly under the user message
                    progress_box = st.empty()

                    def _esc_html2(s: str) -> str:
                        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

                    def _render_progress_list(items_list: list[str]):
                        if not items_list:
                            progress_box.empty()
                            return
                        items_html = "".join(f"<li><span style='color:#6b7280;'>{_esc_html2(m)}</span></li>" for m in items_list)
                        progress_box.markdown(
                            f"<ul style='margin:0.25rem 0 0.5rem 1.25rem;padding:0;'>{items_html}</ul>",
                            unsafe_allow_html=True,
                        )
                        # Brief sleep to allow Streamlit UI to paint incrementally
                        time.sleep(0.03)

                    # If a retrieval is queued, run it now and stream progress in real time
                    if (st.session_state.get('should_start_retrieval') and
                        st.session_state.get('pending_question') and
                        not st.session_state.get('retrieval_in_progress') and
                        int(st.session_state.get('retrieval_token', 0)) != int(st.session_state.get('retrieval_processed_token', 0))):
                        st.session_state['retrieval_in_progress'] = True
                        st.session_state['should_start_retrieval'] = False
                        # Consume token to avoid duplicate runs for this turn
                        try:
                            st.session_state['retrieval_processed_token'] = int(st.session_state.get('retrieval_token', 0))
                        except Exception:
                            st.session_state['retrieval_processed_token'] = st.session_state.get('retrieval_token')
                        # Reset progress for this turn
                        st.session_state['progress_msgs'] = []

                        def _progress(msg: str):
                            st.session_state['progress_msgs'].append(str(msg))
                            _render_progress_list(st.session_state['progress_msgs'])

                        try:
                            _progress("Starting retrieval…")
                            batch = llm_service.retrieve_batch(
                                st.session_state['pending_question'],
                                max_queries=4,
                                max_retries=1,
                                progress_cb=_progress,
                                chat_history=st.session_state.get('chat_history')
                            )
                            st.session_state['last_batch'] = batch
                            first_ok = next((r for r in batch if r.get('rows')), None) if batch else None
                            st.session_state['last_sql'] = first_ok.get('sql') if first_ok else None
                            st.session_state['last_rows'] = first_ok.get('rows') if first_ok else None
                            st.session_state['consult_ready'] = True
                            # Append successful rows and SQL to histories
                            try:
                                for item2 in (batch or []):
                                    rows2 = item2.get('rows') or []
                                    if rows2:
                                        st.session_state['rows_history'].append(rows2)
                                        sql2 = item2.get('sql')
                                        if sql2:
                                            st.session_state['sql_history'].append(sql2)
                            except Exception:
                                pass
                            # Optionally consult immediately
                            if st.session_state.get('auto_consult', True) and st.session_state.get('pending_question'):
                                try:
                                    rows_history = st.session_state.get('rows_history') or []
                                    # Show a spinner while the LLM composes its reply
                                    with st.spinner("Thinking …"):
                                        answer = llm_service.consult_conversation(st.session_state['chat_history'], rows_history)
                                    st.session_state['chat_history'].append({"role": "assistant", "content": answer})
                                    st.session_state['scroll_to_last_assistant'] = True
                                    st.session_state['pending_question'] = None
                                    st.session_state['consult_ready'] = False
                                except Exception as e:
                                    st.error(f"An error occurred during consultation: {e}")
                        except Exception as e:
                            st.error(f"An error occurred while retrieving data: {e}")
                        finally:
                            st.session_state['retrieval_in_progress'] = False

                    # Always render any existing progress list (will be updated live during retrieval)
                    prog = st.session_state.get('progress_msgs') or []
                    _render_progress_list(prog)

        # If requested, scroll to the last assistant anchor after render
        if st.session_state.get('scroll_to_last_assistant') and last_assistant_anchor:
            components.html(
                f"""
                <script>
                const el = document.getElementById('{last_assistant_anchor}');
                if (el) {{ el.scrollIntoView({{ behavior: 'smooth', block: 'center' }}); }}
                </script>
                """,
                height=0,
            )
            # Reset the flag
            st.session_state['scroll_to_last_assistant'] = False

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
            # Increment per-turn token to signal new retrieval
            try:
                st.session_state['retrieval_token'] = int(st.session_state.get('retrieval_token', 0)) + 1
            except Exception:
                st.session_state['retrieval_token'] = 1
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
                st.session_state['rows_history'] = []
                st.session_state['sql_history'] = []
                st.rerun()

        with col1_b:
            # Offer Consult action when rows are ready
            if st.session_state.get('consult_ready') and st.session_state.get('pending_question'):
                if st.button("Consult", type="primary", key="consult_btn"):
                    try:
                        # Show a spinner while the LLM composes its reply
                        with st.spinner("Thinking …"):
                            # Use the full chat history and all retrieved data so far
                            rows_history = st.session_state.get('rows_history') or []
                            answer = llm_service.consult_conversation(st.session_state['chat_history'], rows_history)
                        st.session_state['chat_history'].append({"role": "assistant", "content": answer})
                        # Ask UI to scroll to the latest assistant message
                        st.session_state['scroll_to_last_assistant'] = True
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
                # Prefer a human-friendly description of the SQL
                sql = item.get('sql') or ""
                try:
                    desc = llm_service.describe_sql(sql).strip()
                except Exception:
                    desc = "Retrieved data"
                base = desc if desc else "Retrieved data"
                label = f"{base} (Error)" if error else f"{base} ({len(rows)})"
                # Keep labels reasonably short for tabs
                if len(label) > 70:
                    label = label[:67] + "…"
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

    render_footer()

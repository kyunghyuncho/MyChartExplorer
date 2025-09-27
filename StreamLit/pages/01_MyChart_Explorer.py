# This is the main page of the MyChart Explorer app.
# It allows users to ask questions about their health data.

# Import necessary libraries
import streamlit as st
st.set_page_config(page_title="MyChart Explorer", layout="wide")
from modules.database import get_session, get_db_engine
from modules.llm_service import LLMService
from modules.conversations import list_conversations, save_conversation, load_conversation, delete_conversation
from modules.config import load_configuration

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
    engine = get_db_engine(db_path)
    session = get_session(engine)
    llm_service = LLMService(db_engine=engine)

    # Initialize chat history and last retrieval in session_state
    st.session_state.setdefault('chat_history', [])  # list of {role, content}
    st.session_state.setdefault('last_sql', None)
    st.session_state.setdefault('last_rows', None)
    st.session_state.setdefault('last_batch', None)  # list of {sql, rows, error}
    st.session_state.setdefault('pending_question', None)
    st.session_state.setdefault('consult_ready', False)

    # Sidebar: conversation management
    with st.sidebar:
        st.subheader("Conversations")
        convs = list_conversations()
        options = [f"{c['title']} ({c['id']})" for c in convs]
        selected = st.selectbox("Load a conversation", options=options, index=None, placeholder="Select…")
        if selected:
            # Extract id from trailing parentheses
            sel_id = selected.split("(")[-1].rstrip(")")
            data = load_conversation(sel_id)
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
                if st.session_state['chat_history']:
                    conv_id = save_conversation(st.session_state['chat_history'], title=title or None)
                    st.success(f"Saved as {conv_id}")
                else:
                    st.info("Nothing to save yet.")
        # Delete helper
        if convs:
            del_choice = st.selectbox("Delete conversation", options=["—"] + [c['id'] for c in convs], index=0)
            if del_choice and del_choice != "—":
                if st.button("Delete selected"):
                    delete_conversation(del_choice)
                    st.experimental_rerun()

    # Vertical split: Conversation (top) and Retrieved info (bottom)
    st.markdown("---")
    with st.container():
        # Top: conversation
        st.subheader("Conversation")
        # Render history
        for msg in st.session_state['chat_history']:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])
        
        # Input
        user_input = st.chat_input("Ask about your health data…")
        if user_input:
            # Treat any input as a new question (even if consult was ready)
            st.session_state['pending_question'] = user_input
            st.session_state['last_sql'] = None
            st.session_state['last_rows'] = None
            st.session_state['last_batch'] = None
            st.session_state['consult_ready'] = False
            # Add the user message to chat history
            st.session_state['chat_history'].append({"role": "user", "content": user_input})
            # Immediately start retrieval with a spinner
            try:
                with st.spinner("Retrieving data…"):
                    batch = llm_service.retrieve_batch(st.session_state['pending_question'], max_queries=4, max_retries=1)
                    st.session_state['last_batch'] = batch
                    # keep single fields for backward-compat with older UI bits
                    # choose the first successful result if any
                    first_ok = next((r for r in batch if r.get('rows')), None) if batch else None
                    st.session_state['last_sql'] = first_ok.get('sql') if first_ok else None
                    st.session_state['last_rows'] = first_ok.get('rows') if first_ok else None
                    st.session_state['consult_ready'] = True
            except Exception as e:
                st.error(f"An error occurred while retrieving data: {e}")
        
        # Only show Consult when we have retrieved data for a question
        # Reset conversation button
        if st.button("Reset conversation"):
            st.session_state['chat_history'] = []
            st.session_state['last_sql'] = None
            st.session_state['last_rows'] = None
            st.session_state['last_batch'] = None
            st.session_state['pending_question'] = None
            st.session_state['consult_ready'] = False
            st.rerun()
        
        # Offer Consult action when rows are ready
        if st.session_state.get('consult_ready') and st.session_state.get('pending_question'):
            # Single Consult action (button only)
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
                    # Clear pending state but keep last retrieval visible in the bottom panel
                    st.session_state['pending_question'] = None
                    st.session_state['consult_ready'] = False
                    st.rerun()
                except Exception as e:
                    st.error(f"An error occurred during consultation: {e}")
    
    # Bottom: retrieved data panel
    st.markdown("---")
    with st.container():
        st.subheader("Patient context")
        ctx = llm_service.get_patient_context()
        if ctx:
            # Two rows of simple metrics
            cols_top = st.columns(3)
            cols_top[0].metric("Age", ctx.get("age", "—"))
            cols_top[1].metric("Gender", ctx.get("gender", "—"))
            cols_top[2].metric("DOB", ctx.get("dob", "—"))
    
            cols_bottom = st.columns(3)
            cols_bottom[0].metric("Race", ctx.get("race", "—"))
            cols_bottom[1].metric("Ethnicity", ctx.get("ethnicity", "—"))
            cols_bottom[2].metric("Deceased", "Yes" if ctx.get("deceased") else "No")
        else:
            st.caption("No demographics available.")
    
        # Retrieved data preview
        st.subheader("Retrieved data preview")
        batch = st.session_state.get('last_batch')
        if batch:
            for idx, item in enumerate(batch, start=1):
                sql = item.get('sql')
                rows = item.get('rows') or []
                error = item.get('error')
                title = f"Query {idx} — {len(rows)} row(s)" if not error else f"Query {idx} — error"
                with st.expander(title, expanded=False):
                    if sql:
                        st.code(sql, language="sql")
                    if error:
                        st.error(error)
                    elif rows:
                        try:
                            import pandas as pd
                            if hasattr(rows[0], "_mapping"):
                                cols = list(rows[0]._mapping.keys())
                                data = [tuple(r) for r in rows]
                                df = pd.DataFrame(data, columns=cols)
                            else:
                                df = pd.DataFrame([tuple(r) for r in rows])
                            st.dataframe(df, use_container_width=True, height=300)
                        except Exception:
                            st.text("\n".join(str(r) for r in rows[:50]))
                    else:
                        st.caption("No rows.")
        else:
            st.info("No data retrieved yet. Ask a question above to preview relevant records, then press Consult.")

    # end of vertical split

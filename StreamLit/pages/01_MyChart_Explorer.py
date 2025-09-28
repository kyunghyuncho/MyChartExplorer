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

    # Sidebar: conversation management and backend selection
    with st.sidebar:
        st.subheader("LLM Backend")

        # Ensure llm_provider exists in session_state before rendering widget
        if "llm_provider" not in st.session_state:
            st.session_state["llm_provider"] = "ollama"

        # Callback to persist selection without touching widget keys
        def _persist_backend_choice():
            # Persist only the provider; avoid mutating unrelated widget state
            save_configuration({"llm_provider": st.session_state["llm_provider"]})
            # A toast is fine; Streamlit reruns after callbacks automatically
            st.toast(f"Backend: {st.session_state['llm_provider'].capitalize()}")

        # Bind widget directly to session_state key to avoid index/default clashes
        st.radio(
            "Choose a backend:",
            ("ollama", "gemini"),
            key="llm_provider",
            on_change=_persist_backend_choice,
        )

        st.markdown("---")

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
                    st.rerun()

    # Two-column layout: Conversation (left) and Sticky info panel (right)
    
    # Inject CSS to make the right column sticky
    st.markdown("""
    <style>
    /* Target the second column (right panel) and make it sticky */
    .block-container .element-container:has([data-testid="column"]:nth-child(2)) [data-testid="column"]:nth-child(2) {
        position: sticky !important;
        top: 50px !important;
        height: calc(100vh - 100px) !important;
        overflow-y: auto !important;
        padding-right: 1rem !important;
        border-left: 1px solid #e6e6e6 !important;
        padding-left: 1rem !important;
        background-color: white !important;
        z-index: 1 !important;
    }
    
    /* Alternative selector for broader compatibility */
    div[data-testid="column"]:nth-of-type(2) {
        position: sticky !important;
        top: 50px !important;
        height: calc(100vh - 100px) !important;
        overflow-y: auto !important;
        padding-right: 1rem !important;
        border-left: 1px solid #e6e6e6 !important;
        padding-left: 1rem !important;
        background-color: white !important;
        z-index: 1 !important;
    }
    
    /* More specific selector targeting columns within the main content */
    .main .block-container > div > div > div[data-testid="column"]:nth-child(2) {
        position: sticky !important;
        top: 50px !important;
        height: calc(100vh - 100px) !important;
        overflow-y: auto !important;
        padding-right: 1rem !important;
        border-left: 1px solid #e6e6e6 !important;
        padding-left: 1rem !important;
        background-color: white !important;
        z-index: 1 !important;
    }
    
    /* Ensure the main content area allows for proper scrolling */
    .main .block-container {
        padding-top: 2rem !important;
        max-width: 100% !important;
    }
    
    /* Ensure left column has proper spacing */
    div[data-testid="column"]:nth-of-type(1) {
        padding-right: 2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([7, 3])  # 70% left, 30% right
    
    with col1:
        # Left column: Conversation
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
                        # Clear pending state but keep last retrieval visible in the right panel
                        st.session_state['pending_question'] = None
                        st.session_state['consult_ready'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred during consultation: {e}")
    
    with col2:
        # Right column: A dashboard-style display for patient context and retrieved data.
        
        # --- Patient Information Card ---
        # This container provides a visually distinct "card" for key patient demographics.
        with st.container(border=True):
            st.subheader("Patient Context")
            ctx = llm_service.get_patient_context()
            if ctx:
                # Display demographics in a compact, two-column layout.
                info_col1, info_col2 = st.columns(2)
                info_col1.metric("Age", ctx.get("age", "—"))
                info_col2.metric("Gender", ctx.get("gender", "—"))
                info_col1.metric("Race", ctx.get("race", "—"))
                info_col2.metric("Ethnicity", ctx.get("ethnicity", "—"))
                st.metric("DOB", ctx.get("dob", "—"))
            else:
                st.caption("No demographics available.")

        st.markdown("---") # Visual separator

        # --- Tabbed Retrieved Data ---
        st.subheader("Retrieved Data")
        batch = st.session_state.get('last_batch')
        
        if batch:
            # Prepare tab labels with a summary of results.
            # Example: "Vitals (5 rows)" or "Meds (Error)"
            tab_labels = []
            for idx, item in enumerate(batch):
                rows = item.get('rows', [])
                error = item.get('error')
                # Try to infer a table name from the SQL for a more descriptive label.
                table_name = "Data"
                if item.get('sql'):
                    match = re.search(r"FROM\s+(\w+)", item['sql'], re.IGNORECASE)
                    if match:
                        table_name = match.group(1).capitalize()
                
                if error:
                    label = f"{table_name} (Error)"
                else:
                    label = f"{table_name} ({len(rows)})"
                tab_labels.append(label)

            # Create the tabs.
            tabs = st.tabs(tab_labels)
            
            # Populate each tab with the corresponding query result.
            for i, tab in enumerate(tabs):
                with tab:
                    item = batch[i]
                    sql = item.get('sql')
                    rows = item.get('rows') or []
                    error = item.get('error')

                    if error:
                        st.error(f"An error occurred in this query:\n\n{error}")
                    elif rows:
                        # Display the data table.
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

                    # Include the SQL query in a collapsible expander.
                    if sql:
                        with st.expander("View SQL Query"):
                            st.code(sql, language="sql")
        else:
            # Default message when no data has been retrieved yet.
            st.info("No data retrieved yet. Ask a question to see relevant records.")

# This is the main page of the MyChart Explorer app.
# It allows users to ask questions about their health data.

# Import necessary libraries
import streamlit as st
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

    left, right = st.columns([3, 2])

    # Left: conversation
    with left:
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
            st.session_state['consult_ready'] = False
            # Add the user message to chat history
            st.session_state['chat_history'].append({"role": "user", "content": user_input})
            # Immediately start retrieval with a spinner
            try:
                with st.spinner("Retrieving data…"):
                    sql_query, rows = llm_service.retrieve(st.session_state['pending_question'], max_retries=1)
                    st.session_state['last_sql'] = sql_query
                    st.session_state['last_rows'] = rows
                    st.session_state['consult_ready'] = True
            except Exception as e:
                st.error(f"An error occurred while retrieving data: {e}")

        # Only show Consult when we have retrieved data for a question
        # Reset conversation button
        if st.button("Reset conversation"):
            st.session_state['chat_history'] = []
            st.session_state['last_sql'] = None
            st.session_state['last_rows'] = None
            st.session_state['pending_question'] = None
            st.session_state['consult_ready'] = False

        # Offer Consult action when rows are ready
        if st.session_state.get('consult_ready') and st.session_state.get('pending_question'):
            # Button trigger
            consult_clicked = st.button("Consult", type="primary", key="consult_btn")

            # Enter trigger via a tiny form: hitting Enter submits and triggers consult
            with st.form("consult_form", clear_on_submit=True):
                _ = st.text_input("Press Enter to Consult or click Consult", value="", key="consult_enter", label_visibility="collapsed")
                submitted = st.form_submit_button("Consult")

            if consult_clicked or submitted:
                try:
                    with st.spinner("Consulting…"):
                        answer = llm_service.consult(st.session_state['pending_question'], st.session_state['last_rows'])
                    st.session_state['chat_history'].append({"role": "assistant", "content": answer})
                    # Clear pending state but keep last retrieval visible on the right
                    st.session_state['pending_question'] = None
                    st.session_state['consult_ready'] = False
                except Exception as e:
                    st.error(f"An error occurred during consultation: {e}")

    # Right: retrieved data panel (single well-indented block)
            with right:
                    # Make the actual right column sticky and scrollable
                    st.markdown(
                            """
                            <style>
                                /* Pin the 2nd column */
                                div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-of-type(2) {
                                    position: -webkit-sticky !important;
                                    position: sticky !important;
                                    top: 1rem !important;
                                    align-self: flex-start !important;
                                    z-index: 1;
                                }
                                /* Scroll inside the right column content when tall */
                                div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-of-type(2) > div {
                                    max-height: calc(100vh - 2rem) !important;
                                    overflow: auto !important;
                                }
                            </style>
                            """,
                            unsafe_allow_html=True,
                    )

                # 2) Patient context banner (always visible)
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

    # 3) Retrieved data preview
        st.subheader("Retrieved data preview")
        sql_shown = st.session_state.get('last_sql')
        rows = st.session_state.get('last_rows') or []

        # Show SQL used (collapsible)
        if sql_shown:
            with st.expander("SQL used", expanded=False):
                st.code(sql_shown, language="sql")

        # Render result table or fallback
        if rows:
            try:
                import pandas as pd
                # Try to extract column names using SQLAlchemy Row._mapping (Py3.8+)
                if hasattr(rows[0], "_mapping"):
                    cols = list(rows[0]._mapping.keys())
                    data = [tuple(r) for r in rows]
                    df = pd.DataFrame(data, columns=cols)
                else:
                    df = pd.DataFrame([tuple(r) for r in rows])
                st.caption(f"{len(df)} row(s)")
                st.dataframe(df, use_container_width=True, height=400)
            except Exception:
                st.caption(f"{len(rows)} row(s)")
                st.text("\n".join(str(r) for r in rows[:50]))
        else:
            st.info("No data retrieved yet. Ask a question on the left to preview relevant records, then press Consult.")

    # end right column

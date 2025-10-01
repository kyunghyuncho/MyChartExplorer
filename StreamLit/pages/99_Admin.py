import streamlit as st

from modules.auth import check_auth
from modules.admin import (
    list_users,
    search_users,
    is_superuser,
    set_superuser,
    reset_password,
    export_user_zip,
    delete_user_data,
    delete_user_account,
)
from modules.config import (
    get_preview_limits_global,
    set_preview_limits_global,
    get_notes_snippet_max_chars,
    set_notes_snippet_max_chars,
    get_notes_summarization_enabled,
    set_notes_summarization_enabled,
)
from modules.invitations import (
    invite_user,
    list_invitations,
    delete_invitation,
    get_sendgrid_api_key,
    set_sendgrid_api_key,
    send_invitation_email,
)


st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin Console")

# Require login
check_auth()
current_user = st.session_state.get("username")
if not current_user or not is_superuser(current_user):
    st.error("Admin access required.")
    st.stop()

st.success(f"Signed in as {st.session_state.get('name')} (superuser)")

# Tabs
tab_settings, tab_users, tab_invites = st.tabs(["Settings", "Users", "Invitations"])

with tab_settings:
    st.subheader("LLM Preview Settings")
    cur_rows, cur_budget, cur_sets = get_preview_limits_global()
    colp1, colp2, colp3 = st.columns(3)
    with colp1:
        rows = st.number_input("Max rows per set", min_value=1, max_value=100, value=int(cur_rows))
    with colp2:
        budget = st.number_input("Char budget per set", min_value=500, max_value=2000000, value=int(cur_budget), step=100)
    with colp3:
        sets = st.number_input("Max sets included", min_value=1, max_value=16, value=int(cur_sets))
    if st.button("Save Preview Settings"):
        set_preview_limits_global(rows, budget, sets)
        st.success("Preview settings saved.")

    st.markdown("---")
    st.subheader("Email (SendGrid)")
    sg = st.text_input("SendGrid API Key", type="password", value=get_sendgrid_api_key())
    if st.button("Save SendGrid Key"):
        set_sendgrid_api_key(sg)
        st.success("SendGrid API key saved.")

    st.markdown("---")
    st.subheader("Notes Preview & Summarization")
    coln1, coln2 = st.columns([1, 1])
    with coln1:
        snip_max = st.number_input(
            "Max characters for note text",
            min_value=100,
            max_value=100000,
            value=int(get_notes_snippet_max_chars()),
            step=100,
            help="Controls how much note content is included per row in previews sent to the LLM.",
        )
    with coln2:
        summarize = st.toggle(
            "Summarize long notes",
            value=bool(get_notes_summarization_enabled()),
            help="When enabled, the app may summarize longer note excerpts to fit within preview budgets.",
        )
    if st.button("Save Notes Settings"):
        set_notes_snippet_max_chars(int(snip_max))
        set_notes_summarization_enabled(bool(summarize))
        st.success("Notes settings saved.")

with tab_users:
    st.subheader("Users")
    # Confirmation state for destructive actions
    st.session_state.setdefault("confirm_delete_user", None)
    st.session_state.setdefault("confirm_delete_scope", None)  # 'account' | 'data'
    # Search controls
    search_q = st.text_input("Search by username, name, or email", placeholder="Type to filter users…")
    rows = search_users(search_q) if search_q else list_users()
    if not rows:
        st.info("No users found.")
    else:
        # Pagination controls
        colu1, colu2, colu3 = st.columns([1, 1, 6])
        page_size = colu1.selectbox("Page size", [5, 10, 20, 50], index=1, key="users_page_size")
        total = len(rows)
        max_page = max(1, (total + page_size - 1) // page_size)
        page = colu2.number_input("Page", min_value=1, max_value=max_page, value=1, step=1, key="users_page")
        start = (page - 1) * page_size
        end = min(total, start + page_size)
        st.caption(f"Showing users {start+1}–{end} of {total}")

        for uname, data in rows[start:end]:
            with st.expander(f"{uname}"):
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
                with col1:
                    st.write(f"Name: {data.get('name', '-')}")
                    st.write(f"Email: {data.get('email', '-')}")
                    st.write(f"Superuser: {bool(data.get('superuser', False))}")
                with col2:
                    make_su = st.toggle("Superuser", value=bool(data.get('superuser', False)), key=f"su-{uname}")
                    if st.button("Apply Role", key=f"apply-su-{uname}"):
                        set_superuser(uname, make_su)
                        st.success("Role updated.")
                with col3:
                    if st.button("Reset Password", key=f"reset-{uname}"):
                        try:
                            temp = reset_password(uname)
                            st.code(temp, language=None)
                            st.info("Share this temporary password securely with the user. They should change it after login.")
                        except Exception as e:
                            st.error(str(e))
                with col4:
                    mode = st.radio(
                        "Export Mode",
                        options=["encrypted", "decrypted"],
                        horizontal=True,
                        key=f"mode-{uname}"
                    )
                    include_key = st.checkbox("Include key.txt (encrypted mode)", key=f"key-{uname}")
                    if include_key:
                        st.warning("This includes the user's DB/conversation key inside the ZIP. Share only with the verified account owner.")
                    if st.button("Export Data (ZIP)", key=f"export-{uname}"):
                        try:
                            data_bytes = export_user_zip(uname, mode=mode, include_key=include_key)
                            st.download_button(
                                label="Download ZIP",
                                data=data_bytes,
                                file_name=f"{uname}_mychart_{mode}.zip",
                                mime="application/zip",
                                key=f"dl-{uname}"
                            )
                        except Exception as e:
                            st.error(str(e))
                with col5:
                    danger = st.checkbox("I understand delete is permanent", key=f"danger-{uname}")
                    st.caption("Choose what to delete:")
                    col_del1, col_del2 = st.columns(2)
                    with col_del1:
                        if st.button("Delete Data Only", key=f"delete-data-{uname}"):
                            if danger:
                                try:
                                    delete_user_data(uname)
                                    st.warning("User data deleted (account retained).")
                                except Exception as e:
                                    st.error(str(e))
                            else:
                                st.error("Please confirm the checkbox before deleting.")
                    with col_del2:
                        if st.button("Delete Account", key=f"delete-acct-{uname}"):
                            if danger:
                                # Stage confirmation dialog for this user
                                st.session_state["confirm_delete_user"] = uname
                                st.session_state["confirm_delete_scope"] = "account"
                            else:
                                st.error("Please confirm the checkbox before deleting.")

                    # Second confirmation dialog (inline) for account deletion
                    if (
                        st.session_state.get("confirm_delete_user") == uname
                        and st.session_state.get("confirm_delete_scope") == "account"
                    ):
                        with st.container(border=True):
                            st.error("This will permanently delete the user's account and all associated data.")
                            confirm_text = st.text_input(
                                "Type the username to confirm deletion",
                                key=f"confirm-text-{uname}",
                                placeholder=uname,
                            )
                            cc1, cc2 = st.columns(2)
                            with cc1:
                                if st.button("Confirm Delete Account", key=f"confirm-delete-{uname}"):
                                    if confirm_text.strip() == uname:
                                        try:
                                            delete_user_account(uname)
                                            st.success("User account deleted.")
                                            st.session_state["confirm_delete_user"] = None
                                            st.session_state["confirm_delete_scope"] = None
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))
                                    else:
                                        st.error("Username does not match. Please type the exact username.")
                            with cc2:
                                if st.button("Cancel", key=f"cancel-delete-{uname}"):
                                    st.session_state["confirm_delete_user"] = None
                                    st.session_state["confirm_delete_scope"] = None
                                    st.rerun()

with tab_invites:
    st.subheader("Invite a new user")
    col_i1, col_i2 = st.columns([3, 2])
    with col_i1:
        email = st.text_input("Email to invite", key="invite_email")
    with col_i2:
        app_url = st.text_input("App URL (optional)", placeholder="https://your-app.example.com")
    if st.button("Send Invitation"):
        try:
            rec, msg = invite_user(email, inviter_name=st.session_state.get("name"), app_url=app_url)
            st.success(msg)
            with st.expander("Invitation Details"):
                st.write({k: v for k, v in rec.items() if k != 'code'})
                st.code(rec.get("code", ""), language=None)
                st.caption("This code is also emailed. You can copy it if needed.")
        except Exception as e:
            st.error(str(e))

    st.markdown("---")
    st.subheader("Pending invitations")
    # Pagination for pending list
    colp1, colp2, colp3 = st.columns([1, 1, 6])
    inv_page_size = colp1.selectbox("Page size", [5, 10, 20, 50], index=1, key="inv_page_size")
    # Fetch to compute max pages
    subset, total = list_invitations(pending_only=True, page=1, page_size=99999)
    inv_max_page = max(1, (total + inv_page_size - 1) // inv_page_size)
    inv_page = colp2.number_input("Page", min_value=1, max_value=inv_max_page, value=1, step=1, key="inv_page")
    inv_subset, inv_total = list_invitations(pending_only=True, page=int(inv_page), page_size=int(inv_page_size))
    st.caption(f"Showing {len(inv_subset)} of {inv_total} pending")

    for it in inv_subset:
        with st.expander(f"{it.get('email')} — code: {it.get('code')}"):
            st.write({k: it[k] for k in ["email", "created_at", "expires_at", "used"] if k in it})
            colx1, colx2 = st.columns([1, 1])
            if colx1.button("Delete", key=f"del-inv-{it.get('code')}"):
                if delete_invitation(it.get("code", "")):
                    st.warning("Invitation deleted.")
                else:
                    st.error("Failed to delete.")
            if colx2.button("Resend Email", key=f"resend-inv-{it.get('code')}"):
                ok, msg = send_invitation_email(it.get("email", ""), it.get("code", ""), inviter_name=st.session_state.get("name"))
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

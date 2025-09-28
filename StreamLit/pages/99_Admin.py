import streamlit as st

from modules.auth import check_auth
from modules.admin import (
    list_users,
    is_superuser,
    set_superuser,
    reset_password,
    export_user_zip,
    delete_user_data,
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

st.subheader("Users")
rows = list_users()
if not rows:
    st.info("No users found.")
else:
    for uname, data in rows:
        with st.expander(f"{uname}"):
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
            with col1:
                st.write(f"Name: {data.get('name', '-')}")
                st.write(f"Email: {data.get('email', '-')}")
                st.write(f"Superuser: {bool(data.get('superuser', False))}")
            with col2:
                # Toggle superuser
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
                if st.button("Delete User Data", key=f"delete-{uname}"):
                    if danger:
                        try:
                            delete_user_data(uname)
                            st.warning("User data deleted.")
                        except Exception as e:
                            st.error(str(e))
                    else:
                        st.error("Please confirm the checkbox before deleting.")

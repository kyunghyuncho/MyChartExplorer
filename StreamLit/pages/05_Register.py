import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import secrets

st.set_page_config(page_title="Register", layout="centered")
st.title("Register a New User")

# Load authenticator config
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("`config.yaml` not found. Please create it.")
    st.stop()


authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Guard: if already logged in, inform and link home
if st.session_state.get("authentication_status"):
    st.success("You're already logged in.")
    st.page_link("Home.py", label="Go to Home", icon="🏠")
else:
    try:
        # The register_user method returns a tuple: (bool, str) on new versions
        # It returns the username upon successful registration.
        username_of_newly_registered_user = authenticator.register_user()
        if username_of_newly_registered_user is not None:
            st.success('User registered successfully. Please log in from Home.')
            
            # Generate a database encryption key for the new user
            db_key = secrets.token_hex(32)
            config['credentials']['usernames'][username_of_newly_registered_user[1]]['db_encryption_key'] = db_key

            with open('config.yaml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
    except Exception as e:
        st.error(e)

st.divider()
st.page_link("Home.py", label="Back to Login", icon="🔐")

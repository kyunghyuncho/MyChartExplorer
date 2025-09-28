import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import secrets
from modules.paths import get_config_yaml_path
from pathlib import Path

st.set_page_config(page_title="Register", layout="centered")
st.title("Register a New User")

# Load or create authenticator config
cfg_path = get_config_yaml_path()
cfg_file = Path(cfg_path)
if not cfg_file.exists():
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    # Minimal default config
    default_cfg = {
        'credentials': {'usernames': {}},
        'cookie': {
            'name': 'mychart_auth',
            'key': secrets.token_hex(16),
            'expiry_days': 30,
        },
        'preauthorized': {'emails': []},
    }
    with cfg_file.open('w', encoding='utf-8') as f:
        yaml.dump(default_cfg, f, default_flow_style=False)

with cfg_file.open() as file:
    config = yaml.load(file, Loader=SafeLoader)


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
        # register_user returns username on success.
        result = authenticator.register_user()
        # Handle both possible return types (string username or tuple)
        username = None
        if isinstance(result, str):
            username = result
        elif isinstance(result, (list, tuple)) and len(result) >= 2:
            # Some versions returned (success_bool, username)
            success, uname = result[0], result[1]
            if success:
                username = uname

        if username:
            # Generate and persist a per-user DB encryption key
            db_key = secrets.token_hex(32)
            config.setdefault('credentials', {}).setdefault('usernames', {}).setdefault(username, {})['db_encryption_key'] = db_key
            with open(get_config_yaml_path(), 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            st.success('User registered successfully. Please log in from Home.')
    except Exception as e:
        st.error(e)

st.divider()
st.page_link("Home.py", label="Back to Login", icon="🔐")

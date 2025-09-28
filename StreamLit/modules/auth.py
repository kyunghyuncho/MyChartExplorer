import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import os
import secrets
from pathlib import Path
from .paths import get_config_yaml_path


def _ensure_config_yaml(path: str) -> None:
    """Create a minimal config.yaml if it doesn't exist."""
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    default = {
        'credentials': {
            'usernames': {}
        },
        'cookie': {
            'name': 'mychart_auth',
            'key': secrets.token_hex(16),
            'expiry_days': 30,
        },
        'preauthorized': {
            'emails': []
        }
    }
    try:
        with p.open('w', encoding='utf-8') as f:
            yaml.dump(default, f, default_flow_style=False)
        try:
            import os as _os
            _os.chmod(p, 0o600)
        except Exception:
            pass
    except Exception:
        # Best effort; if this fails, subsequent open will raise and surface to UI
        pass

def get_authenticator():
    """
    Initializes and returns the Streamlit Authenticator object.
    It locates the config.yaml file relative to the project's root directory.
    """
    # Path to config.yaml, possibly under DATADIR
    config_path = get_config_yaml_path()
    _ensure_config_yaml(config_path)
    with open(config_path) as file:
        config = yaml.load(file, Loader=SafeLoader)
    
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    return authenticator

def check_auth():
    """
    A simple function to call at the top of each authenticated page.
    Redirects to Home.py if not logged in.
    """
    if 'authentication_status' not in st.session_state or st.session_state['authentication_status'] is not True:
        st.warning("You must be logged in to access this page. Redirecting to login...")
        st.switch_page("Home.py")


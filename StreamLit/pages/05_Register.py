import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import secrets
import re
from pathlib import Path
from modules.paths import get_config_yaml_path
from modules.invitations import validate_invitation, mark_invitation_used
import time
import os
from modules.admin import list_users

st.set_page_config(page_title="Register", layout="centered")
st.title("Register a New User (Invitation Required)")

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
    try:
        import os as _os
        _os.chmod(cfg_file, 0o600)
    except Exception:
        pass

with cfg_file.open() as file:
    config = yaml.load(file, Loader=SafeLoader) or {}


def _email_taken(email: str) -> bool:
    users = ((config.get('credentials') or {}).get('usernames') or {})
    e = (email or '').strip().lower()
    for _, data in users.items():
        if (data or {}).get('email', '').strip().lower() == e:
            return True
    return False


def _hash_password_compat(password: str) -> str:
    """Hash a password using streamlit_authenticator's Hasher, compatible across versions.

    Tries multiple call patterns:
    - Hasher([pwd]).generate()[0]
    - Hasher().generate([pwd])[0]
    - Hasher.hash([pwd]) or Hasher.hash(pwd)
    - Hasher.hash_passwords([pwd])
    - Hasher.encrypt([pwd]) / Hasher.encrypt_passwords([pwd])
    """
    H = getattr(stauth, "Hasher", None)
    if H is None:
        raise RuntimeError("streamlit_authenticator.Hasher not available")
    # Instance with generate(list)
    try:
        obj = H([password])
        gen = getattr(obj, "generate", None)
        if callable(gen):
            out = gen()
            return out[0] if isinstance(out, (list, tuple)) else str(out)
    except TypeError:
        # Try no-arg constructor then generate(list)
        try:
            obj = H()
            gen = getattr(obj, "generate", None)
            if callable(gen):
                out = gen([password])
                return out[0] if isinstance(out, (list, tuple)) else str(out)
        except Exception:
            pass
    except Exception:
        pass

    # Class/staticmethod fallbacks
    for name in ("hash", "hash_passwords", "encrypt", "encrypt_passwords"):
        m = getattr(H, name, None)
        if callable(m):
            try:
                # Prefer list input when method name implies plural
                if "passwords" in name:
                    out = m([password])
                else:
                    try:
                        out = m([password])
                    except Exception:
                        out = m(password)
                return out[0] if isinstance(out, (list, tuple)) else str(out)
            except Exception:
                continue

    raise RuntimeError("Unsupported streamlit_authenticator Hasher API: cannot hash password.")


# Guard: if already logged in, inform and link home
if st.session_state.get("authentication_status"):
    st.success("You're already logged in.")
    st.page_link("Home.py", label="Go to Home", icon="🏠")
else:
    # If no users exist, show a secure Admin Bootstrap form first
    users_exist = len(list_users()) > 0
    if not users_exist:
        st.warning("Initial setup: create the first admin account.")
        with st.form("bootstrap_admin_form"):
            token_input = st.text_input("Bootstrap Token", type="password", help="Admin bootstrap token from environment variable or secrets.")
            name = st.text_input("Full Name")
            email = st.text_input("Email")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submit_bootstrap = st.form_submit_button("Create Admin Account")

        if submit_bootstrap:
            token_expected = None
            try:
                token_expected = st.secrets.get("ADMIN_BOOTSTRAP_TOKEN")  # type: ignore[attr-defined]
            except Exception:
                token_expected = None
            if not token_expected:
                token_expected = os.environ.get("ADMIN_BOOTSTRAP_TOKEN")

            if not token_expected:
                st.error("ADMIN_BOOTSTRAP_TOKEN is not set. Set it in environment or Streamlit secrets for secure bootstrap.")
            elif token_input.strip() != str(token_expected).strip():
                st.error("Invalid bootstrap token.")
            elif not name or not email or not username or not password or not confirm:
                st.error("All fields are required.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif not re.match(r"^[A-Za-z0-9_\-\.]+$", username):
                st.error("Username may contain letters, numbers, underscores, dashes, and dots only.")
            else:
                try:
                    users = config.setdefault('credentials', {}).setdefault('usernames', {})
                    if username in users:
                        st.error("Username already exists. Please choose another.")
                    else:
                        hashed = _hash_password_compat(password)
                        db_key = secrets.token_hex(32)
                        users[username] = {
                            'name': name,
                            'email': email,
                            'password': hashed,
                            'superuser': True,
                            'db_encryption_key': db_key,
                        }
                        with cfg_file.open('w', encoding='utf-8') as f:
                            yaml.dump(config, f, default_flow_style=False)
                        try:
                            import os as _os
                            _os.chmod(cfg_file, 0o600)
                        except Exception:
                            pass
                        st.success('Admin account created. Redirecting to login…')
                        time.sleep(2)
                        st.switch_page("Home.py")
                except Exception as e:
                    st.error(str(e))

        st.stop()

    # Otherwise, normal invitation-only registration
    with st.form("register_form"):
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        code = st.text_input("Invitation Code")
        st.caption("Don't have a code? Please reach out to Kyunghyun Cho to request an invitation.")
        submitted = st.form_submit_button("Register")

    if submitted:
        # Basic validation
        if not name or not email or not username or not password or not confirm or not code:
            st.error("All fields are required.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif not re.match(r"^[A-Za-z0-9_\-\.]+$", username):
            st.error("Username may contain letters, numbers, underscores, dashes, and dots only.")
        elif _email_taken(email):
            st.error("This email is already registered.")
        else:
            # Validate invitation
            if not validate_invitation(email, code):
                st.error("Invalid or expired invitation code for this email.")
            else:
                try:
                    # Create user in config.yaml
                    users = config.setdefault('credentials', {}).setdefault('usernames', {})
                    if username in users:
                        st.error("Username already exists. Please choose another.")
                    else:
                        # Hash password with compatibility across library versions
                        hashed = _hash_password_compat(password)
                        db_key = secrets.token_hex(32)
                        users[username] = {
                            'name': name,
                            'email': email,
                            'password': hashed,
                            'superuser': False,
                            'db_encryption_key': db_key,
                        }
                        with cfg_file.open('w', encoding='utf-8') as f:
                            yaml.dump(config, f, default_flow_style=False)
                        try:
                            import os as _os
                            _os.chmod(cfg_file, 0o600)
                        except Exception:
                            pass
                        # Mark invitation as used
                        mark_invitation_used(email, code)
                        st.success('User registered successfully. Redirecting to login…')
                        # Small delay then navigate to Home (login) page
                        time.sleep(2)
                        st.switch_page("Home.py")
                except Exception as e:
                    st.error(str(e))

st.divider()
st.page_link("Home.py", label="Back to Login", icon="🔐")

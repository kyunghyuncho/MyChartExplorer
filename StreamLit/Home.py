# Import necessary libraries
import streamlit as st
import os
from modules.ui import render_footer
from modules.config import load_configuration
from modules.auth import get_authenticator
from streamlit_authenticator.utilities.exceptions import LoginError
from modules.paths import (
    get_user_dir,
    get_user_db_path,
    get_user_config_json_path,
    get_config_yaml_path,
)
from pathlib import Path

# Set the title of the app
st.set_page_config(
        page_title="MyChart Explorer — Explore your health records",
        page_icon="🩺",
        layout="wide",
        initial_sidebar_state="auto",
)

# --- 🔍 SEO & Social Metadata ---
# Inject meta/link tags into <head> so search engines and social platforms can index and preview correctly.
# This uses a tiny JS snippet to create/update tags safely without relying on body-level meta parsing.
_seo_title = "MyChart Explorer — Explore your health records"
_seo_description = (
        "MyChart Explorer is a secure, easy-to-use app to import, analyze, and chat about your "
        "MyChart health records. Invitation-only beta by KC Explorer LLC."
)
_seo_keywords = (
        "MyChart, health records, FHIR, Streamlit, data visualization, healthcare, KC Explorer LLC, "
        "HIPAA, EHR, patient portal, medical data"
)
_canonical = "https://mychartexplorer.com/"
_og_image = "https://mychartexplorer.com/static/og-image.png"  # Provide this image at ~1200x630
_theme_color = "#0E7CF2"

_ld_json = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "MyChart Explorer",
        "url": _canonical,
        "publisher": {
                "@type": "Organization",
                "name": "KC Explorer LLC"
        },
        "description": _seo_description
}

_meta_injection = f"""
<script>
(function() {{
    const ensureMeta = (attr, key, value) => {{
        let el = document.querySelector(`meta[${{attr}}='${{key}}']`);
        if (!el) {{
            el = document.createElement('meta');
            el.setAttribute(attr, key);
            document.head.appendChild(el);
        }}
        el.setAttribute('content', value);
    }};

    const ensureLink = (rel, href) => {{
        let el = document.querySelector(`link[rel='${{rel}}']`);
        if (!el) {{
            el = document.createElement('link');
            el.setAttribute('rel', rel);
            document.head.appendChild(el);
        }}
        el.setAttribute('href', href);
    }};

    // Basic meta
    ensureMeta('name', 'description', {(_seo_description)!r});
    ensureMeta('name', 'keywords', {(_seo_keywords)!r});
    ensureMeta('name', 'robots', 'index,follow');
    ensureMeta('name', 'theme-color', {(_theme_color)!r});
    ensureMeta('name', 'application-name', 'MyChart Explorer');
    ensureMeta('name', 'author', 'KC Explorer LLC');
    // Streamlit sets viewport, but ensure if missing
    if (!document.querySelector('meta[name="viewport"]')) {{
        ensureMeta('name', 'viewport', 'width=device-width, initial-scale=1');
    }}

    // Open Graph
    ensureMeta('property', 'og:title', {(_seo_title)!r});
    ensureMeta('property', 'og:description', {(_seo_description)!r});
    ensureMeta('property', 'og:type', 'website');
    ensureMeta('property', 'og:url', {(_canonical)!r});
    ensureMeta('property', 'og:site_name', 'MyChart Explorer');
    ensureMeta('property', 'og:image', {(_og_image)!r});

    // Twitter
    ensureMeta('name', 'twitter:card', 'summary_large_image');
    ensureMeta('name', 'twitter:title', {(_seo_title)!r});
    ensureMeta('name', 'twitter:description', {(_seo_description)!r});
    ensureMeta('name', 'twitter:image', {(_og_image)!r});

    // Canonical
    ensureLink('canonical', {(_canonical)!r});

    // Structured data (JSON-LD)
    const ld = document.createElement('script');
    ld.type = 'application/ld+json';
    ld.text = {(_ld_json)!r};
    // Replace existing JSON-LD for WebSite if present
    const existingLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
        .find(s => {{
            try {{
                const j = JSON.parse(s.textContent || 'null');
                return j && j['@type'] === 'WebSite';
            }} catch {{ return false; }}
        }});
    if (existingLd) {{ existingLd.remove(); }}
    document.head.appendChild(ld);
        // Signal to prerenderers that the page is ready for indexing
        try {{ window.prerenderReady = true; }} catch (e) {{ }}
}})();
</script>
"""

# Height 0 prevents visible spacing; this runs once at render time.
try:
    import importlib
    _components = importlib.import_module("streamlit.components.v1")
    _components.html(_meta_injection, height=0)
except Exception:
    # Fallback: inline minimal description and keywords if components are not available
    import json as _json
    _ld_json_str = _json.dumps(_ld_json)
    st.markdown(
        f"""
        <meta name=\"description\" content=\"{_seo_description}\">\n
        <meta name=\"keywords\" content=\"{_seo_keywords}\">\n
        <link rel=\"canonical\" href=\"{_canonical}\">\n
        <script type=\"application/ld+json\">{_ld_json_str}</script>
        """,
        unsafe_allow_html=True,
    )

st.info(
    "Waiting list: MyChart Explorer is currently invitation-only while we scale. "
    "If you'd like early access or an invitation, please add your name to our waiting list. "
    "We'll notify you as slots open.\n\n"
    "[Join the waiting list →](https://forms.gle/V1o55agKKoiZ11jR7)",
    icon="📝",
)

st.title("MyChart Explorer")
st.caption("Explore and consult on your own MyChart-exported health records.")

# Capture SMART OAuth callback parameters if present
try:
    params = st.query_params  # type: ignore[attr-defined]
    if isinstance(params, dict):
        raw_code = params.get('code')
        raw_state = params.get('state')
        code_val = raw_code[0] if isinstance(raw_code, list) else raw_code
        state_val = raw_state[0] if isinstance(raw_state, list) else raw_state
        if isinstance(code_val, str) and code_val:
            st.session_state['pending_fhir_code'] = code_val
            if isinstance(state_val, str) and state_val:
                st.session_state['pending_fhir_state'] = state_val
            st.info("Received an authorization code from FHIR login. Continue on the Data Importer → SMART tab to exchange it.")
except Exception:
    pass

# --- Authentication ---
authenticator = get_authenticator()

# Initialize state
if "show_registration" not in st.session_state:
    st.session_state["show_registration"] = False
if "authentication_status" not in st.session_state:
    st.session_state["authentication_status"] = None

# --- Main Application Logic ---
# User is already logged in
if st.session_state.get("authentication_status"):
    username = st.session_state["username"]
    # Ensure per-user dir exists under DATADIR (or default)
    _ = get_user_dir(username)
    
    st.session_state['db_path'] = get_user_db_path(username)
    st.session_state['config_path'] = get_user_config_json_path(username)

    # Retrieve and store the encryption key in the session
    # Read from config.yaml to get per-user db_encryption_key (avoid accessing authenticator internals)
    try:
        import yaml
        from yaml.loader import SafeLoader
        cfg_path = get_config_yaml_path()
        p = Path(cfg_path)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            # minimal default to avoid FileNotFoundError on first run
            import secrets
            default_cfg = {
                'credentials': {'usernames': {}},
                'cookie': {
                    'name': 'mychart_auth',
                    'key': secrets.token_hex(16),
                    'expiry_days': 30,
                },
                'preauthorized': {'emails': []},
            }
            with p.open('w', encoding='utf-8') as f:
                yaml.dump(default_cfg, f, default_flow_style=False)
            try:
                import os as _os
                _os.chmod(p, 0o600)
            except Exception:
                pass
        with p.open() as f:
            cfg = yaml.load(f, Loader=SafeLoader) or {}
        user_creds = ((cfg.get('credentials') or {}).get('usernames') or {}).get(username, {})
        db_key = user_creds.get('db_encryption_key')
        if db_key:
            st.session_state['db_encryption_key'] = db_key
    except Exception:
        # Don't block the UI if config can't be read; encryption is optional
        pass
    
    authenticator.logout()
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    load_configuration()

    db_path = st.session_state.get('db_path')
    if 'data_imported' not in st.session_state:
        if db_path and os.path.exists(db_path):
            st.session_state['data_imported'] = True
            st.toast(f"Found and loaded existing database: {os.path.basename(db_path)}", icon="✅")
        else:
            st.session_state['data_imported'] = False
    
    if st.session_state.get('data_imported', False):
        st.success("Your data is loaded and ready.")
    else:
        st.info("Start by importing your MyChart XML to build your local database.")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.page_link("pages/03_Data_Importer.py", label="Data Importer", icon="📥")
    with col_b:
        st.page_link("pages/01_MyChart_Explorer.py", label="MyChart Explorer", icon="💬")
    with col_c:
        st.page_link("pages/02_Database_Explorer.py", label="Database Explorer", icon="🗂️")
    with col_d:
        st.page_link("pages/10_Instructions.py", label="Instructions", icon="📖")

    st.divider()
    st.page_link("pages/00_About.py", label="About", icon="ℹ️")
    st.page_link("pages/06_Terms_and_Conditions.py", label="Terms & Conditions", icon="📄")
    
    # Sidebar quick links (kept minimal)
    st.sidebar.page_link("pages/01_MyChart_Explorer.py", label="MyChart Explorer", icon="💬")
    st.sidebar.page_link("pages/00_About.py", label="About", icon="ℹ️")
    st.sidebar.page_link("pages/06_Terms_and_Conditions.py", label="Terms & Conditions", icon="📄")
    st.sidebar.markdown("[License](https://raw.githubusercontent.com/kyunghyuncho/MyChartExplorer/refs/heads/main/StreamLit/LICENSE)")
    render_footer()

# User is not logged in
else:
    # Beta/invitation notice for login screen
    st.info(
        "Beta service: Access is by invitation. If you need an invitation code, please email kc@mychartexplorer.com.",
        icon="🧪",
    )
    try:
        authenticator.login(location='main')
    except LoginError as e:
        st.error(f"Login failed: {e}")
        st.switch_page("pages/05_Register.py")


    if st.session_state.get("authentication_status") is False:
        st.error('Username/password is incorrect. Please try again or register a new account.')
        st.page_link("pages/05_Register.py", label="Register a new user", icon="✍️")
    elif st.session_state.get("authentication_status") is None:
        st.warning('Please enter your username and password.')
        st.page_link("pages/05_Register.py", label="Register a new user", icon="✍️")

    # Sidebar quick links (kept minimal)
    st.sidebar.page_link("pages/01_MyChart_Explorer.py", label="MyChart Explorer", icon="💬")
    st.sidebar.page_link("pages/00_About.py", label="About", icon="ℹ️")
    st.sidebar.page_link("pages/06_Terms_and_Conditions.py", label="Terms & Conditions", icon="📄")
    st.sidebar.markdown("[License](https://raw.githubusercontent.com/kyunghyuncho/MyChartExplorer/refs/heads/main/StreamLit/LICENSE)")

    render_footer()

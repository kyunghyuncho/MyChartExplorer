# This is the settings page for the Streamlit app.
# It allows users to configure the LLM provider, API keys, and SSH tunneling.

# Import necessary libraries
import streamlit as st
import os
from modules.ui import render_footer
from modules.config import load_configuration, save_configuration, get_db_size_limit_mb, set_db_size_limit_mb
from modules.config import _get_active_config_path  # reveal where settings are saved
from modules.config import _read_file_config  # to verify writes without session overlay
from modules.config import _read_json  # to read global config for migration
from modules.paths import get_global_config_json_path
from modules.admin import is_superuser, export_user_zip
from modules.ssh_tunnel import start_ssh_tunnel, start_ssh_tunnel_sync, stop_ssh_tunnel, get_tunnel_status
from modules.auth import check_auth
from modules.paths import get_conversations_dir
from modules.admin import get_user_provisioned_openrouter

# Check user authentication
check_auth()

# Set the title of the page
st.title("Settings")

# Load the current configuration (syncs session_state from disk)
config = load_configuration()
active_path = _get_active_config_path()
st.caption(f"Active settings file: {active_path}")

# If logged in, offer migration from global config.json when per-user values are empty
username = st.session_state.get("username")
if isinstance(username, str) and username.strip():
    try:
        global_path = get_global_config_json_path()
        if global_path != active_path:
            disk_user = _read_file_config() or {}
            disk_global = _read_json(global_path) or {}
            # Candidate keys to migrate
            migrate_keys = [
                "llm_provider",
                "openrouter_api_key",
                "openrouter_base_url",
                "ollama_url",
                "ollama_model",
                "auto_consult",
            ]
            missing = [k for k in migrate_keys if not (disk_user.get(k) or "") and (disk_global.get(k) or "")]
            if missing:
                with st.expander("Detected settings in global config; import into your profile?"):
                    st.caption("We found values in the global settings file that are empty in your user profile. You can import them below.")
                    if st.button("Import from global now"):
                        to_import = {k: disk_global.get(k) for k in missing}
                        # Persist into user's config
                        save_configuration(to_import)
                        # Reflect into session_state immediately
                        for k, v in to_import.items():
                            st.session_state[k] = v
                        st.success("Imported settings from global into your user profile.")
                        # Refresh page state
                        config = load_configuration()
    except Exception:
        pass

# Create a form for the settings
with st.form("settings_form"):
    form_error: str | None = None
    try:
        # Add a selectbox to choose the LLM provider
        st.subheader("LLM Provider")
        provider_options = ["ollama", "openrouter"]
        # Gracefully handle legacy values (e.g., 'gemini')
        cur = config.get("llm_provider", "ollama")
        if cur not in provider_options:
            # Prefer OpenRouter if an API key exists; otherwise Ollama
            if config.get("openrouter_api_key"):
                cur = "openrouter"
            else:
                cur = "ollama"
            st.info("Migrated from legacy provider setting. Please confirm your preferred provider below.")
        llm_provider = st.selectbox("Choose your LLM provider", provider_options, index=provider_options.index(cur))

        # Add fields for Ollama configuration
        st.subheader("Ollama Configuration")
        
        # Get the current tunnel status
        tunnel_status = get_tunnel_status()
        is_tunnel_active = tunnel_status.get("active", False)
        
        # Determine the value and disabled state of the Ollama URL input
        ollama_url_value = tunnel_status.get("ollama_url", config.get("ollama_url", "http://localhost:11434"))
        ollama_url_disabled = is_tunnel_active
        
        ollama_url = st.text_input(
            "Ollama URL",
            value=ollama_url_value,
            placeholder="http://localhost:11434",
            help="If an SSH tunnel is active, this will be the tunnel's local address.",
            disabled=ollama_url_disabled,
        )
        ollama_model = st.text_input("Ollama Model", value=config.get("ollama_model", "gpt-oss:20b"))

        # Add fields for OpenRouter configuration
        st.subheader("OpenRouter Configuration")
        # If admin has provisioned a key for this user, do not show or allow editing the API key here
        provisioned = None
        try:
            provisioned = get_user_provisioned_openrouter(st.session_state.get("username"))
        except Exception:
            provisioned = None
        api_key_placeholder = "(managed by admin)" if provisioned else config.get("openrouter_api_key", "")
        openrouter_api_key = st.text_input(
            "OpenRouter API Key",
            type="password",
            value=api_key_placeholder,
            help="Create an account and API key at openrouter.ai, then paste it here.",
            disabled=bool(provisioned),
        )
        openrouter_base_url = st.text_input(
            "OpenRouter Base URL",
            value=config.get("openrouter_base_url", "https://openrouter.ai/api/v1"),
            help="You can keep the default unless you run through a proxy.",
        )
        st.caption(
            "Hosted provider: OpenRouter. Only the model google/gemini-2.5-flash is used for now. "
            "When this provider is selected, prompts are sent to OpenRouter using your key."
        )
        st.caption(
            "Policy note (Oct 5, 2025): We currently limit hosted usage to google/gemini-2.5-flash. "
            "According to Google's Gemini API policy, requests are not used to train Google's models by default. "
            "See Google's terms for details (ai.google.dev/gemini-api/terms). Calls via OpenRouter are also subject to OpenRouter's policies."
        )
    # (moved expander below the form to keep the form minimal and avoid submit-button detection issues)

        # Database size limit (admin-controlled)
        st.subheader("Storage Limits")
        current_limit = get_db_size_limit_mb()
        if is_superuser(st.session_state.get("username")):
            db_size_limit_mb = st.number_input(
                "Max per-user database size (MB)",
                min_value=10,
                max_value=2048,
                value=int(current_limit),
                help="Admin-only: when a user's database exceeds this size, importing will be blocked.",
            )
        else:
            st.caption(f"Max per-user database size: {current_limit} MB (set by admin)")
            db_size_limit_mb = current_limit

        # Add fields for SSH tunneling configuration
        st.subheader("SSH Tunnel for Remote Ollama")
        ssh_host = st.text_input("SSH Host", value=config.get("ssh_host", ""))
        ssh_port = st.number_input("SSH Port", value=int(config.get("ssh_port", 22)))
        ssh_user = st.text_input("SSH User", value=config.get("ssh_user", ""))
        ssh_password = st.text_input("SSH Password", type="password", value=config.get("ssh_password", ""))
        ssh_private_key = st.text_input("SSH Private Key (path)", value=config.get("ssh_private_key", ""))
        ssh_passphrase = st.text_input("SSH Private Key Passphrase", type="password", value=config.get("ssh_passphrase", ""))
        remote_ollama_url = st.text_input("Remote Ollama URL", value=config.get("remote_ollama_url", "http://localhost:11434"))
    except Exception as _form_e:
        form_error = str(_form_e)

    # Create a submit button for the form
    submitted = st.form_submit_button("Save Settings", type="primary")
    # If the form is submitted, save the configuration
    if submitted and not form_error:
        # Create a new configuration dictionary
        new_config = {
            "llm_provider": llm_provider,
            "ollama_url": ollama_url,
            "ollama_model": ollama_model,
            # If admin manages a key, do not overwrite user's config value; keep whatever is on disk
            "openrouter_api_key": (config.get("openrouter_api_key") if provisioned else openrouter_api_key),
            "openrouter_base_url": openrouter_base_url,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "ssh_private_key": ssh_private_key,
            "ssh_passphrase": ssh_passphrase,
            "remote_ollama_url": remote_ollama_url,
        }
        # Save the new configuration to disk
        save_configuration(new_config)
        # Persist admin-controlled limit globally when admin edits it
        if is_superuser(st.session_state.get("username")):
            set_db_size_limit_mb(int(db_size_limit_mb))
        # Also reflect saved values into session_state so other pages pick them up immediately
        for k, v in new_config.items():
            st.session_state[k] = v
        # Read raw file (no session overlay) to verify persistence
        disk_after = _read_file_config() or {}
        mismatches = []
        # When admin manages the key, skip mismatch check for API key field
        if not provisioned:
            if (openrouter_api_key or "") != (disk_after.get("openrouter_api_key") or ""):
                mismatches.append("OpenRouter API Key")
        if (openrouter_base_url or "") != (disk_after.get("openrouter_base_url") or ""):
            mismatches.append("OpenRouter Base URL")
        if (ollama_url or "") != (disk_after.get("ollama_url") or ""):
            mismatches.append("Ollama URL")
        if (ollama_model or "") != (disk_after.get("ollama_model") or ""):
            mismatches.append("Ollama Model")
        if mismatches:
            st.error(
                "Some settings did not persist as expected: " + ", ".join(mismatches) + ". "
                "Please check file permissions and that you're editing the correct user profile."
            )
        else:
            st.success("Settings saved successfully!")
    elif form_error:
        st.error(f"Settings form error: {form_error}")

# OpenRouter help expander (moved outside the form)
with st.expander("How to get an OpenRouter API key"):
    st.markdown(
        """
        1. Go to [openrouter.ai](https://openrouter.ai) and create an account.
        2. (Optional) Add a payment method or load credit so requests can be billed.
        3. Open [Settings → API Keys](https://openrouter.ai/settings/keys).
        4. Click "Create Key" and copy the generated key.
        5. Paste the key into the "OpenRouter API Key" field above and click Save.

        Useful links:
        - API docs: https://openrouter.ai/docs
        - Keys page: https://openrouter.ai/settings/keys
        
        If you don't have an OpenRouter key yet, you can request a temporary API key by emailing kc@mychartexplorer.com. We'll review requests and may issue a limited key for evaluation.
        """
    )
    st.page_link("pages/10_Instructions.py", label="See detailed setup instructions", icon="📖")

# Add buttons to start and stop the SSH tunnel
st.subheader("SSH Tunnel Control")
# Create three columns for the buttons
col1, col2, col3 = st.columns(3)
# Add a button to start the SSH tunnel
if col1.button("Start SSH Tunnel"):
    if config["ssh_host"]:
        timeout_s = 12.0  # chosen a bit higher than default 10 in case of slower auth
        with st.spinner(f"Starting SSH tunnel (timeout {int(timeout_s)}s)..."):
            ok = start_ssh_tunnel_sync(config, timeout_seconds=timeout_s)
        # After spinner, inspect session state for result
        err = st.session_state.get('ssh_tunnel_error')
        if ok and not err:
            st.success("SSH tunnel started successfully (synchronous).")
            # Force a rerun so fields above reflect updated ollama_url immediately
            st.rerun()
        elif ok and err:
            st.warning(f"Tunnel started but reported warning: {err}")
        else:
            st.error(err or "Failed to start SSH tunnel (unknown error).")
    else:
        st.warning("Please configure the SSH host in the settings above.")

# Add a button to stop the SSH tunnel
if col2.button("Stop SSH Tunnel"):
    # Show a spinner while the tunnel is being stopped
    with st.spinner("Stopping SSH tunnel..."):
        try:
            # Stop the SSH tunnel
            stop_ssh_tunnel()
            # Show a success message
            st.success("SSH tunnel stopped successfully!")
            # Refresh UI so fields above update immediately (ollama_url reverts)
            st.rerun()
        except Exception as e:
            # Show an error message if something goes wrong
            st.error(f"Failed to stop SSH tunnel: {e}")

# Add a button to test the tunnel and show status
with col3:
    if st.button("Show Tunnel Status"):
        status = get_tunnel_status()
        st.json(status)
        err = status.get('error')
        if err:
            st.error(f"Tunnel error: {err}")

# --- Export My Data (decrypted-only) ---
st.markdown("---")
st.subheader("Export My Data")
st.caption("Download a decrypted ZIP of your database tables (as JSON) and conversations. Keep it private.")

username = st.session_state.get("username")
if username:
    # Show a quick estimate of data size and contents
    def _fmt_bytes(n: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        s = float(n)
        i = 0
        while s >= 1024 and i < len(units) - 1:
            s /= 1024.0
            i += 1
        return f"{s:.1f} {units[i]}"

    db_path = st.session_state.get("db_path")
    db_size = os.path.getsize(db_path) if db_path and os.path.exists(db_path) else 0
    conv_dir = get_conversations_dir(username)
    conv_size = 0
    conv_count = 0
    try:
        if os.path.isdir(conv_dir):
            for root, _, files in os.walk(conv_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        conv_size += os.path.getsize(fp)
                        conv_count += 1
                    except Exception:
                        pass
    except Exception:
        pass

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Database size", _fmt_bytes(db_size))
    col_b.metric("Conversations size", _fmt_bytes(conv_size))
    col_c.metric("Conversations files", conv_count)
    st.caption("Export includes: JSON files per DB table (export/db/) and decrypted conversations (export/conversations/). No keys are included.")

    if st.button("Create Export (ZIP)"):
        with st.spinner("Preparing your export…"):
            try:
                data_bytes = export_user_zip(username, mode="decrypted", include_key=False)
                st.download_button(
                    label="Download My Data",
                    data=data_bytes,
                    file_name=f"{username}_mychart_decrypted.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
                st.success("Your export is ready.")
            except Exception as e:
                st.error(f"Failed to create export: {e}")
else:
    st.info("Log in to export your data.")

render_footer()

# This is the settings page for the Streamlit app.
# It allows users to configure the LLM provider, API keys, and SSH tunneling.

# Import necessary libraries
import streamlit as st
import os
from modules.ui import render_footer
from modules.config import load_configuration, save_configuration, get_db_size_limit_mb, set_db_size_limit_mb
from modules.admin import is_superuser, export_user_zip
from modules.ssh_tunnel import start_ssh_tunnel, stop_ssh_tunnel, get_tunnel_status
from modules.auth import check_auth
from modules.paths import get_conversations_dir

# Check user authentication
check_auth()

# Set the title of the page
st.title("Settings")

# Load the current configuration (syncs session_state from disk)
config = load_configuration()

# Create a form for the settings
with st.form("settings_form"):
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
    ollama_url = st.text_input(
        "Ollama URL",
        value=config["ollama_url"],
        placeholder="http://localhost:11434",
        help="If you run a local Ollama instance, it typically listens on http://localhost:11434. Leave blank to use that default.",
    )
    ollama_model = st.text_input("Ollama Model", value=config.get("ollama_model", "gpt-oss:20b"))

    # Add fields for OpenRouter configuration
    st.subheader("OpenRouter Configuration")
    openrouter_api_key = st.text_input(
        "OpenRouter API Key",
        type="password",
        value=config.get("openrouter_api_key", ""),
        help="Create an account and API key at openrouter.ai, then paste it here.",
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
            """
        )
        st.page_link("pages/10_Instructions.py", label="See detailed setup instructions", icon="📖")

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
    ssh_host = st.text_input("SSH Host", value=config["ssh_host"])
    ssh_port = st.number_input("SSH Port", value=config["ssh_port"])
    ssh_user = st.text_input("SSH User", value=config["ssh_user"])
    ssh_password = st.text_input("SSH Password", type="password", value=config["ssh_password"])
    ssh_private_key = st.text_input("SSH Private Key (path)", value=config.get("ssh_private_key", ""))
    ssh_passphrase = st.text_input("SSH Private Key Passphrase", type="password", value=config.get("ssh_passphrase", ""))
    remote_ollama_url = st.text_input("Remote Ollama URL", value=config["remote_ollama_url"])
    local_tunnel_port = st.number_input("Local Tunnel Port", value=int(config.get("local_tunnel_port", 11435)))

    # Create a submit button for the form
    submitted = st.form_submit_button("Save Settings", type="primary")
    # If the form is submitted, save the configuration
    if submitted:
        # Create a new configuration dictionary
        new_config = {
            "llm_provider": llm_provider,
            "ollama_url": ollama_url,
            "ollama_model": ollama_model,
            "openrouter_api_key": openrouter_api_key,
            "openrouter_base_url": openrouter_base_url,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "ssh_private_key": ssh_private_key,
            "ssh_passphrase": ssh_passphrase,
            "remote_ollama_url": remote_ollama_url,
            "local_tunnel_port": int(local_tunnel_port),
        }
        # Save the new configuration to disk
        save_configuration(new_config)
        # Persist admin-controlled limit globally when admin edits it
        if is_superuser(st.session_state.get("username")):
            set_db_size_limit_mb(int(db_size_limit_mb))
        # Also reflect saved values into session_state so other pages pick them up immediately
        for k, v in new_config.items():
            st.session_state[k] = v
    # Show a success message
    st.success("Settings saved successfully!")

# Add buttons to start and stop the SSH tunnel
st.subheader("SSH Tunnel Control")
# Create three columns for the buttons
col1, col2, col3 = st.columns(3)
# Add a button to start the SSH tunnel
if col1.button("Start SSH Tunnel"):
    # If an SSH host is configured
    if config["ssh_host"]:
        # Show a spinner while the tunnel is being started
        with st.spinner("Starting SSH tunnel..."):
            try:
                # Start the SSH tunnel
                start_ssh_tunnel(config)
                # Show a success message
                st.success("SSH tunnel started successfully!")
            except Exception as e:
                # Show an error message if something goes wrong
                st.error(f"Failed to start SSH tunnel: {e}")
    else:
        # If no SSH host is configured, show a warning
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
        except Exception as e:
            # Show an error message if something goes wrong
            st.error(f"Failed to stop SSH tunnel: {e}")

# Add a button to test the tunnel and show status
with col3:
    if st.button("Show Tunnel Status"):
        status = get_tunnel_status()
        st.json(status)

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

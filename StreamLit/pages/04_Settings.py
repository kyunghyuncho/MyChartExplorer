# This is the settings page for the Streamlit app.
# It allows users to configure the LLM provider, API keys, and SSH tunneling.

# Import necessary libraries
import streamlit as st
from modules.config import load_configuration, save_configuration
from modules.ssh_tunnel import start_ssh_tunnel, stop_ssh_tunnel, get_tunnel_status

# Set the title of the page
st.title("Settings")

# Load the current configuration (syncs session_state from disk)
config = load_configuration()

# Create a form for the settings
with st.form("settings_form"):
    # Add a selectbox to choose the LLM provider
    st.subheader("LLM Provider")
    llm_provider = st.selectbox("Choose your LLM provider", ["ollama", "gemini"], index=["ollama", "gemini"].index(config["llm_provider"]))

    # Add fields for Ollama configuration
    st.subheader("Ollama Configuration")
    ollama_url = st.text_input("Ollama URL", value=config["ollama_url"])
    ollama_model = st.text_input("Ollama Model", value=config.get("ollama_model", "gpt-oss:20b"))

    # Add fields for Gemini configuration
    st.subheader("Gemini Configuration")
    gemini_api_key = st.text_input("Gemini API Key", type="password", value=config.get("gemini_api_key", ""))
    gemini_model = st.text_input("Gemini Model", value=config.get("gemini_model", "gemini-2.5-pro"))

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
    submitted = st.form_submit_button("Save Settings")
    # If the form is submitted, save the configuration
    if submitted:
        # Create a new configuration dictionary
        new_config = {
            "llm_provider": llm_provider,
            "ollama_url": ollama_url,
            "ollama_model": ollama_model,
            "gemini_api_key": gemini_api_key,
            "gemini_model": gemini_model,
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

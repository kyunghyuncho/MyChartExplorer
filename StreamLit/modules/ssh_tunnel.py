# This module handles the creation and management of SSH tunnels.
# It is used to connect to a remote Ollama server securely.

# Import necessary libraries
import streamlit as st
"""Compatibility shim for Paramiko >= 3 where DSSKey was removed.
Ensure DSSKey attribute exists before importing sshtunnel to avoid AttributeError in older sshtunnel code.
"""
try:
    import paramiko  # type: ignore
    if not hasattr(paramiko, "DSSKey"):
        # Provide a falsy placeholder so feature detection in sshtunnel can skip DSA keys gracefully
        paramiko.DSSKey = None  # type: ignore[attr-defined]
except Exception:
    pass
from sshtunnel import SSHTunnelForwarder
import threading
from urllib.parse import urlparse
import socket

# A global variable to hold the SSH tunnel server instance
TUNNEL_SERVER = None

def _parse_remote(url: str):
    """Parse a URL like http://host:port and return (host, port)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 11434
        return host, int(port)
    except Exception:
        # fallback for raw host:port
        if ":" in url:
            host, port = url.split(":", 1)
            return host.replace("//", ""), int(port)
        return url, 11434


def _tcp_check(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def start_ssh_tunnel(config):
    """
    Starts the SSH tunnel in a separate thread.

    Args:
        config (dict): The configuration dictionary containing SSH details.
    """
    # Get the SSH configuration details
    ssh_host = config["ssh_host"]
    ssh_port = int(config["ssh_port"])
    ssh_user = config["ssh_user"]
    ssh_password = config["ssh_password"]
    ssh_private_key = config.get("ssh_private_key") or None
    ssh_passphrase = config.get("ssh_passphrase") or None
    remote_ollama_url = config["remote_ollama_url"]

    # Parse the remote Ollama URL to get the remote host and port
    remote_host, remote_port = _parse_remote(remote_ollama_url)
    
    # Define the local port for the tunnel
    local_port = int(config.get("local_tunnel_port", 11435))  # Avoid conflict with local ollama

    # Stop any existing tunnel
    stop_ssh_tunnel()

    # Create the SSH tunnel server instance
    global TUNNEL_SERVER
    tunnel_kwargs = {
        "ssh_address_or_host": (ssh_host, ssh_port),
        "ssh_username": ssh_user,
        "remote_bind_address": (remote_host, remote_port),
        # Bind to localhost for security; UI still uses http://localhost:port
        "local_bind_address": ("127.0.0.1", local_port),
    }
    if ssh_private_key:
        tunnel_kwargs["ssh_pkey"] = ssh_private_key
        if ssh_passphrase:
            tunnel_kwargs["ssh_private_key_password"] = ssh_passphrase
    else:
        tunnel_kwargs["ssh_password"] = ssh_password

    TUNNEL_SERVER = SSHTunnelForwarder(**tunnel_kwargs)

    # Define a function to run the tunnel in a separate thread
    def run_tunnel():
        try:
            # Start the tunnel
            TUNNEL_SERVER.start()
            # Store the tunnel status in the session state
            st.session_state['ssh_tunnel_active'] = True
            # Update the ollama_url to use the tunnel
            st.session_state['ollama_url'] = f"http://localhost:{local_port}"
            # Optionally verify the local endpoint is reachable
            if not _tcp_check("127.0.0.1", local_port, timeout=1.5):
                st.session_state['ssh_tunnel_error'] = "Local tunnel did not open in time."
        except Exception as e:
            # If an error occurs, store the error message in the session state
            st.session_state['ssh_tunnel_error'] = str(e)

    # Create and start the thread
    tunnel_thread = threading.Thread(target=run_tunnel)
    tunnel_thread.daemon = True
    tunnel_thread.start()

def stop_ssh_tunnel():
    """
    Stops the SSH tunnel if it is running.
    """
    # Access the global tunnel server instance
    global TUNNEL_SERVER
    # If the tunnel server exists and is active
    if TUNNEL_SERVER and TUNNEL_SERVER.is_active:
        # Stop the tunnel
        TUNNEL_SERVER.stop()
        # Reset the tunnel server instance
        TUNNEL_SERVER = None
        # Update the tunnel status in the session state
        st.session_state['ssh_tunnel_active'] = False
        # Revert the ollama_url to the default
        st.session_state['ollama_url'] = "http://localhost:11434"

def get_tunnel_status():
    """Return a friendly status dict about the tunnel."""
    global TUNNEL_SERVER
    return {
        "active": bool(TUNNEL_SERVER and getattr(TUNNEL_SERVER, "is_active", False)),
        "bind_addr": getattr(TUNNEL_SERVER, "local_bind_address", None),
        "remote": getattr(TUNNEL_SERVER, "remote_bind_address", None),
        "ollama_url": st.session_state.get("ollama_url"),
        "error": st.session_state.get("ssh_tunnel_error"),
    }

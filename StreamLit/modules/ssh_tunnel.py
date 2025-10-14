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
import time
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
    return True


def start_ssh_tunnel_sync(config, timeout_seconds: float = 10.0):
    """Start the SSH tunnel synchronously with a timeout.

    This implements Solution B from `tunnel_port.md`:
    - Provide immediate, deterministic state without a race against the UI rerun.
    - If the underlying `SSHTunnelForwarder.start()` call hangs longer than `timeout_seconds`, abort and surface an error.

    Args:
        config (dict): SSH + remote Ollama configuration.
        timeout_seconds (float): Max seconds to wait for tunnel establishment.

    Returns:
        bool: True if tunnel started successfully; False otherwise.
    """
    ssh_host = config["ssh_host"]
    ssh_port = int(config["ssh_port"])
    ssh_user = config["ssh_user"]
    ssh_password = config["ssh_password"]
    ssh_private_key = config.get("ssh_private_key") or None
    ssh_passphrase = config.get("ssh_passphrase") or None
    remote_ollama_url = config["remote_ollama_url"]

    remote_host, remote_port = _parse_remote(remote_ollama_url)
    local_port = int(config.get("local_tunnel_port", 11435))

    # Stop any existing tunnel first
    stop_ssh_tunnel()

    global TUNNEL_SERVER
    tunnel_kwargs = {
        "ssh_address_or_host": (ssh_host, ssh_port),
        "ssh_username": ssh_user,
        "remote_bind_address": (remote_host, remote_port),
        "local_bind_address": ("127.0.0.1", local_port),
    }
    if ssh_private_key:
        tunnel_kwargs["ssh_pkey"] = ssh_private_key
        if ssh_passphrase:
            tunnel_kwargs["ssh_private_key_password"] = ssh_passphrase
    else:
        tunnel_kwargs["ssh_password"] = ssh_password

    TUNNEL_SERVER = SSHTunnelForwarder(**tunnel_kwargs)

    # Use a thread to allow timeout control without freezing Streamlit excessively
    exc_holder: list[Exception] = []
    started_event = threading.Event()

    def _run():
        try:
            TUNNEL_SERVER.start()
        except Exception as e:  # Capture exception for main thread
            exc_holder.append(e)
        finally:
            started_event.set()

    def _cleanup_failure(msg: str):
        """Set failure state and best-effort stop/clear the tunnel server."""
        st.session_state['ssh_tunnel_active'] = False
        st.session_state['ssh_tunnel_error'] = msg
        # Best-effort stop and clear via common stop function
        try:
            stop_ssh_tunnel()
        except Exception:
            pass

    # Mark provisional state so UI can show intent immediately
    st.session_state['ssh_tunnel_active'] = 'starting'
    st.session_state['ssh_tunnel_error'] = None
    st.session_state['ollama_url'] = f"http://localhost:{local_port}"

    th = threading.Thread(target=_run, daemon=True)
    th.start()

    deadline = time.time() + timeout_seconds
    # Poll event instead of join(timeout) so we can remain responsive later if needed
    while time.time() < deadline:
        if started_event.wait(timeout=0.1):
            break
    if not started_event.is_set():
        # Timeout: attempt cleanup
        _cleanup_failure(
            f"Timeout starting SSH tunnel after {timeout_seconds:.0f}s. Please verify server host/port, credentials, and network access."
        )
        return False

    # Thread finished: check for exception
    if exc_holder:
        err = exc_holder[0]
        _cleanup_failure(f"Failed to start SSH tunnel: {err}")
        return False

    # Success path
    st.session_state['ssh_tunnel_active'] = True
    # Re-confirm bound port in case remote changed; sshtunnel uses attribute local_bind_port
    try:
        bound_port = getattr(TUNNEL_SERVER, 'local_bind_port', local_port)
        st.session_state['ollama_url'] = f"http://localhost:{bound_port}"
        # Verify connectivity quickly
        if not _tcp_check("127.0.0.1", int(bound_port), timeout=1.5):
            st.session_state['ssh_tunnel_error'] = "Tunnel established but local port not reachable (connectivity test failed)."
    except Exception:
        pass
    return True

def stop_ssh_tunnel():
    """
    Stops the SSH tunnel and clears related session state.
    Always attempts to reset local state even if the tunnel was not fully active.
    """
    global TUNNEL_SERVER
    try:
        if TUNNEL_SERVER:
            # Stop only if active to avoid raising from sshtunnel when not started
            if getattr(TUNNEL_SERVER, 'is_active', False):
                TUNNEL_SERVER.stop()
    finally:
        # Clear the reference regardless to avoid stale handles
        TUNNEL_SERVER = None
        # Update session state consistently
        st.session_state['ssh_tunnel_active'] = False
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

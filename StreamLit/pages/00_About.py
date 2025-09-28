import streamlit as st

st.set_page_config(page_title="About", layout="wide")

st.title("About MyChart Explorer")

tab_overview, tab_privacy = st.tabs(["Overview", "If you care about privacy …"])

with tab_overview:
    st.markdown(
        """
        **MyChart Explorer** is an experimental platform intended for experienced users (for example, software developers) who want to explore their personal health records locally and privately.

        The goal of this experiment is to demonstrate how we can democratize access to our own medical records to maintain and improve our health. In the long run, approaches like this can help lower the burden on care providers and improve the overall quality of care.
        """
    )

    st.info(
        "Your data is stored locally on this server and is not shared with any third parties. "
        "I do not intend to access or share your data without your consent. "
        "However, please be aware that if you use cloud-based AI services "
        "(e.g., Gemini API), your data may be transmitted to those services. "
        "For improved privacy controls, consider using a paid Gemini API key. "
        "See the Gemini API Terms (Unpaid Services may be used to improve Google's services): "
        "https://ai.google.dev/gemini-api/terms",
        icon="🔒",
    )

    st.subheader("Creator")
    st.markdown(
        """
        Built by **Kyunghyun Cho**. Learn more at: [https://kyunghyuncho.me/](https://kyunghyuncho.me/)

        If you'd like to reach out, please email me, although I can't promise a response due to bandwidth constraints.

        I’m open to discussion—both about this experimental platform and healthcare more broadly. Feedback, ideas, critiques, and requests for collaborations are welcome.
        """
    )

    st.subheader("Open Source & Feedback")
    st.markdown(
        """
        This project is open-source. You're welcome to leave comments or file issues here:
        
        https://github.com/kyunghyuncho/MyChartExplorer/tree/main/StreamLit
        """
    )

with tab_privacy:
    st.subheader("Run Locally with Ollama (Maximum Privacy)")
    st.markdown(
        """
        You can run everything on your own machine without any cloud keys:

        1. Install **Ollama** from https://ollama.com (Linux: `curl -fsSL https://ollama.com/install.sh | sh`).
        2. Pull a local model (e.g., `gpt-oss:20b` or `llama3`): `ollama pull gpt-oss:20b`.
        3. In the app, open **Settings → LLM Provider**, choose **ollama**, and set model name.
        4. Launch the app locally and use the **MyChart Explorer** page. No external API calls are required.

        With this setup, data and inference stay on your machine.
        """
    )

    st.subheader("Use a Remote Ollama Server")
    st.markdown(
        """
        You can also point the app to a remote Ollama server—either your own home server or another trusted machine:

        - If your server is directly reachable, set the **Ollama URL** on the **Settings** page (e.g., `http://server.local:11434`).
        - If it’s behind a firewall/NAT, use the built-in **SSH Tunnel** (Settings → SSH Tunnel for Remote Ollama):
          1. Enter SSH host/user (and key/passphrase if needed).
          2. Click **Start SSH Tunnel**.
          3. Set **Ollama URL** to the local tunnel (e.g., `http://localhost:11435`).

        This keeps inference on your own hardware while letting you use the app from your laptop.
        """
    )

# Footer
st.divider()
st.caption("© 2025 Kyunghyun Cho — MIT License. See the LICENSE file in the repository.")

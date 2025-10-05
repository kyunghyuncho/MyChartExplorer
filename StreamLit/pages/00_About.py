import streamlit as st
import streamlit as st
from modules.ui import render_footer

st.set_page_config(page_title="About", layout="wide")

st.title("About MyChart Explorer")
st.info(
    "Waiting list: MyChart Explorer is currently invitation-only while we scale. "
    "If you'd like early access or an invitation, please add your name to our waiting list. "
    "We'll notify you as slots open.\n\n"
    "[Join the waiting list →](https://forms.gle/V1o55agKKoiZ11jR7)",
    icon="📝",
)

tab_overview, tab_privacy = st.tabs(["Overview", "If you care about privacy …"])

with tab_overview:
    st.markdown(
        """
        **MyChart Explorer** is an experimental platform provided by **KC Explorer LLC** (managed by the sole member, **Kyunghyun Cho**). It is intended for experienced users (for example, software developers) who want to explore their personal health records locally and privately.

        The goal of this experiment is to demonstrate how we can democratize access to our own medical records to maintain and improve our health. In the long run, approaches like this can help lower the burden on care providers and improve the overall quality of care.
        """
    )

    st.info(
        "Your data is stored locally on this server and is not shared with any third parties. "
        "However, when you select a hosted LLM provider (OpenRouter), prompts and small previews of your data "
        "are sent to OpenRouter using your API key and governed by their terms. We currently use only the model "
        "google/gemini-2.5-flash via OpenRouter. As of Oct 5, 2025, Google's Gemini API policy says requests are "
        "not used to train Google's models by default. See their terms for specifics. OpenRouter's policies also apply. "
        "Select a local provider (Ollama) for maximum privacy.",
        icon="🔒",
    )

    st.subheader("Creator")
    st.markdown(
        """
        Built by **Kyunghyun Cho**. Learn more at: [https://kyunghyuncho.me/](https://kyunghyuncho.me/)

        If you'd like to reach out, please email **kc@mychartexplorer.com** or visit **https://www.mychartexplorer.com**. I can't promise a response due to bandwidth constraints.

        I’m open to discussion—both about this experimental platform and healthcare more broadly. Feedback, ideas, critiques, and requests for collaborations are welcome.
        """
    )

    st.subheader("Open Source, License & Feedback")
    st.markdown(
        """
        Licensing:
        - Streamlit app: PolyForm Noncommercial 1.0.0 — see `StreamLit/LICENSE` in the repository.
        - Other parts (Python scripts, Swift app): MIT — see the root `LICENSE`.

        You're welcome to leave comments or file issues here:
        
        https://github.com/kyunghyuncho/MyChartExplorer/tree/main/StreamLit
        """
    )

    st.subheader("Commercialization and Implementation")
    st.markdown(
        """
        For commercial licensing, implementations, or partnerships (for clinics, hospitals, or networks), please reach out to **Kyunghyun Cho**, the sole member of **KC Explorer LLC**, at **kc@mychartexplorer.com** or visit **https://www.mychartexplorer.com**.
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

render_footer()

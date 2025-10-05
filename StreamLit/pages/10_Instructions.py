import streamlit as st
from modules.ui import render_footer

st.set_page_config(page_title="Instructions", layout="wide")

st.title("Instructions & Setup")

st.markdown("""
This page provides instructions on how to use the MyChart Explorer application, from getting your data to setting up the AI models.
""")

tab1, tab2, tab3 = st.tabs(["Data Ingestion", "Ollama Setup (Local AI)", "OpenRouter API Setup (Hosted AI)"])

with tab1:
    st.header("Step 1: Download Your MyChart Data")
    st.markdown("""
    To get started, you need to download your health records from your patient portal. 
    The file you need is a set of XML files containing your health data.
    """)

    st.subheader("Example: Downloading from NYU Langone Health")

    st.markdown("""
    To get started, you need to download your health records from your MyChart patient portal. The file you need is an XML file containing your health data.

    1.  Log in to your **NYU Langone Health MyChart** account.
    2.  Navigate to the **"Menu"**.
    3.  Under the "My Record" section, find and click on **"Download My Record"**.
    4.  You will be taken to a page to download your health summary. Select the following options:
        *   **Which records?** Choose **"All available"** to get a complete picture of your health history.
        *   **What format?** Select **"XML format"**. This is crucial for the application to be able to read your data.
    5.  Click **"Download"**. A file named `MyChart_All.xml` (or similar) will be saved to your computer.

    > **Disclaimer:** Your health data is sensitive and private. This application is designed to run locally on your machine. Your data is not uploaded to any external servers when you use this tool. You are responsible for securely storing your downloaded data file.
    """)

    st.subheader("Example: Downloading from an Athenahealth Patient Portal")
    st.markdown(
        """
        Menus can vary by practice, but most Athenahealth-powered portals follow a similar flow. For example, at
        Sullivan Street Medical (Midtown Manhattan):

        1. Log in to your practice's **Athenahealth** patient portal.
        2. Open the main **Menu** and go to **My Health** (or **Health Record/Medical Records**).
        3. Find **Download/Export Health Record** (sometimes labeled **Download My Record** or **Export**).
        4. Choose the document type: **Continuity of Care Document (CCD)** or **Summary of Care**.
        5. Select the format: **XML** or **C-CDA (XML)**.
        6. Pick a date range or choose **All available**.
        7. Click **Download**. Save the file (e.g., `Patient_Summary.xml`).

        You can now import this XML on the **Data Importer** page.
        """
    )

    st.header("Step 2: Import Your Data")
    st.markdown("""
    Once you have the XML file:
    1.  Navigate to the **"Data Importer"** page from the sidebar.
    2.  Click the **"Browse files"** button and select the `.xml` file you downloaded.
    3.  The application will process and import your data into a local, private database.
    4.  You will see a confirmation message once the import is complete. You can then proceed to the **"MyChart Explorer"** to start asking questions.
    """)
    st.info(
        "Tested systems: Epic/MyChart (e.g., NYU Langone Health) and AthenaHealth (Sullivan Street Medical, Midtown Manhattan). Other portals that export CCDA/XML may also work.",
        icon="✅",
    )

with tab2:
    st.header("How to Install Ollama for Local Inference")
    st.markdown("""
    Ollama allows you to run powerful open-source language models directly on your own computer. This is a great option for privacy and offline use.

    Follow the instructions for your operating system.
    """)

    st.subheader("macOS")
    st.markdown("""
    1.  **Download:** Go to the [Ollama website](https://ollama.com) and download the macOS application.
    2.  **Install:** Open the downloaded `.zip` file and drag the `Ollama.app` to your `Applications` folder.
    3.  **Run:** Launch the Ollama application from your Applications folder. You will see an icon in the menu bar indicating that Ollama is running.
    4.  **Pull a Model:** Open your terminal and run the following command to download a model. `gpt-oss:20b` is a great starting point.
        ```bash
        ollama pull gpt-oss:20b
        ```
    5.  **Verify:** Once the download is complete, the model is ready to be used by the MyChart Explorer. You can select it from the model list on the MyChart Explorer page.
    """)

    st.subheader("Windows")
    st.markdown("""
    1.  **Download:** Go to the [Ollama website](https://ollama.com) and download the Windows installer.
    2.  **Install:** Run the downloaded installer and follow the on-screen prompts. Ollama will be set up to run as a background service.
    3.  **Pull a Model:** Open PowerShell or Command Prompt and run the following command to download a model. `gpt-oss:20b` is a good choice.
        ```bash
        ollama pull gpt-oss:20b
        ```
    4.  **Verify:** After the download, the model is available for use in the application.
    """)

    st.subheader("Linux")
    st.markdown("""
    1.  **Install:** The recommended way to install Ollama on Linux is with a single command. Open your terminal and run:
        ```bash
        curl -fsSL https://ollama.com/install.sh | sh
        ```
    2.  **Pull a Model:** After the installation script completes, pull a model:
        ```bash
        ollama pull gpt-oss:20b
        ```
    3.  **Service:** The Ollama service will be automatically started and will run on system startup.
    """)

    st.info("""
    **Optional: SSH Tunneling**
    If you are running Ollama on a different machine (e.g., a home server), you can connect to it using an SSH tunnel. Instructions for setting this up can be found on the **"Settings"** page.
    """, icon="🔌")


with tab3:
    st.header("How to Get and Set an OpenRouter API Key")
    st.markdown("""
    OpenRouter is a hosted API gateway for multiple models. For this app, we use `google/gemini-2.5-flash` via OpenRouter.

    Steps:
    1.  **Create an account:** Go to [openrouter.ai](https://openrouter.ai) and sign up.
    2.  **(Optional) Add credit card or balance:** Ensure requests can be billed.
    3.  **Create a key:** Visit [Settings → API Keys](https://openrouter.ai/settings/keys) and click **Create Key**.
    4.  **Copy the key** when it's shown.
    5.  **Set the key in the app:** Open **Settings**, find **OpenRouter Configuration**, and paste your key into **OpenRouter API Key**. Leave Base URL as `https://openrouter.ai/api/v1` unless you have a proxy.
    6.  Click **Save Settings**.

    The application is now configured to use OpenRouter for hosted inference.

    Useful links:
    - Keys page: https://openrouter.ai/settings/keys
    - API docs: https://openrouter.ai/docs
    """)
    st.info(
        "Privacy reminder: when you select OpenRouter as the provider, prompts and small data previews are sent to OpenRouter using your key. "
        "As of Oct 5, 2025, Google's Gemini API policy states requests are not used to train Google's models by default; "
        "see ai.google.dev/gemini-api/terms. Calls via OpenRouter are also subject to OpenRouter's policies. "
        "Select Ollama for maximum local privacy.",
        icon="🔒",
    )
    
render_footer()
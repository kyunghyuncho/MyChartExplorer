import streamlit as st

st.set_page_config(
    page_title="Instructions: Get Your MyChart Data",
    page_icon="📥",
    layout="wide",
)

st.title("📥 Instructions: How to Get Your MyChart Data")

st.markdown(
    """
This page provides instructions on how to download your health records from an Epic MyChart portal. We use NYU Langone Health's MyChart as a specific example.
"""
)

st.info(
    "**Disclaimer:** The following steps are for the NYU Langone MyChart portal. The user interface and navigation on your provider's MyChart portal may be different. If you cannot find these options, please contact your healthcare provider for assistance.",
    icon="⚠️",
)

st.header("Example: NYU Langone MyChart")
st.markdown(
    """
1.  **Log In:** Navigate to the NYU Langone MyChart portal and log in:
    [https://mychart.nyulmc.org/mychart](https://mychart.nyulmc.org/mychart)

2.  **Navigate to "Share My Record":** Once logged in, click on the **"Menu"** button, and find the **"Share My Record"** option under the "Sharing" section.

3.  **Choose "Yourself":** On the "Share My Record" page, you will see options for who to share with. Click on the **"Yourself"** option.

4.  **Download a Snapshot:** Select the option to **"Download or send a snapshot of your health record."**

5.  **Select Records:** Choose **"All Visits"** to get a complete record. Then press **"Continue"**.

6.  **Wait for Notification:** The system will prepare your files. This may take some time. You should receive an email from MyChart when your download is ready.

7.  **Download and Unzip:** Follow the link in the email to download a `.zip` file. Unzip this file on your computer.

8.  **Locate XML Files:** Inside the unzipped folder, you should find a directory structure similar to `IHE_XDM/`. Your XML health records will be inside a sub-folder, for instance `IHE_XDM/[your first name]1/`. These are the files you will use with the **Data Importer** page in this app.
"""
)

st.warning(
    "If these steps do not work for your provider, look for terms like 'Download', 'Export', 'Share Record', or 'Health Summary' in your MyChart portal. When in doubt, contact your provider's patient support.",
    icon="💡",
)

import streamlit as st
from modules.ui import render_footer

st.set_page_config(page_title="Terms & Conditions", layout="wide")

st.title("Terms & Conditions")

st.markdown(
    """
    Updated: October 3, 2025

    ## Ownership
    - MyChart Explorer is provided by **KC Explorer LLC** (sole member: **Kyunghyun Cho**).

    ## Licensing
    - **PolyForm Noncommercial 1.0.0**

    Noncommercial use of the MyChartExplorer App is permitted under the PolyForm Noncommercial terms. **Commercial use requires a separate agreement with KC Explorer LLC.**

    ## Experimental Platform; No Medical Advice
    - This is an experimental platform and **not a medical device**.
    - The software is provided **as-is**, without warranties or guarantees of any kind.
    - All information is for **informational purposes only**. Always consult a qualified clinician for medical advice.

    ## Privacy
    - Your data is stored locally on this server or in your configured data directory.
    - If you select a hosted AI provider (OpenRouter), prompts and small previews of your data may be transmitted to OpenRouter using your API key and are governed by OpenRouter's terms. We currently limit hosted usage to the model `google/gemini-2.5-flash` via OpenRouter. As of Oct 5, 2025, Google's Gemini API policy states requests are not used to train Google's models by default; see ai.google.dev/gemini-api/terms. OpenRouter's policies also apply. If you select a local provider (Ollama), no prompts leave your environment.
    - See the About page for additional privacy guidance.

    ## Third-Party Components
    This project may include or interact with third-party components and services. Such components are provided under their own licenses and/or terms.

    ## Commercialization and Implementation
    For commercial licensing, implementations, or partnerships (for clinics, hospitals, or networks), please reach out to **Kyunghyun Cho**, the sole member of **KC Explorer LLC**, at **kc@mychartexplorer.com** or visit **https://www.mychartexplorer.com**.

    ---
    These Terms & Conditions may be updated from time to time to reflect changes in licensing or project scope. Continued use of the software indicates acceptance of the current terms.
    """
)

st.markdown(
    """
    ## Detailed Terms and Conditions

    1) Purpose — MyChart Explorer helps you view and understand your own health records. It is read-only and does not change your medical chart.

    2) No Medical Advice — The app provides educational information only and is not a substitute for professional medical advice, diagnosis, or treatment. Always talk to your clinician about your care. Call emergency services in an emergency.

    3) Eligibility & Accounts — You must be legally allowed to use this service and keep your login secure. You are responsible for activity under your account.

    4) Data Access & Sources — With your consent, the app may connect to third-party systems (e.g., Epic) using SMART on FHIR to retrieve your records. Access is read-only. The app does not write to the EHR.

    5) Privacy & Security — We strive to protect your information with encryption in transit and per-user encrypted storage at rest. We do not sell your personal information. See the app's documentation for details.

    6) Storage & Deletion — Your data is stored in your app workspace. You (or an admin) may delete your data at any time from the Admin/Settings tools. Deletion is permanent and cannot be undone.

    7) AI/LLM Usage & Limitations — Bring‑Your‑Own‑LLM: You choose the model provider and supply any API keys (e.g., a local runner like Ollama or a hosted provider via OpenRouter). The app does not operate its own hosted model on your data. When you select a hosted provider, only the prompts/snippets shown in the UI are sent to that provider using your key. For hosted use, we currently restrict to `google/gemini-2.5-flash`. As of Oct 5, 2025, Google's Gemini API policy indicates requests are not used to train Google's models by default (see ai.google.dev/gemini-api/terms). Hosted traffic is also subject to OpenRouter's policies. If you select a local model, no prompts leave your environment. We attempt to disable provider data retention/training where available, but hosted providers process data under their own terms. Outputs may be incomplete or incorrect and are for educational use only. Verify with your clinician. You can opt out by using a local model and/or removing your API keys.

    8) Acceptable Use — Do not misuse the service (e.g., attempts to break security, reverse engineer, or infringe rights). We may suspend or terminate access for violations.

    9) No Warranties — The service is provided “as is” without warranties of any kind.

    10) Liability — To the maximum extent permitted by law, we are not liable for indirect, incidental, special, or consequential damages. Our total liability for any claim is limited to the amount you paid for the service (if any) in the 12 months before the claim.

    11) Changes — We may update these Terms. Continued use after changes means you accept the updated Terms.

    12) Contact — Questions? Email kc@mychartexplorer.com.
    """
)

render_footer()

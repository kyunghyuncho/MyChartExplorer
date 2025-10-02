import streamlit as st

st.set_page_config(page_title="Terms & Conditions", layout="wide")
st.title("Terms & Conditions")

st.caption("Effective date: October 1, 2025")

st.markdown(
    """
### 1) Purpose
MyChart Explorer helps you view and understand your own health records. It is read-only and does not change your medical chart.

### 2) No Medical Advice
The app provides educational information only and is not a substitute for professional medical advice, diagnosis, or treatment. Always talk to your clinician about your care. Call emergency services in an emergency.

### 3) Eligibility & Accounts
You must be legally allowed to use this service and keep your login secure. You are responsible for activity under your account.

### 4) Data Access & Sources
With your consent, the app may connect to third-party systems (e.g., Epic) using SMART on FHIR to retrieve your records. Access is read-only. The app does not write to the EHR.

### 5) Privacy & Security
We strive to protect your information with encryption in transit and per-user encrypted storage at rest. We do not sell your personal information. See the app's documentation for details.

### 6) Storage & Deletion
Your data is stored in your app workspace. You (or an admin) may delete your data at any time from the Admin/Settings tools. Deletion is permanent and cannot be undone.

### 7) AI/LLM Usage & Limitations
- Bring‑Your‑Own‑LLM: You choose the model provider and supply any API keys (e.g., a local runner like Ollama or a hosted provider like Google Gemini). The app does not operate its own hosted model on your data.
- Control of data flow: When you select a hosted provider, only the prompts/snippets shown in the UI are sent to that provider using your key. If you select a local model, no prompts leave your environment.
- Provider policies: We attempt to disable provider data retention/training where available, but hosted providers process data under their own terms and privacy policies.
- Safety: Outputs may be incomplete or incorrect and are for educational use only—do not rely on them for medical decisions; verify with your clinician.
- Opt‑out: Use a local model and/or disable summarization features to avoid sending text to hosted providers, and you may remove your API keys at any time in Settings.

### 8) Acceptable Use
Do not misuse the service (e.g., attempts to break security, reverse engineer, or infringe rights). We may suspend or terminate access for violations.

### 9) No Warranties
The service is provided “as is” without warranties of any kind.

### 10) Liability
To the maximum extent permitted by law, we are not liable for indirect, incidental, special, or consequential damages. Our total liability for any claim is limited to the amount you paid for the service (if any) in the 12 months before the claim.

### 11) Changes
We may update these Terms. Continued use after changes means you accept the updated Terms.

### 12) Contact
Questions? Email kc@mychartexplorer.com.
    """
)

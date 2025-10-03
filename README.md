# MyChart Explorer — Streamlit App

Provided by KC Explorer LLC (sole member: Kyunghyun Cho). This is an experimental platform.

Explore and consult on your MyChart-exported health data with an AI assistant. Import CCDA/XML, store locally in SQLite, retrieve relevant records with safe, read-only SQL, and get concise answers grounded in your own chart.

Live app: https://www.mychartexplorer.com

Disclaimer: This is not a medical device. Informational only. Always consult a qualified clinician for medical advice. Provided on an as-is basis without warranties or liability, as detailed in the applicable licenses.

---

## Highlights

- Import MyChart CCDA/XML into a private SQLite database
- Conversation-style Q&A with Gemini or Ollama
- Read-only SQL generation with strict sanitizer (SELECT/WITH only)
- Conversation-aware answers using all retrieved context so far
- Save/load conversations; self-serve data export (decrypted-only)
- Configurable backend: Gemini API key or local Ollama (SSH tunnel supported)

## Privacy & Security

- Retrieval-only SQL sanitizer blocks writes/DDL/PRAGMA
- Patient scoping inlined into SQL (no bind params) to avoid leakage
- Ollama URL restricted to localhost to mitigate SSRF; use SSH tunnel for remote
- Least-privilege filesystem perms for configs, user dirs, and saved conversations
- “Export My Data” provides decrypted-only export for your records and chats

## Get Started (Hosted)

1) Visit https://www.mychartexplorer.com
2) Register or sign in
3) Import your MyChart CCDA/XML
4) Open “MyChart Explorer” and ask questions; the app retrieves relevant rows and consults automatically (configurable)

## Run Locally (Streamlit)

From the StreamLit directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional: choose a data directory for per-user configs and DB
export DATADIR="$HOME/.mychartexplorer"
streamlit run Home.py
```

macOS + SQLCipher (optional, for encrypted DBs):

```bash
brew install sqlcipher
export C_INCLUDE_PATH="/opt/homebrew/opt/sqlcipher/include"
export LIBRARY_PATH="/opt/homebrew/opt/sqlcipher/lib"
pip install -r requirements.txt
```

## Repository Layout

- StreamLit/ — Streamlit app (recommended and hosted version)
- GeminiMyChartExplorer/ — legacy macOS Swift app (not required for Streamlit)
- PythonVersion/ — tooling and scripts (importers/advisors)

## License

This repository uses different licenses for different parts:

- `StreamLit/` (Streamlit application): PolyForm Noncommercial 1.0.0 — see `StreamLit/LICENSE`
- Everything else (e.g., `PythonVersion/`, `GeminiMyChartExplorer/`): MIT — see `LICENSE`

Commercialization and Implementation
- For commercial licensing, implementations, or partnerships, please contact Kyunghyun Cho (sole member of KC Explorer LLC) at kc@mychartexplorer.com or visit https://www.mychartexplorer.com.

# MyChart Explorer (Streamlit)

Provided by KC Explorer LLC (sole member: Kyunghyun Cho). This is an experimental platform.

Explore and consult on your MyChart-exported health data with an AI assistant. Import CCDA/XML, store locally in SQLite, retrieve relevant records with safe, read-only SQL, and get concise answers grounded in your own chart.

Live app: https://www.mychartexplorer.com

Disclaimer: This is not a medical device. Informational only. Always consult a qualified clinician for medical advice.

## Requirements

- Python 3.11+
- macOS or Linux recommended
- Recommended: a virtual environment
- Optional: GPU-backed Ollama for local LLMs, or an OpenRouter API key

## Setup

```bash
# from the StreamLit folder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### macOS Prerequisites

If you are on macOS, you may need to install `sqlcipher` for the database encryption features to work.

```bash
brew install sqlcipher
export C_INCLUDE_PATH="/opt/homebrew/opt/sqlcipher/include"
export LIBRARY_PATH="/opt/homebrew/opt/sqlcipher/lib"
# Now, run the pip install command
pip install -r requirements.txt
```

## Running

```bash
# from the StreamLit folder
streamlit run Home.py
```

The app is a multipage app. Use the left sidebar to navigate pages.

Hosted version
- You can use the hosted app at https://www.mychartexplorer.com with the same workflows (import, explore, consult) without local setup.

## Data Directory (DATADIR)

By default, the app stores its configuration and user data under the StreamLit folder:
- config.yaml (authentication)
- config.json (global settings when not logged in)
- user_data/<username>/ (per-user DB, settings, and conversations)

You can override this location by setting the DATADIR environment variable before launching the app:

```bash
export DATADIR="$HOME/.mychartexplorer"
streamlit run Home.py
```

If DATADIR is not set, the current repository directory (StreamLit) is used.

First run behavior:
- If `config.yaml` does not exist at the chosen data directory, the app will automatically create a minimal one on first run.
- Then, go to the Register page to add your first user. Per-user data will be created under `user_data/<username>/` in the same data directory.

## User Registration and Security

This application supports multi-user environments by providing a user registration and login system.

- **User Accounts**: Each user can create their own account to keep their health data, configuration, and conversations private.
- **Data Isolation**: Your data is stored in a user-specific directory and is only accessible after you log in.
- **Getting Started**: New users should go to the "Register" page from the sidebar to create an account. Existing users can log in on the Home page.

## Pages Overview

- Register: Create a user account to save your data and conversations.
- MyChart Explorer (Chat): ask questions; the app retrieves relevant data and consults on it.
- Database Explorer: browse tables and rows.
- Data Importer: import your MyChart XML into a local SQLite DB.
- Settings: configure LLM backend, models, OpenRouter key, and SSH tunnel.
- Instructions: How to use the app.

## Tested Data Sources

- Epic/MyChart (e.g., NYU Langone Health): XML export imported successfully via Data Importer.
- AthenaHealth (Sullivan Street Medical, Midtown Manhattan): XML export imported successfully.

Other portals that provide a CCDA/XML export may work as well, but only the above have been explicitly tested so far.

## Database Schema

For reference during development and debugging:
- Human-readable schema: `docs/SCHEMA.md`
- SQLite DDL: `schema.sql`

## Backends: Ollama and OpenRouter

- Switch backend in two places:
  - Sidebar of MyChart Explorer (quick switch)
  - Settings page (persist model names and other details)
- OpenRouter
  - Set your OpenRouter API key in Settings (and optional base URL).
  - If you don't have a key yet, you can request a temporary API key by emailing kc@mychartexplorer.com. We'll review requests and may issue a limited key for evaluation.
  - Hosted model is currently fixed to `google/gemini-2.5-flash` to ensure concise and fast replies.
- Ollama
  - Point Ollama URL and set model name in Settings (e.g., `llama3`, `llama3.1:8b`).

## SSH Tunnel (for remote Ollama)

Configure SSH host/user in Settings. Use the SSH Tunnel Control buttons to start/stop the tunnel.

## Troubleshooting
- FileNotFoundError for `config.yaml`: On current versions, the app auto-creates a minimal `config.yaml` at startup. If you still see this error, confirm:
  - You launched Streamlit from the same shell where you exported `DATADIR` (if using it).
  - The data directory (e.g., `~/.mychartexplorer`) is writable.
  - Alternatively, copy an existing `config.yaml` into your data directory.

- "Import could not be resolved" in editor: ensure you’re using the `.venv` Python in your editor. The app still runs if packages are installed in `.venv`.
- Widget state errors: Avoid setting widget-related keys in `st.session_state`. Configuration saves only whitelist known config keys.
- OpenRouter calls failing: confirm your API key and base URL in Settings. Ensure the hosted model `google/gemini-2.5-flash` is available to your account.
  - If you don't have an OpenRouter key, email kc@mychartexplorer.com to request a temporary evaluation key.
- Pandas not installed: tables fall back to text; install `pandas` for DataFrame previews.

## Tips

- The app shows the SQL used for retrieval so you can trust and verify results.
- You can save and reload conversations in the sidebar.

---

If you prefer the native macOS prototype, see the Swift app under `GeminiMyChartExplorer/` (not required for Streamlit).

## License

This Streamlit application (`StreamLit/`) is licensed under PolyForm Noncommercial 1.0.0 — see `StreamLit/LICENSE`.
Other parts of the repository are licensed under MIT — see the root `LICENSE`.

Commercialization and Implementation
- For commercial licensing, implementations, or partnerships, please contact Kyunghyun Cho (sole member of KC Explorer LLC) at kc@mychartexplorer.com or visit https://www.mychartexplorer.com.

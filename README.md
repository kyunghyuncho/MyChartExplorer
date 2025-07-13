# MyChartExplorer

Use `importer` to ingest Epic's XML files into a sqlite3 database, and then use `advisor` to query `gemini-2.5-flash` with any medical question which will be automatically augmented with your own medical records.

## Swift UI version

Check out `GeminiMyChartExplorer` with Xcode to build your own Mac native app.

### Local inference support

The Swift UI version supports local model inference using `gemma3:4b-it-qat` via `Ollama`.

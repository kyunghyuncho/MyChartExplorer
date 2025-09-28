# This module handles all interactions with the Large Language Models (LLMs).
# It provides a unified interface for different LLM backends like Ollama and Gemini.

# Import necessary libraries
import streamlit as st
import google.generativeai as genai
import requests
import json
import re
from sqlalchemy import text, inspect
from datetime import date, datetime

class LLMService:
    """
    A class to interact with different LLM backends.
    """

    def __init__(self, db_engine):
        """
        Initializes the LLMService.
        """
        # Store the database engine
        self.db_engine = db_engine
        # Load the configuration snapshot; note we will re-read live values when needed
        self.config = self._load_config()

    def _load_config(self):
        """
        Loads the configuration from Streamlit's session state.
        This allows for easy configuration of the LLM service.
        """
        # Default configuration
        config = {
            "llm_provider": "gemini",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "llama3",
            "gemini_api_key": None,
            "gemini_model": "gemini-1.5-flash",
        }
        # Override with session state if available
        for key in config:
            if key in st.session_state:
                config[key] = st.session_state[key]
        return config

    def _get_db_schema(self):
        """
        Retrieves the database schema as a string.
        """
        # Get the table names from the database using SQLAlchemy inspector
        inspector = inspect(self.db_engine)
        table_names = inspector.get_table_names()
        schema = ""
        # For each table, get the schema and append it to the string
        for table_name in table_names:
            # Append the table creation SQL to the schema string
            schema += f"Table {table_name}:\n"
            # Get the table columns
            with self.db_engine.connect() as connection:
                # Get the table columns using a query
                result = connection.execute(text(f"PRAGMA table_info({table_name});"))
                # Append the column information to the schema string
                for row in result:
                    schema += f"  {row[1]} {row[2]}\n"
            schema += "\n"
        return schema

    def _sanitize_sql(self, sql_text: str) -> str:
        """Normalize and validate LLM SQL for SQLite (read-only only).

        Steps:
        - Strip markdown code fences and inline backticks
        - Strip SQL comments (line -- and block /* */)
        - Extract the first top-level statement (respect quotes)
        - Enforce read-only (must start with SELECT or WITH)
        - Validate balanced quotes and parentheses
        - Return cleaned statement with a single trailing semicolon or empty string if unsafe/invalid
        """
        if not sql_text:
            return ""

        def strip_code_fences(s: str) -> str:
            lines = s.splitlines()
            out = []
            in_fence = False
            for line in lines:
                l = line.strip()
                if l.startswith("```"):
                    in_fence = not in_fence
                    continue
                # Drop a lone language tag like 'sql'
                if not in_fence and l.lower() == "sql":
                    continue
                out.append(line)
            return "\n".join(out)

        def strip_sql_comments(s: str) -> str:
            out = []
            i = 0
            n = len(s)
            in_squote = False
            in_dquote = False
            in_block_comment = False
            while i < n:
                ch = s[i]
                nxt = s[i + 1] if i + 1 < n else ""
                if in_block_comment:
                    if ch == "*" and nxt == "/":
                        in_block_comment = False
                        i += 2
                        continue
                    i += 1
                    continue
                if not in_squote and not in_dquote:
                    # line comment
                    if ch == "-" and nxt == "-":
                        # skip to end of line
                        while i < n and s[i] != "\n":
                            i += 1
                        continue
                    # block comment
                    if ch == "/" and nxt == "*":
                        in_block_comment = True
                        i += 2
                        continue
                    # quote toggles
                    if ch == "'":
                        in_squote = True
                        out.append(ch)
                        i += 1
                        continue
                    if ch == '"':
                        in_dquote = True
                        out.append(ch)
                        i += 1
                        continue
                    out.append(ch)
                    i += 1
                    continue
                else:
                    # inside quotes
                    if in_squote:
                        out.append(ch)
                        i += 1
                        if ch == "'":
                            in_squote = False
                        continue
                    if in_dquote:
                        out.append(ch)
                        i += 1
                        if ch == '"':
                            in_dquote = False
                        continue
            return "".join(out)

        def first_statement(s: str) -> str:
            i = 0
            n = len(s)
            in_squote = False
            in_dquote = False
            in_block_comment = False
            while i < n:
                ch = s[i]
                nxt = s[i + 1] if i + 1 < n else ""
                if in_block_comment:
                    if ch == "*" and nxt == "/":
                        in_block_comment = False
                        i += 2
                        continue
                    i += 1
                    continue
                if not in_squote and not in_dquote:
                    # start of block comment
                    if ch == "/" and nxt == "*":
                        in_block_comment = True
                        i += 2
                        continue
                    # line comment, skip to end of line
                    if ch == "-" and nxt == "-":
                        while i < n and s[i] != "\n":
                            i += 1
                        continue
                    if ch == ";":
                        return s[: i + 1]
                    if ch == "'":
                        in_squote = True
                    elif ch == '"':
                        in_dquote = True
                i += 1
            return s

        def validate_readonly_and_balance(s: str) -> str:
            t = s.strip().lstrip("\ufeff")  # remove BOM if present
            if not t:
                return ""
            lowered = t.lower()
            if not (lowered.startswith("select") or lowered.startswith("with")):
                return ""
            # balance check
            in_squote = False
            in_dquote = False
            paren = 0
            i = 0
            n = len(t)
            while i < n:
                ch = t[i]
                if not in_squote and not in_dquote:
                    if ch == "(":
                        paren += 1
                    elif ch == ")":
                        paren -= 1
                        if paren < 0:
                            return ""
                    elif ch == "'":
                        in_squote = True
                    elif ch == '"':
                        in_dquote = True
                else:
                    if in_squote and ch == "'":
                        in_squote = False
                    elif in_dquote and ch == '"':
                        in_dquote = False
                i += 1
            if in_squote or in_dquote or paren != 0:
                return ""
            # ensure single trailing semicolon
            if not t.endswith(";"):
                t = t + ";"
            return t

        s = sql_text.strip().replace("`", "")
        s = strip_code_fences(s)
        s = strip_sql_comments(s)
        s = first_statement(s)
        cleaned = validate_readonly_and_balance(s)
        return cleaned

    def _generate_sql(self, question):
        """
        Generates an SQL query from a natural language question.
        """
        # Get the database schema
        schema = self._get_db_schema()
        # Create the prompt for the LLM
        # Try to include current patient_id to discourage parameters
        pid = self._get_current_patient_id()
        pid_hint = f"Use patient_id = {pid} where relevant." if pid is not None else "Filter correctly by patient when needed."
        prompt = f"""
        Given the following database schema:
        {schema}

        Generate a SQL query to answer the following question: "{question}"
        
    Output a single plain SQL statement only.
    - No explanations
    - No markdown
    - No code fences
    - Do NOT use parameters (? or :name); inline literal values only.
    - {pid_hint}
    Retrieval-only rules (strict):
    - Retrieve existing fields only; do not generate or fabricate values.
    - Do NOT create synthetic columns from constant strings (e.g., 'Immunization' AS event_type).
    - Do NOT summarize or aggregate unless the question explicitly requests it (avoid GROUP BY/COUNT/AVG/etc.).
    - Prefer filtering with patient_id where applicable.
    - Use only column names present in the schema; do not rename columns unnecessarily.
    - Avoid UNIONs that add label columns; return raw rows from the relevant table(s).
        """
        # Use the configured LLM provider to generate the SQL
        cfg = self._load_config()
        if cfg["llm_provider"] == "ollama":
            # Generate SQL using Ollama
            return self._query_ollama(prompt, cfg)
        elif cfg["llm_provider"] == "gemini":
            # Generate SQL using Gemini (strict, plain text)
            sys_inst = (
                "You are a SQLite query generator. Output exactly one valid SQLite statement that starts with SELECT or WITH. "
                "No markdown, no explanations, no comments, no code fences. Do not use parameters; inline literal values. "
                "Use only columns from the provided schema and avoid fabricating columns or labels."
            )
            return self._query_gemini(
                prompt,
                cfg,
                response_mime_type="text/plain",
                temperature=0.1,
                system_instruction=sys_inst,
            )
        else:
            # Raise an error if the provider is not supported
            raise ValueError("Unsupported LLM provider")

    def _generate_sql_batch(self, question: str, max_queries: int = 4) -> str:
        """Ask the LLM for multiple small, focused SQL queries as a JSON array of strings."""
        schema = self._get_db_schema()
        pid = self._get_current_patient_id()
        pid_hint = f"Use patient_id = {pid} where relevant." if pid is not None else "Filter correctly by patient when needed."
        prompt = f"""
Given the following database schema:
{schema}

Produce up to {max_queries} small, distinct SQLite read-only SQL queries (strings) that together help answer:
"{question}"

Guidelines:
- Output must be a single compact JSON array of strings, e.g., ["SELECT ...;", "SELECT ...;"]
- Each string must be a single valid SELECT or WITH statement for SQLite.
- No parameters (? or :name); inline literal values only. {pid_hint}
- Prefer diversity across relevant tables (e.g., medications, immunizations, results, vitals, problems, procedures, notes).
- Avoid duplicates and keep each query concise and focused.
Retrieval-only rules (strict):
- Retrieve existing fields only; do not generate or fabricate values.
- Do NOT create synthetic columns from constant strings (e.g., 'Immunization' AS event_type).
- Do NOT summarize or aggregate unless the question explicitly requests it (avoid GROUP BY/COUNT/AVG/etc.).
- Prefer filtering with patient_id where applicable.
- Use only column names present in the schema; do not rename columns unnecessarily.
- Avoid UNIONs that add label columns; return raw rows from the relevant table(s).
"""
        cfg = self._load_config()
        if cfg["llm_provider"] == "ollama":
            return self._query_ollama(prompt, cfg)
        elif cfg["llm_provider"] == "gemini":
            sys_inst = (
                "You produce only a compact JSON array of strings. Each string is one valid SQLite SELECT or WITH statement. "
                "No markdown, no comments, no additional text. Do not use parameters; inline literal values."
            )
            return self._query_gemini(
                prompt,
                cfg,
                response_mime_type="application/json",
                temperature=0.1,
                system_instruction=sys_inst,
            )
        else:
            raise ValueError("Unsupported LLM provider")

    # Public pipeline helpers for the UI
    def generate_sql(self, question: str) -> str:
        raw_sql = self._generate_sql(question)
        return self._sanitize_sql(raw_sql)

    def generate_sql_batch(self, question: str, max_queries: int = 4) -> list[str]:
        raw = self._generate_sql_batch(question, max_queries=max_queries)
        items: list[str] = []
        # First try JSON parsing
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                items = [str(x) for x in arr]
        except Exception:
            # Fallback: split by newlines; filter non-empty
            items = [line for line in raw.splitlines() if line.strip()]
        cleaned: list[str] = []
        seen = set()
        for s in items:
            q = self._sanitize_sql(s)
            q = self._inline_patient_id(q)
            if not q:
                continue
            if q in seen:
                continue
            seen.add(q)
            cleaned.append(q)
            if len(cleaned) >= max_queries:
                break
        return cleaned

    def execute_sql(self, sql_query: str):
        if not sql_query:
            return []
        with self.db_engine.connect() as connection:
            return connection.execute(text(sql_query)).fetchall()

    def retrieve(self, question: str, max_retries: int = 1):
        """Generate SQL for the question, sanitize/validate, execute, and retry once if it fails.

        Returns a tuple (sql, rows). Raises on final failure.
        """
        raw_sql = self._generate_sql(question)
        sql_query = self._sanitize_sql(raw_sql)
        sql_query = self._inline_patient_id(sql_query)
        if not sql_query:
            # attempt a second try asking for plain SELECT/WITH only
            retry_prompt = f"""
You previously returned an invalid or unsafe SQL for this question:
Question: {question}
Schema:
{self._get_db_schema()}

Return a single valid SQLite SELECT or WITH query only. No markdown, no code fences, no comments.
Do NOT use parameters (? or :name); inline literal values only.
{('Use patient_id = ' + str(self._get_current_patient_id()) + ' where relevant.') if self._get_current_patient_id() is not None else ''}
            """
            cfg = self._load_config()
            raw_sql = (
                self._query_ollama(retry_prompt, cfg)
                if cfg["llm_provider"] == "ollama"
                else self._query_gemini(
                    retry_prompt,
                    cfg,
                    response_mime_type="text/plain",
                    temperature=0.1,
                    system_instruction=(
                        "You are a SQLite query generator. Return exactly one corrected valid SQLite statement that starts with SELECT or WITH. "
                        "No markdown, no explanations, no comments, no code fences. Do not use parameters; inline literal values."
                    ),
                )
            )
            sql_query = self._sanitize_sql(raw_sql)
            sql_query = self._inline_patient_id(sql_query)
            if not sql_query:
                raise ValueError("Failed to generate a valid read-only SQL query.")
        try:
            rows = self.execute_sql(sql_query)
            return sql_query, rows
        except Exception as e:
            # Retry once with error hint
            if max_retries <= 0:
                raise
            err_msg = str(e)
            retry_prompt = f"""
Your previous SQL had an error when executed on SQLite.
Question: {question}
Error: {err_msg}
Previous SQL:
{sql_query}

Using the schema below, produce a corrected single SELECT/WITH statement for SQLite.
It must be valid SQL, no markdown, no comments, no code fences. Do NOT use parameters (? or :name); inline literal values only.
{('Use patient_id = ' + str(self._get_current_patient_id()) + ' where relevant.') if self._get_current_patient_id() is not None else ''}
{self._get_db_schema()}
            """
            cfg = self._load_config()
            raw_sql2 = (
                self._query_ollama(retry_prompt, cfg)
                if cfg["llm_provider"] == "ollama"
                else self._query_gemini(
                    retry_prompt,
                    cfg,
                    response_mime_type="text/plain",
                    temperature=0.1,
                    system_instruction=(
                        "You are a SQLite query generator. Return exactly one corrected valid SQLite statement that starts with SELECT or WITH. "
                        "No markdown, no explanations, no comments, no code fences. Do not use parameters; inline literal values."
                    ),
                )
            )
            sql2 = self._sanitize_sql(raw_sql2)
            sql2 = self._inline_patient_id(sql2)
            if not sql2:
                raise
            rows2 = self.execute_sql(sql2)
            return sql2, rows2

    def retrieve_batch(self, question: str, max_queries: int = 4, max_retries: int = 1):
        """Best-effort retrieval of multiple small queries.

        Returns a list of dicts: [{"sql": str, "rows": list, "error": Optional[str]}]
        """
        queries = self.generate_sql_batch(question, max_queries=max_queries)

        # Hybrid boost: add deterministic queries for clinical notes to increase recall
        extra_queries: list[str] = []
        if self._has_table("notes"):
            # Always include a recent-notes overview
            extra_queries.append(
                "SELECT note_date, note_title, provider, substr(note_content, 1, 500) AS snippet FROM notes ORDER BY note_date DESC LIMIT 10;"
            )
            # If the question appears to target narrative content, add simple keyword searches
            if self._is_notes_intent(question):
                for kw in self._extract_keywords(question)[:4]:
                    # Escape single quotes for SQL literal
                    safe = kw.replace("'", "''")
                    extra_queries.append(
                        "SELECT note_date, note_title, provider, substr(note_content, 1, 500) AS snippet "
                        "FROM notes "
                        f"WHERE lower(note_title) LIKE '%{safe.lower()}%' OR lower(note_content) LIKE '%{safe.lower()}%' "
                        "ORDER BY note_date DESC LIMIT 20;"
                    )

        run_queries = extra_queries + queries
        # Avoid producing too many tabs; cap execution to extras + max_queries
        max_to_run = min(len(run_queries), len(extra_queries) + max_queries)

        results = []
        for idx, q in enumerate(run_queries):
            if idx >= max_to_run:
                break
            try:
                rows = self.execute_sql(q)
                results.append({"sql": q, "rows": rows, "error": None})
            except Exception as e:
                if max_retries > 0:
                    # try one correction for this query
                    retry_prompt = f"""
Your previous SQL had an error when executed on SQLite.
Question: {question}
Error: {str(e)}
Previous SQL:
{q}

Using the schema below, produce a corrected single SELECT/WITH statement for SQLite.
It must be valid SQL, no markdown, no comments, no code fences. Do NOT use parameters (? or :name); inline literal values only.
{('Use patient_id = ' + str(self._get_current_patient_id()) + ' where relevant.') if self._get_current_patient_id() is not None else ''}
{self._get_db_schema()}
                    """
                    cfg = self._load_config()
                    raw_sql2 = (
                        self._query_ollama(retry_prompt, cfg)
                        if cfg["llm_provider"] == "ollama"
                        else self._query_gemini(
                            retry_prompt,
                            cfg,
                            response_mime_type="text/plain",
                            temperature=0.1,
                            system_instruction=(
                                "You are a SQLite query generator. Return exactly one corrected valid SQLite statement that starts with SELECT or WITH. "
                                "No markdown, no explanations, no comments, no code fences. Do not use parameters; inline literal values."
                            ),
                        )
                    )
                    sql2 = self._sanitize_sql(raw_sql2)
                    sql2 = self._inline_patient_id(sql2)
                    if sql2:
                        try:
                            rows2 = self.execute_sql(sql2)
                            results.append({"sql": sql2, "rows": rows2, "error": None})
                            continue
                        except Exception as e2:
                            results.append({"sql": sql2, "rows": [], "error": str(e2)})
                            continue
                # if no retry or still failing
                results.append({"sql": q, "rows": [], "error": str(e)})
        return results

    def consult(self, question: str, rows) -> str:
        # Format retrieved rows
        results_str = "\n".join([str(row) for row in rows]) if rows else "(no rows)"
        # Build patient context and prepend it
        patient_context = self._get_patient_context_text()
        final_prompt = f"""
Patient context:
{patient_context}

Based on the following data from the user's medical records:
{results_str}

Answer the following question: "{question}"
"""
        cfg = self._load_config()
        if cfg["llm_provider"] == "ollama":
            return self._query_ollama(final_prompt, cfg)
        elif cfg["llm_provider"] == "gemini":
            return self._query_gemini(final_prompt, cfg)
        else:
            raise ValueError("Unsupported LLM provider")

    def consult_multi(self, question: str, rows_list: list[list]) -> str:
        """Consult over multiple result sets by concatenating short previews."""
        previews = []
        for idx, rows in enumerate(rows_list, 1):
            if not rows:
                continue
            # take up to 10 rows per set
            subset = rows[:10]
            previews.append(f"-- Result set {idx} --\n" + "\n".join(str(r) for r in subset))
        results_str = "\n\n".join(previews) if previews else "(no rows)"
        patient_context = self._get_patient_context_text()
        final_prompt = f"""
Patient context:
{patient_context}

Based on the following data from the user's medical records (multiple subsets):
{results_str}

Answer the following question: "{question}"
"""
        cfg = self._load_config()
        if cfg["llm_provider"] == "ollama":
            return self._query_ollama(final_prompt, cfg)
        elif cfg["llm_provider"] == "gemini":
            return self._query_gemini(final_prompt, cfg)
        else:
            raise ValueError("Unsupported LLM provider")

    def _summarize_notes(self, notes):
        """
        Summarizes a list of clinical notes.
        """
        # Create the prompt for the LLM
        prompt = f"""
        Summarize the following clinical notes:
        {notes}
        """
        # Use the configured LLM provider to summarize the notes
        if self.config["llm_provider"] == "ollama":
            # Summarize using Ollama
            return self._query_ollama(prompt)
        elif self.config["llm_provider"] == "gemini":
            # Summarize using Gemini
            return self._query_gemini(prompt)
        else:
            # Raise an error if the provider is not supported
            raise ValueError("Unsupported LLM provider")

    def _query_ollama(self, prompt, cfg=None):
        """
        Queries the Ollama API.
        """
        cfg = cfg or self._load_config()
        # The payload for the Ollama API
        payload = {
            "model": cfg["ollama_model"],
            "prompt": prompt,
            "stream": False
        }
        # Determine base URL: use configured value or fall back to local default
        base_url = (cfg.get("ollama_url") or "http://localhost:11434").rstrip("/")
        # Make a POST request to the Ollama API
        response = requests.post(f"{base_url}/api/generate", json=payload)
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        # Parse the JSON response and return the content
        return response.json()["response"].strip()

    def _query_gemini(
        self,
        prompt: str,
        cfg=None,
        response_mime_type: str | None = None,
        temperature: float | None = None,
        system_instruction: str | None = None,
    ):
        """
        Queries the Gemini API with optional system instructions and response MIME type control.
        Defaults remain compatible with older usage.
        """
        cfg = cfg or self._load_config()
        genai.configure(api_key=cfg["gemini_api_key"])
        generation_config = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if response_mime_type:
            generation_config["response_mime_type"] = response_mime_type
        # Instantiate model with optional system instruction
        if system_instruction:
            model = genai.GenerativeModel(
                cfg["gemini_model"], system_instruction=system_instruction
            )
        else:
            model = genai.GenerativeModel(cfg["gemini_model"])
        # Generate content
        if generation_config:
            response = model.generate_content(prompt, generation_config=generation_config)
        else:
            response = model.generate_content(prompt)
        # Safely extract text across SDK versions
        text = None
        try:
            if hasattr(response, "text") and response.text:
                text = response.text
            elif hasattr(response, "candidates") and response.candidates:
                # Some versions provide parts
                parts = []
                for c in response.candidates:
                    if getattr(c, "content", None) and getattr(c.content, "parts", None):
                        for p in c.content.parts:
                            if hasattr(p, "text") and p.text:
                                parts.append(p.text)
                text = "\n".join(parts)
        except Exception:
            text = None
        text = (text or "").strip()
        return text

    def ask_question(self, question):
        """Backward-compatible single-step ask that uses the new pipeline."""
        sql_query = self.generate_sql(question)
        if not sql_query:
            return "Sorry, I couldn't generate a safe SQL query. Please rephrase your question."
        rows = self.execute_sql(sql_query)
        return self.consult(question, rows)

    # ---------------- Patient context helpers -----------------
    def _parse_date(self, s: str):
        if not s:
            return None
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y%m", "%Y"):
            try:
                return datetime.strptime(s[:len(fmt.replace('%', ''))], fmt).date()
            except Exception:
                continue
        try:
            # ISO-like fallback
            return datetime.fromisoformat(s).date()
        except Exception:
            return None

    def _calc_age(self, dob: date) -> int | None:
        if not dob:
            return None
        today = date.today()
        years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return years

    def get_patient_context(self) -> dict:
        """Return a dict of patient demographics for prompting and display (no name for privacy)."""
        q = text(
            "SELECT dob, gender, marital_status, race, ethnicity, deceased, deceased_date FROM patients LIMIT 1"
        )
        with self.db_engine.connect() as conn:
            row = conn.execute(q).fetchone()
        if not row:
            return {}
        dob = self._parse_date(row[0]) if row[0] else None
        age = self._calc_age(dob) if dob else None
        return {
            "dob": dob.isoformat() if dob else None,
            "age": age,
            "gender": row[1],
            "marital_status": row[2],
            "race": row[3],
            "ethnicity": row[4],
            "deceased": bool(row[5]) if row[5] is not None else None,
            "deceased_date": row[6],
        }

    def _get_patient_context_text(self) -> str:
        d = self.get_patient_context() or {}
        parts = []
        if d.get("age") is not None:
            parts.append(f"age {d['age']}")
        if d.get("dob"):
            parts.append(f"DOB {d['dob']}")
        if d.get("gender"):
            parts.append(f"gender {d['gender']}")
        if d.get("race"):
            parts.append(f"race {d['race']}")
        if d.get("ethnicity"):
            parts.append(f"ethnicity {d['ethnicity']}")
        if d.get("deceased"):
            parts.append("deceased")
            if d.get("deceased_date"):
                parts.append(f"on {d['deceased_date']}")
        return ", ".join(parts) if parts else "(no demographics available)"

    # ---------------- Intent and keyword helpers (notes-focused) -----------------
    def _has_table(self, name: str) -> bool:
        try:
            insp = inspect(self.db_engine)
            return name in (insp.get_table_names() or [])
        except Exception:
            return False

    def _is_notes_intent(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        keywords = [
            "note", "notes", "progress note", "clinic note", "office note", "visit note",
            "encounter", "visit", "hpi", "assessment", "plan", "a/p", "impression",
            "discharge", "admission", "consult", "operative", "op note", "summary",
            "letter", "provider said", "doctor said", "nurse note",
        ]
        return any(k in q for k in keywords)

    def _extract_keywords(self, question: str) -> list[str]:
        if not question:
            return []
        # Simple heuristic: split on non-letters, drop stopwords/short tokens
        import re as _re
        tokens = [t for t in _re.split(r"[^a-zA-Z]+", question.lower()) if len(t) >= 4]
        stop = {
            "about","after","before","since","with","without","which","what","that","this","from","into","over","under","where","when","your","their","there","have","been","being","were","will","would","could","should","because","while","during","notes","note","visit","visits","encounter","encounters",
        }
        uniq = []
        seen = set()
        for t in tokens:
            if t in stop:
                continue
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        return uniq[:8]

    # ---------------- SQL parameter helpers -----------------
    def _get_current_patient_id(self):
        try:
            with self.db_engine.connect() as conn:
                r = conn.execute(text("SELECT id FROM patients LIMIT 1")).fetchone()
                return int(r[0]) if r and r[0] is not None else None
        except Exception:
            return None

    def _inline_patient_id(self, sql: str) -> str:
        """Replace patient_id parameter placeholders with the current patient id literal.

        - Only operates outside quotes
        - Replaces patterns like: patient_id = ?  or patient_id = :patient_id
        - Leaves SQL unchanged if no patient id available
        - After replacement, if any remaining parameter markers (? or :name) exist, returns empty string to trigger retry
        """
        if not sql:
            return sql
        pid = self._get_current_patient_id()
        if pid is None:
            # If SQL contains parameter placeholders, reject to force retry without params
            if "?" in sql or re.search(r":[A-Za-z_][A-Za-z0-9_]*", sql):
                return ""
            return sql

        # Walk through and only modify outside of quotes
        out = []
        i = 0
        n = len(sql)
        in_squote = False
        in_dquote = False
        while i < n:
            ch = sql[i]
            if ch == "'" and not in_dquote:
                in_squote = not in_squote
                out.append(ch)
                i += 1
                continue
            if ch == '"' and not in_squote:
                in_dquote = not in_dquote
                out.append(ch)
                i += 1
                continue
            if not in_squote and not in_dquote:
                # Try regex from this position for alias?.patient_id = ? or :name
                m = re.match(r"((?:[A-Za-z_][A-Za-z0-9_]*\.)?)patient_id\s*=\s*(\?|:[A-Za-z_][A-Za-z0-9_]*)", sql[i:])
                if m:
                    # Preserve optional alias prefix
                    prefix = m.group(1) or ""
                    repl = f"{prefix}patient_id = {pid}"
                    out.append(repl)
                    i += m.end()
                    continue
            out.append(ch)
            i += 1

        s2 = "".join(out)
        # If any other bind params remain, reject and force retry
        if "?" in s2 or re.search(r":[A-Za-z_][A-Za-z0-9_]*", s2):
            return ""
        return s2

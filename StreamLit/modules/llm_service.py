# This module handles all interactions with the Large Language Models (LLMs).
# It provides a unified interface for different LLM backends like Ollama and Gemini.

# Import necessary libraries
import streamlit as st
import google.generativeai as genai
import requests
import json
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
        # Load the configuration from Streamlit secrets or session state
        self.config = self._load_config()

    def _load_config(self):
        """
        Loads the configuration from Streamlit's session state.
        This allows for easy configuration of the LLM service.
        """
        # Default configuration
        config = {
            "llm_provider": "ollama",
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
        prompt = f"""
        Given the following database schema:
        {schema}

        Generate a SQL query to answer the following question: "{question}"
        
    Output a single plain SQL statement only.
    - No explanations
    - No markdown
    - No code fences
        """
        # Use the configured LLM provider to generate the SQL
        if self.config["llm_provider"] == "ollama":
            # Generate SQL using Ollama
            return self._query_ollama(prompt)
        elif self.config["llm_provider"] == "gemini":
            # Generate SQL using Gemini
            return self._query_gemini(prompt)
        else:
            # Raise an error if the provider is not supported
            raise ValueError("Unsupported LLM provider")

    # Public pipeline helpers for the UI
    def generate_sql(self, question: str) -> str:
        raw_sql = self._generate_sql(question)
        return self._sanitize_sql(raw_sql)

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
        if not sql_query:
            # attempt a second try asking for plain SELECT/WITH only
            retry_prompt = f"""
You previously returned an invalid or unsafe SQL for this question:
Question: {question}
Schema:
{self._get_db_schema()}

Return a single valid SQLite SELECT or WITH query only. No markdown, no code fences.
            """
            raw_sql = (self._query_ollama(retry_prompt)
                       if self.config["llm_provider"] == "ollama"
                       else self._query_gemini(retry_prompt))
            sql_query = self._sanitize_sql(raw_sql)
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
It must be valid SQL, no markdown, no comments, no code fences:
{self._get_db_schema()}
            """
            raw_sql2 = (self._query_ollama(retry_prompt)
                        if self.config["llm_provider"] == "ollama"
                        else self._query_gemini(retry_prompt))
            sql2 = self._sanitize_sql(raw_sql2)
            if not sql2:
                raise
            rows2 = self.execute_sql(sql2)
            return sql2, rows2

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
        if self.config["llm_provider"] == "ollama":
            return self._query_ollama(final_prompt)
        elif self.config["llm_provider"] == "gemini":
            return self._query_gemini(final_prompt)
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

    def _query_ollama(self, prompt):
        """
        Queries the Ollama API.
        """
        # The payload for the Ollama API
        payload = {
            "model": self.config["ollama_model"],
            "prompt": prompt,
            "stream": False
        }
        # Make a POST request to the Ollama API
        response = requests.post(f"{self.config['ollama_url']}/api/generate", json=payload)
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        # Parse the JSON response and return the content
        return response.json()["response"].strip()

    def _query_gemini(self, prompt):
        """
        Queries the Gemini API.
        """
        # Configure the Gemini API with the API key
        genai.configure(api_key=self.config["gemini_api_key"])
        # Create a generative model instance
        model = genai.GenerativeModel(self.config["gemini_model"])
        # Generate content using the model
        response = model.generate_content(prompt)
        # Return the generated text
        return response.text.strip()

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

# This module handles all interactions with the Large Language Models (LLMs).
# It provides a unified interface for different LLM backends like Ollama and Gemini.

# Import necessary libraries
import streamlit as st
import google.generativeai as genai
import requests
import json
import re
from sqlalchemy import text, inspect
from typing import Callable
from .config import (
    get_preview_limits_global,
    get_notes_snippet_max_chars,
    get_notes_summarization_enabled,
)
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
            # Must start with SELECT or WITH
            if not (lowered.startswith("select") or lowered.startswith("with")):
                return ""
            # Disallow dangerous keywords anywhere using word boundaries to avoid false positives
            import re as _re
            if _re.search(r"\b(insert|update|delete|create|alter|drop|attach|detach|vacuum|pragma)\b", lowered):
                return ""
            # If starts with WITH, ensure it eventually leads to a SELECT and not DML
            if lowered.startswith("with") and "select" not in lowered:
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

    def _generate_sql(self, question, history_text: str | None = None):
        """
        Generates an SQL query from a natural language question.
        """
        # Get the database schema
        schema = self._get_db_schema()
        # Create the prompt for the LLM
        # Try to include current patient_id to discourage parameters
        pids = self._get_current_patient_ids()
        if pids:
            pid_list = ", ".join(str(i) for i in pids)
            pid_hint = f"Use patient_id IN ({pid_list}) where relevant."
        else:
            pid_hint = "Filter correctly by patient when needed."
        convo_block = f"\nConversation so far (summarized):\n{history_text}\n\n" if history_text else "\n"
        prompt = f"""
        Given the following database schema:
        {schema}
        {convo_block}
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

    def _generate_sql_batch(self, question: str, max_queries: int = 4, history_text: str | None = None) -> str:
        """Ask the LLM for multiple small, focused SQL queries as a JSON array of strings."""
        schema = self._get_db_schema()
        pids = self._get_current_patient_ids()
        if pids:
            pid_list = ", ".join(str(i) for i in pids)
            pid_hint = f"Use patient_id IN ({pid_list}) where relevant."
        else:
            pid_hint = "Filter correctly by patient when needed."
        convo_block = f"\nConversation so far (summarized):\n{history_text}\n\n" if history_text else "\n"
        prompt = f"""
Given the following database schema:
{schema}
{convo_block}

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
    def generate_sql(self, question: str, chat_history: list[dict] | None = None) -> str:
        hist = self._summarize_conversation_for_sql(chat_history) if chat_history else None
        raw_sql = self._generate_sql(question, history_text=hist)
        return self._sanitize_sql(raw_sql)

    def generate_sql_batch(self, question: str, max_queries: int = 4, chat_history: list[dict] | None = None) -> list[str]:
        hist = self._summarize_conversation_for_sql(chat_history) if chat_history else None
        raw = self._generate_sql_batch(question, max_queries=max_queries, history_text=hist)
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

    def retrieve(self, question: str, max_retries: int = 1, chat_history: list[dict] | None = None):
        """Generate SQL for the question, sanitize/validate, execute, and retry once if it fails.

        Returns a tuple (sql, rows). Raises on final failure.
        """
        hist = self._summarize_conversation_for_sql(chat_history) if chat_history else None
        raw_sql = self._generate_sql(question, history_text=hist)
        sql_query = self._sanitize_sql(raw_sql)
        sql_query = self._inline_patient_id(sql_query)
        if not sql_query:
            # attempt a second try asking for plain SELECT/WITH only
            retry_prompt = f"""
You previously returned an invalid or unsafe SQL for this question:
Question: {question}
Schema:
{self._get_db_schema()}

Return a single valid SQLite SELECT OR WITH query only. No markdown, no code fences, no comments.
Do NOT use parameters (? or :name); inline literal values only.
{('Use patient_id IN (' + ', '.join(str(i) for i in self._get_current_patient_ids()) + ') where relevant.') if self._get_current_patient_ids() else ''}
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
{('Use patient_id IN (' + ', '.join(str(i) for i in self._get_current_patient_ids()) + ') where relevant.') if self._get_current_patient_ids() else ''}
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

    def retrieve_batch(self, question: str, max_queries: int = 4, max_retries: int = 1,
                       progress_cb: Callable[[str], None] | None = None,
                       chat_history: list[dict] | None = None):
        """Best-effort retrieval of multiple small queries.

        Returns a list of dicts: [{"sql": str, "rows": list, "error": Optional[str]}]
        """
        if progress_cb:
            try:
                progress_cb("Generating SQL candidates…")
            except Exception:
                pass
        queries = self.generate_sql_batch(question, max_queries=max_queries, chat_history=chat_history)
        if progress_cb:
            try:
                progress_cb(f"Generated {len(queries)} candidate queries.")
            except Exception:
                pass

        # Hybrid boost: add deterministic queries for clinical notes to increase recall
        extra_queries: list[str] = []
        if self._has_table("notes"):
            # Determine desired snippet length from admin setting (bounded for SQL substr)
            try:
                snip_len = int(get_notes_snippet_max_chars())
            except Exception:
                snip_len = 600
            sql_snip_len = max(200, min(2000, snip_len))
            # Always include a recent-notes overview
            if self._table_has_column("notes", "patient_id") and self._get_current_patient_ids():
                pid_list = ", ".join(str(i) for i in self._get_current_patient_ids())
                extra_queries.append(
                    "SELECT note_date, note_title, provider, substr(note_content, 1, "
                    f"{sql_snip_len}) AS snippet FROM notes "
                    f"WHERE patient_id IN ({pid_list}) ORDER BY note_date DESC LIMIT 10;"
                )
            else:
                extra_queries.append(
                    "SELECT note_date, note_title, provider, substr(note_content, 1, "
                    f"{sql_snip_len}) AS snippet FROM notes ORDER BY note_date DESC LIMIT 10;"
                )
            # If the question appears to target narrative content, add simple keyword searches
            if self._is_notes_intent(question):
                for kw in self._extract_keywords(question)[:4]:
                    # Escape single quotes for SQL literal
                    safe = kw.replace("'", "''")
                    if self._table_has_column("notes", "patient_id") and self._get_current_patient_ids():
                        pid_list = ", ".join(str(i) for i in self._get_current_patient_ids())
                        extra_queries.append(
                            "SELECT note_date, note_title, provider, substr(note_content, 1, "
                            f"{sql_snip_len}) AS snippet "
                            "FROM notes "
                            f"WHERE (lower(note_title) LIKE '%{safe.lower()}%' OR lower(note_content) LIKE '%{safe.lower()}%') "
                            f"AND patient_id IN ({pid_list}) "
                            "ORDER BY note_date DESC LIMIT 20;"
                        )
                    else:
                        extra_queries.append(
                            "SELECT note_date, note_title, provider, substr(note_content, 1, "
                            f"{sql_snip_len}) AS snippet "
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
                # Compute a short table label for this query (best-effort)
                tbl = self._first_table_label(q)
                short_desc = self._short_sql_desc(q)
                if progress_cb:
                    try:
                        label = f"Executing query {idx + 1}/{max_to_run}"
                        if short_desc:
                            label += f" — {short_desc}"
                        elif tbl:
                            label += f" ({tbl})"
                        label += "…"
                        progress_cb(label)
                    except Exception:
                        pass
                rows = self.execute_sql(q)
                results.append({"sql": q, "rows": rows, "error": None})
                if progress_cb:
                    try:
                        label = f"✓ Query {idx + 1}"
                        if short_desc:
                            label += f" — {short_desc}"
                        elif tbl:
                            label += f" ({tbl})"
                        label += f": {len(rows)} row(s)"
                        progress_cb(label)
                    except Exception:
                        pass
            except Exception as e:
                if max_retries > 0:
                    # try one correction for this query
                    if progress_cb:
                        try:
                            label = f"Retrying query {idx + 1}"
                            if short_desc:
                                label += f" — {short_desc}"
                            elif tbl:
                                label += f" ({tbl})"
                            label += f" after error: {str(e)[:120]}"
                            progress_cb(label)
                        except Exception:
                            pass
                    retry_prompt = f"""
Your previous SQL had an error when executed on SQLite.
Question: {question}
Error: {str(e)}
Previous SQL:
{q}

Using the schema below, produce a corrected single SELECT/WITH statement for SQLite.
It must be valid SQL, no markdown, no comments, no code fences. Do NOT use parameters (? or :name); inline literal values only.
{('Use patient_id IN (' + ', '.join(str(i) for i in self._get_current_patient_ids()) + ') where relevant.') if self._get_current_patient_ids() else ''}
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
                            # Update table label/desc from corrected SQL if available
                            tbl2 = self._first_table_label(sql2) or tbl
                            short_desc2 = self._short_sql_desc(sql2) or short_desc
                            if progress_cb:
                                try:
                                    label = f"✓ Query {idx + 1}"
                                    if short_desc2:
                                        label += f" — {short_desc2}"
                                    elif tbl2:
                                        label += f" ({tbl2})"
                                    label += f" retry: {len(rows2)} row(s)"
                                    progress_cb(label)
                                except Exception:
                                    pass
                            continue
                        except Exception as e2:
                            results.append({"sql": sql2, "rows": [], "error": str(e2)})
                            if progress_cb:
                                try:
                                    label = f"✗ Query {idx + 1}"
                                    if short_desc:
                                        label += f" — {short_desc}"
                                    elif tbl:
                                        label += f" ({tbl})"
                                    label += f" retry failed: {str(e2)[:120]}"
                                    progress_cb(label)
                                except Exception:
                                    pass
                            continue
                # if no retry or still failing
                results.append({"sql": q, "rows": [], "error": str(e)})
                if progress_cb:
                    try:
                        label = f"✗ Query {idx + 1}"
                        if short_desc:
                            label += f" — {short_desc}"
                        elif tbl:
                            label += f" ({tbl})"
                        label += f" failed: {str(e)[:120]}"
                        progress_cb(label)
                    except Exception:
                        pass
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
            subset_lines = self._preview_rows(rows)
            previews.append(f"-- Result set {idx} --\n" + "\n".join(subset_lines))
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

    def consult_conversation(self, chat_history: list[dict], rows_history: list[list]) -> str:
        """Consult using the full conversation so far and all retrieved data so far.

        - Includes patient context
        - Summarizes conversation (last ~12 messages) with role labels
        - Includes previews from all result sets gathered so far (up to 8 sets, 10 rows each)
        - Asks the model to answer the last user question
        """
        # Build conversation transcript
        hist = chat_history or []
        # keep the last 12 messages for brevity
        hist_tail = hist[-12:]
        lines = []
        for m in hist_tail:
            role = m.get("role", "user")
            role_label = "User" if role == "user" else "Assistant"
            content = str(m.get("content", "")).strip()
            if content:
                lines.append(f"{role_label}: {content}")
        convo_str = "\n".join(lines) if lines else "(no prior conversation)"

        # Build results previews
        previews = []
        max_sets = self._get_preview_limits()[2]
        for idx, rows in enumerate(rows_history[:max_sets], 1):
            if not rows:
                continue
            subset_lines = self._preview_rows(rows)
            previews.append(f"-- Result set {idx} --\n" + "\n".join(subset_lines))
        results_str = "\n\n".join(previews) if previews else "(no rows collected)"

        # Last user question (fallback to empty)
        last_q = next((m.get("content") for m in reversed(hist_tail) if m.get("role") == "user"), "")

        patient_context = self._get_patient_context_text()
        final_prompt = f"""
Patient context:
{patient_context}

Conversation so far:
{convo_str}

Data gathered so far (across multiple queries and turns):
{results_str}

Task:
Provide the best possible, accurate, and concise answer to the last user question in the conversation above.
If the data is insufficient, state clearly what is missing or cannot be concluded from the available records.
"""
        cfg = self._load_config()
        if cfg["llm_provider"] == "ollama":
            return self._query_ollama(final_prompt, cfg)
        elif cfg["llm_provider"] == "gemini":
            return self._query_gemini(final_prompt, cfg)
        else:
            raise ValueError("Unsupported LLM provider")

    # ---------------- Preview helpers -----------------
    def _get_preview_limits(self) -> tuple[int, int, int]:
        """Return (max_rows_per_set, char_budget_per_set, max_sets) with sensible defaults.

        Values are admin-configured globally in the Admin Console.
        """
        # Read admin/global limits; fall back to built-in defaults if unavailable
        try:
            mr, cb, ms = get_preview_limits_global()
        except Exception:
            mr, cb, ms = (20, 3000, 8)
        # clamp to reasonable bounds
        mr = max(1, min(100, mr))
        cb = max(500, min(20000, cb))
        ms = max(1, min(16, ms))
        return mr, cb, ms

    def _preview_rows(self, rows) -> list[str]:
        """Build a compact, informative preview of a result set.

        - Prefers most recent rows if a date-like column exists
        - Limits total rows and characters for prompt efficiency
        - Produces readable key=value summaries for mapping rows
        """
        if not rows:
            return []

        max_rows, char_budget, _ = self._get_preview_limits()

        # Work on a shallow copy to avoid mutating caller's list
        rows_local = list(rows)

        # Detect mapping rows and columns
        mapping_mode = hasattr(rows_local[0], "_mapping")
        cols = []
        if mapping_mode:
            try:
                cols = list(rows_local[0]._mapping.keys())
            except Exception:
                cols = []

        # If a date-like column exists, sort by it descending
        date_cols_pref = [
            "note_date", "result_date", "date", "datetime", "visit_date", "encounter_date",
            "start_date", "end_date", "performed_date", "observation_date", "collected_date",
        ]

        def _row_get(r, k):
            try:
                return r._mapping.get(k)
            except Exception:
                return None

        date_col = None
        if mapping_mode and cols:
            for c in date_cols_pref:
                if c in cols:
                    date_col = c
                    break
            if date_col is not None:
                try:
                    def _key(r):
                        v = _row_get(r, date_col)
                        d = self._parse_date(str(v)) if v is not None else None
                        # sort None last
                        return (d is None, d)
                    rows_local.sort(key=_key, reverse=True)
                except Exception:
                    pass

        # Choose a small, meaningful subset of columns for display
        preferred_cols = [
            # Core identifiers and timing
            "id", date_col or "",
            # Notes-specific fields (ensure content gets included)
            "note_title", "snippet", "note_content",
            # Generic/common columns
            "title", "name", "test", "component", "value", "result", "unit", "status", "provider", "code",
        ]
        preferred_cols = [c for c in preferred_cols if c and (not cols or c in cols)]
        if mapping_mode and not preferred_cols and cols:
            preferred_cols = cols[:6]

        lines: list[str] = []
        used_chars = 0
        for r in rows_local[: max_rows * 2]:  # allow a little slack pre-truncation
            if used_chars >= char_budget or len(lines) >= max_rows:
                break
            try:
                if mapping_mode:
                    m = r._mapping
                    parts = []
                    for c in preferred_cols:
                        v = m.get(c)
                        if v is None:
                            continue
                        sv = str(v)
                        # Truncate very long fields; allow larger budget for note content with admin setting
                        max_len = 200
                        if c in ("snippet", "note_content"):
                            try:
                                max_len = int(get_notes_snippet_max_chars())
                            except Exception:
                                max_len = 600
                        if len(sv) > max_len:
                            # Optional summarization for very long notes
                            if c in ("snippet", "note_content") and get_notes_summarization_enabled():
                                try:
                                    sv = self._summarize_text_safe(sv, target_chars=max_len)
                                except Exception:
                                    sv = sv[: max_len - 3] + "..."
                            else:
                                sv = sv[: max_len - 3] + "..."
                        parts.append(f"{c}={sv}")
                    if not parts:
                        # fallback to full mapping limited
                        raw = dict(m)
                        s = str(raw)
                    else:
                        s = "; ".join(parts)
                else:
                    s = str(r)
                    if len(s) > 300:
                        s = s[:297] + "..."
            except Exception:
                s = str(r)

            # respect remaining budget
            if used_chars + len(s) > char_budget:
                # take only what fits (if any)
                remaining = max(0, char_budget - used_chars)
                if remaining < 10:  # too tight to be useful
                    break
                s = s[: remaining - 3] + "..."
            lines.append(s)
            used_chars += len(s)

        return lines[:max_rows]

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

    def _summarize_text_safe(self, text: str, target_chars: int = 600) -> str:
        """Summarize arbitrary text to approximately target_chars using the configured provider.

        Best-effort; falls back to naive truncation on error.
        """
        text = str(text or "")
        if len(text) <= max(100, target_chars):
            return text
        cfg = self._load_config()
        prompt = (
            "Summarize the following clinical note content succinctly in plain text, preserving key clinical facts and chronology. "
            f"Limit to about {target_chars} characters.\n\n" + text
        )
        try:
            if cfg["llm_provider"] == "ollama":
                out = self._query_ollama(prompt, cfg)
            elif cfg["llm_provider"] == "gemini":
                out = self._query_gemini(prompt, cfg, response_mime_type="text/plain", temperature=0.2)
            else:
                out = ""
        except Exception:
            out = ""
        out = (out or "").strip()
        if not out:
            return text[: max(100, target_chars) - 3] + "..."
        if len(out) > target_chars + 100:
            out = out[: target_chars - 3] + "..."
        return out

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
        raw_url = (cfg.get("ollama_url") or "http://localhost:11434").strip()
        # Allow only http/https schemes and strip trailing slash
        try:
            from urllib.parse import urlparse
            parsed = urlparse(raw_url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in ("http", "https"):
                base_url = "http://localhost:11434"
            elif host not in ("localhost", "127.0.0.1"):
                # Restrict to loopback to avoid SSRF; remote access should use SSH tunnel which also binds localhost
                base_url = "http://localhost:11434"
            else:
                base_url = raw_url.rstrip("/")
        except Exception:
            base_url = "http://localhost:11434"
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
    def _get_current_patient_ids(self) -> list[int]:
        """Return all patient IDs available in the patients table for this user DB."""
        try:
            with self.db_engine.connect() as conn:
                rows = conn.execute(text("SELECT id FROM patients WHERE id IS NOT NULL")).fetchall()
            ids = []
            for r in (rows or []):
                try:
                    ids.append(int(r[0]))
                except Exception:
                    continue
            # ensure unique and stable order
            return sorted(set(ids))
        except Exception:
            return []

    def _inline_patient_id(self, sql: str) -> str:
        """Replace patient_id parameter placeholders with the current patient id(s) literal.

        - Only operates outside quotes
    - Replaces patterns like: patient_id = ?  or patient_id = :patient_id or patient_id = 123 with IN (...)
        - Leaves SQL unchanged if no patient ids available
        - After replacement, if any remaining parameter markers (? or :name) exist, returns empty string to trigger retry
        """
        if not sql:
            return sql
        pids = self._get_current_patient_ids()
        if not pids:
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
        in_list = ", ".join(str(i) for i in pids)
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
                # Try regex from this position for alias?.patient_id = (?|:name|123)
                m = re.match(r"((?:[A-Za-z_][A-Za-z0-9_]*\.)?)patient_id\s*=\s*(\?|:[A-Za-z_][A-Za-z0-9_]*|\d+)", sql[i:])
                if m:
                    # Preserve optional alias prefix
                    prefix = m.group(1) or ""
                    repl = f"{prefix}patient_id IN ({in_list})"
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

    def _table_has_column(self, table: str, column: str) -> bool:
        try:
            insp = inspect(self.db_engine)
            cols = [c.get('name') for c in (insp.get_columns(table) or [])]
            return column in (cols or [])
        except Exception:
            return False

    def _first_table_label(self, sql: str) -> str | None:
        """Best-effort extraction of the first table name after FROM for labeling purposes."""
        try:
            if not sql:
                return None
            m = re.search(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.IGNORECASE)
            if not m:
                return None
            return m.group(1).strip().capitalize()
        except Exception:
            return None

    def _short_sql_desc(self, sql: str, limit: int = 80) -> str | None:
        """Create a compact human-readable description for progress lines.

        Prefers "Table: columns" from the SQL description; truncates to limit.
        """
        try:
            if not sql:
                return None
            tbl = self._first_table_label(sql)
            d = self._describe_sql(sql) or ""
            cols = None
            m = re.search(r"showing\s+([^;\.]+)", d, flags=re.IGNORECASE)
            if m:
                cols = m.group(1).strip()
            if cols:
                core = f"{tbl}: {cols}" if tbl else cols
            else:
                core = d
            core = (core or "").strip().rstrip(".")
            if not core:
                core = tbl or ""
            if not core:
                return None
            if len(core) > limit:
                return core[: limit - 1] + "…"
            return core
        except Exception:
            return None

    # ---------------- Conversation summarization for SQL generation -----------------
    def _summarize_conversation_for_sql(self, chat_history: list[dict] | None,
                                        max_messages: int = 12,
                                        max_chars: int = 1500) -> str | None:
        """Summarize recent conversation turns to ground SQL generation on context.

        - Uses last max_messages turns
        - Truncates to max_chars for prompt efficiency
        - Formats as simple User:/Assistant: lines
        """
        if not chat_history:
            return None
        tail = (chat_history or [])[-max_messages:]
        lines: list[str] = []
        for m in tail:
            role = m.get("role", "user")
            role_label = "User" if role == "user" else "Assistant"
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role_label}: {content}")
        if not lines:
            return None
        s = "\n".join(lines)
        if len(s) > max_chars:
            s = s[-max_chars:]
        return s

    # ---------------- SQL description helper -----------------
    def _describe_sql(self, sql: str) -> str:
        """Heuristically describe a SELECT/WITH SQLite query in plain language.

        Keeps it short: tables involved, key filters, sorting, grouping, and row limit.
        Safe and deterministic (no LLM call).
        """
        if not sql:
            return ""
        s = (sql or "").strip()
        low = s.lower()

        def _slice(after: str, until: list[str]) -> str:
            try:
                i = low.index(after)
            except ValueError:
                return ""
            j = len(s)
            for u in until:
                try:
                    k = low.index(u, i + len(after))
                    j = min(j, k)
                except ValueError:
                    pass
            return s[i + len(after):j].strip()

        # Extract core clauses
        sel = _slice("select", [" from ", ";"]).strip()
        frm = _slice(" from ", [" where ", " group by ", " order by ", " limit ", ";"]).strip()
        whr = _slice(" where ", [" group by ", " order by ", " limit ", ";"]).strip()
        grp = _slice(" group by ", [" order by ", " limit ", ";"]).strip()
        ordby = _slice(" order by ", [" limit ", ";"]).strip()
        lim = _slice(" limit ", [";"]).strip()

        # Tables (split on joins/commas)
        tables: list[str] = []
        if frm:
            # Remove join conditions
            core = re.split(r"\bjoin\b|\bon\b", frm, flags=re.IGNORECASE)[0]
            # Split by commas or whitespace chains
            parts = re.split(r"\s*,\s*|\s+", core)
            # Filter plausible identifiers
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                # Skip aliases keywords
                if p.lower() in {"as"}:
                    continue
                # remove alias after a table name e.g., notes n
                tables.append(p)
            # post-process: collapse alias sequences like ['notes','n'] -> ['notes']
            if len(tables) >= 2 and len(tables[0]) and len(tables[1]) == 1:
                tables = [tables[0]]

        # Columns list (approximate)
        cols_desc = "all columns"
        if sel:
            if "*" in sel:
                cols_desc = "all columns"
            else:
                cols = [c.strip() for c in sel.split(",") if c.strip()]
                # Remove function wrappers for brevity
                clean_cols = []
                for c in cols[:6]:
                    c2 = re.sub(r"\b(count|avg|sum|min|max)\s*\((.*?)\)", r"\1(\2)", c, flags=re.IGNORECASE)
                    clean_cols.append(c2)
                cols_desc = ", ".join(clean_cols)
                if len(cols) > 6:
                    cols_desc += ", …"

        desc_parts: list[str] = []
        if tables:
            desc_parts.append(f"Rows from {', '.join(tables)}")
        else:
            desc_parts.append("Rows from the database")

        if cols_desc:
            desc_parts.append(f"showing {cols_desc}")

        if whr:
            w = re.sub(r"\s+", " ", whr)
            if len(w) > 220:
                w = w[:220] + "…"
            desc_parts.append(f"filtered by: {w}")

        if grp:
            g = re.sub(r"\s+", " ", grp)
            desc_parts.append(f"grouped by {g}")

        if ordby:
            o = re.sub(r"\s+", " ", ordby)
            desc_parts.append(f"sorted by {o}")

        if lim:
            n = re.findall(r"\d+", lim)
            if n:
                desc_parts.append(f"up to {n[0]} row(s)")

        # Aggregation hint
        if re.search(r"\b(count|avg|sum|min|max)\s*\(", sel, flags=re.IGNORECASE):
            desc_parts.append("includes aggregated metrics")

        return "; ".join(desc_parts) + "."

    def describe_sql(self, sql: str) -> str:
        """Public helper to describe a SQL query succinctly."""
        try:
            return self._describe_sql(sql)
        except Exception:
            return "Retrieves relevant rows from the database."

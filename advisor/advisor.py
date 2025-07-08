#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import sqlite3
import json
import os
import textwrap
import platform
import requests 

# --- Configuration ---
API_CACHE_FILE = ".gemini_api_key.cache"
DB_CACHE_FILE = ".database_path.cache"
MODEL_NAME = "gemini-2.5-flash"

class PersonalMedicalAdvisorApp(tk.Tk):
    """
    A standalone desktop application for getting personalized medical advice
    by querying a local medical database and the Gemini API.
    """
    def __init__(self):
        super().__init__()
        self.title("Personal Medical Advisor")
        self.geometry("1200x800")
        self.minsize(800, 600)

        # --- App State ---
        self.api_key = ""
        self.db_path = ""
        self.conversation_history = []
        self.retrieved_data = ""
        
        # --- Font Management ---
        self.base_font_size = 12 # Increased default font size
        self.fonts = {}

        # --- UI Initialization ---
        self._configure_styles()
        self._create_widgets()
        self._load_cached_data()
        self._apply_font_settings()
        self._bind_shortcuts()

    def _configure_styles(self):
        """Configures the visual style of the application using ttk."""
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        # --- Modern Color Scheme ---
        self.colors = {
            "bg_main": "#f0f4f8",
            "bg_sidebar": "#ffffff",
            "bg_chat": "#ffffff",
            "bg_input": "#ffffff",
            "text_primary": "#1e293b",
            "text_secondary": "#475569",
            "accent": "#0ea5e9",
            "accent_hover": "#0284c7",
            "border": "#e2e8f0",
            "info": "#0369a1",
            "error": "#dc2626",
            "user_msg": "#075985",
            "bot_msg": "#166534"
        }

        self.configure(background=self.colors["bg_main"])
        self.style.configure("TFrame", background=self.colors["bg_main"])
        self.style.configure("Card.TFrame", background=self.colors["bg_sidebar"], borderwidth=1, relief="solid", bordercolor=self.colors["border"])
        self.style.configure("TLabel", background=self.colors["bg_sidebar"], foreground=self.colors["text_primary"])
        self.style.configure("Status.TLabel", background=self.colors["bg_sidebar"], foreground=self.colors["text_secondary"])
        self.style.configure("Title.TLabel", font=("Arial", 18, "bold"), background=self.colors["bg_sidebar"])
        self.style.configure("TLabelframe", background=self.colors["bg_sidebar"], bordercolor=self.colors["border"])
        self.style.configure("TLabelframe.Label", background=self.colors["bg_sidebar"], foreground=self.colors["text_secondary"], font=("Arial", 10, "bold"))

        # --- Button Styles ---
        self.style.map("TButton",
            background=[('active', self.colors["accent_hover"]), ('!disabled', self.colors["accent"])],
            foreground=[('!disabled', 'white')]
        )
        self.style.configure("TButton", font=("Arial", 10, "bold"), padding=10, borderwidth=0, relief="flat", focuscolor=self.colors["accent"])
        
        self.style.map("Reset.TButton",
            background=[('active', '#fee2e2'), ('!disabled', '#fef2f2')],
            foreground=[('!disabled', '#b91c1c')]
        )
        self.style.configure("Reset.TButton", font=("Arial", 10, "bold"), padding=10, borderwidth=1, relief="solid")
        self.style.map("Reset.TButton", bordercolor=[('!disabled', '#fecaca')])

        # --- Entry Style ---
        self.style.configure("TEntry",
            fieldbackground=self.colors["bg_input"],
            foreground=self.colors["text_primary"],
            borderwidth=1,
            relief="solid",
            padding=10
        )
        self.style.map("TEntry",
            bordercolor=[('focus', self.colors["accent"]), ('!focus', self.colors["border"])]
        )

    def _apply_font_settings(self):
        """Applies all font configurations to the widgets. Called on init and when font size changes."""
        self.fonts = {
            "normal": ("Arial", self.base_font_size),
            "bold": ("Arial", self.base_font_size, "bold"),
            "italic": ("Arial", self.base_font_size, "italic"),
            "h1": ("Arial", self.base_font_size + 6, "bold"),
            "h2": ("Arial", self.base_font_size + 3, "bold"),
            "code": ("Courier New", self.base_font_size - 1),
        }
        
        # Update chat display tags for markdown rendering
        self.chat_display.tag_configure("h1", font=self.fonts["h1"], spacing3=10)
        self.chat_display.tag_configure("h2", font=self.fonts["h2"], spacing3=8)
        self.chat_display.tag_configure("bold", font=self.fonts["bold"])
        self.chat_display.tag_configure("italic", font=self.fonts["italic"])
        self.chat_display.tag_configure("code", font=self.fonts["code"], background="#f8fafc", relief="sunken", borderwidth=1, lmargin1=10, lmargin2=10, spacing1=5, spacing3=5)
        self.chat_display.tag_configure("bullet", font=self.fonts["normal"], lmargin1=25, lmargin2=25)
        self.chat_display.tag_configure("info", font=self.fonts["italic"], foreground=self.colors["info"])
        self.chat_display.tag_configure("error", font=self.fonts["bold"], foreground=self.colors["error"])
        self.chat_display.tag_configure("user_msg", font=self.fonts["bold"], foreground=self.colors["user_msg"])
        self.chat_display.tag_configure("bot_msg", font=self.fonts["bold"], foreground=self.colors["bot_msg"])
        
        # Update other widgets
        self.symptom_entry.configure(font=self.fonts["normal"])

    def _bind_shortcuts(self):
        """Binds keyboard shortcuts for font size adjustment."""
        modifier = "Command" if platform.system() == "Darwin" else "Control"
        self.bind(f"<{modifier}-plus>", self.increase_font_size)
        self.bind(f"<{modifier}-equal>", self.increase_font_size) # plus is often on the = key
        self.bind(f"<{modifier}-minus>", self.decrease_font_size)

    def increase_font_size(self, event=None):
        self.base_font_size += 1
        self._apply_font_settings()

    def decrease_font_size(self, event=None):
        if self.base_font_size > 8:
            self.base_font_size -= 1
            self._apply_font_settings()

    def _create_widgets(self):
        """Creates and arranges all the main widgets of the application."""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Left Sidebar ---
        left_frame = ttk.Frame(self, width=320, style="Card.TFrame", padding=20)
        left_frame.grid(row=0, column=0, sticky="nsw", padx=(10, 5), pady=10)
        left_frame.grid_propagate(False)
        self._create_left_pane(left_frame)

        # --- Right Main Area ---
        right_frame = ttk.Frame(self, padding=(5, 10, 10, 10))
        right_frame.grid(row=0, column=1, sticky="nsew")
        self._create_right_pane(right_frame)

    def _create_left_pane(self, parent):
        """Populates the left sidebar with controls."""
        parent.columnconfigure(0, weight=1)
        
        # --- App Title ---
        title_label = ttk.Label(parent, text="🩺 Medical Advisor", style="Title.TLabel")
        title_label.grid(row=0, column=0, pady=(0, 25), sticky="w")

        # --- Database Setup Card ---
        db_frame = ttk.LabelFrame(parent, text="Medical Database", padding=15)
        db_frame.grid(row=1, column=0, sticky="ew", pady=10)
        db_frame.columnconfigure(0, weight=1)
        self.db_status_label = ttk.Label(db_frame, text="No database selected.", style="Status.TLabel", wraplength=250)
        self.db_status_label.grid(row=0, column=0, sticky="ew")
        db_button = ttk.Button(db_frame, text="📁 Select Database File", command=self.select_database)
        db_button.grid(row=1, column=0, pady=(10, 0), sticky="ew")

        # --- API Key Setup Card ---
        api_frame = ttk.LabelFrame(parent, text="Gemini API Key", padding=15)
        api_frame.grid(row=2, column=0, sticky="ew", pady=10)
        api_frame.columnconfigure(0, weight=1)
        self.api_status_label = ttk.Label(api_frame, text="API key not set.", style="Status.TLabel")
        self.api_status_label.grid(row=0, column=0, sticky="ew")
        api_button = ttk.Button(api_frame, text="🔑 Set API Key", command=self.set_api_key)
        api_button.grid(row=1, column=0, pady=(10, 0), sticky="ew")

        # --- Reset Button ---
        reset_button = ttk.Button(parent, text="🔄 Reset Conversation", command=self.reset_conversation, style="Reset.TButton")
        reset_button.grid(row=3, column=0, sticky="ew", pady=(20, 10))

    def _create_right_pane(self, parent):
        """Populates the right main area with the chat interface."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        # --- Chat Display Area ---
        chat_container = ttk.Frame(parent, style="Card.TFrame")
        chat_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        chat_container.rowconfigure(0, weight=1)
        chat_container.columnconfigure(0, weight=1)

        self.chat_display = tk.Text(chat_container, wrap=tk.WORD, state=tk.DISABLED, bg=self.colors["bg_chat"],
                                    relief="flat", borderwidth=0, padx=20, pady=20,
                                    fg=self.colors["text_primary"])
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        
        self.markdown_renderer = MarkdownRenderer(self.chat_display, self.colors, self.fonts)

        scrollbar = ttk.Scrollbar(chat_container, command=self.chat_display.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_display['yscrollcommand'] = scrollbar.set

        # --- User Input Area ---
        input_frame = ttk.Frame(parent)
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.symptom_entry = ttk.Entry(input_frame, style="TEntry")
        self.symptom_entry.grid(row=0, column=0, sticky="ew", padx=(0,10))
        self.symptom_entry.bind("<Return>", self.handle_symptom_submission)

        self.send_button = ttk.Button(input_frame, text="➤ Send", command=self.handle_symptom_submission)
        self.send_button.grid(row=0, column=1, sticky="e")
        
        self.disable_chat_input("Please select a database and set your API key.")
    
    def _load_cached_data(self):
        """Loads API key and DB path from cache files on startup."""
        if os.path.exists(API_CACHE_FILE):
            with open(API_CACHE_FILE, 'r') as f:
                self.api_key = f.read().strip()
            self.api_status_label.config(text="API key loaded from cache.", foreground="green")
        
        if os.path.exists(DB_CACHE_FILE):
            with open(DB_CACHE_FILE, 'r') as f:
                self.db_path = f.read().strip()
            if os.path.exists(self.db_path):
                self.db_status_label.config(text=f"DB: {os.path.basename(self.db_path)}", foreground="green")
            else:
                self.db_path = "" # Invalidate if path no longer exists
        
        self.check_setup_completion()

    def select_database(self):
        """Opens a file dialog to select the SQLite database."""
        path = filedialog.askopenfilename(
            title="Select your SQLite medical database",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
        )
        if path:
            self.db_path = path
            with open(DB_CACHE_FILE, 'w') as f:
                f.write(self.db_path)
            self.db_status_label.config(text=f"DB: {os.path.basename(self.db_path)}", foreground="green")
            self.markdown_renderer.display_info(f"Database selected: {self.db_path}")
            self.check_setup_completion()

    def set_api_key(self):
        """Opens a dialog to securely input the Gemini API key."""
        key = simpledialog.askstring("API Key", "Please enter your Gemini API key:", show='*')
        if key:
            self.api_key = key.strip()
            with open(API_CACHE_FILE, 'w') as f:
                f.write(self.api_key)
            self.api_status_label.config(text="API key has been set.", foreground="green")
            self.markdown_renderer.display_info("API Key has been set.")
            self.check_setup_completion()

    def check_setup_completion(self):
        """Enables or disables the chat input based on setup status."""
        if self.api_key and self.db_path:
            self.enable_chat_input("Please describe your symptoms...")
            return True
        self.disable_chat_input("Please select a database and set your API key.")
        return False

    def disable_chat_input(self, message):
        """Disables the user input field and shows a message."""
        self.symptom_entry.config(state=tk.DISABLED)
        self.symptom_entry.delete(0, tk.END)
        self.symptom_entry.insert(0, message)
        self.send_button.config(state=tk.DISABLED)

    def enable_chat_input(self, placeholder):
        """Enables the user input field with a placeholder text."""
        self.symptom_entry.config(state=tk.NORMAL)
        self.symptom_entry.delete(0, tk.END)
        self.symptom_entry.insert(0, placeholder)
        self.send_button.config(state=tk.NORMAL)
        
    def reset_conversation(self):
        """Clears the conversation and resets the state."""
        if messagebox.askokcancel("Reset", "Are you sure you want to clear the conversation and start over?"):
            self.conversation_history = []
            self.retrieved_data = ""
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete('1.0', tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.markdown_renderer.display_info("Conversation reset. Please enter your symptoms.")
            self.check_setup_completion()

    def call_gemini_api(self, prompt, is_json_output=False):
        """A wrapper for making calls to the Gemini API."""
        self.markdown_renderer.display_info(f"Querying Gemini ({'JSON mode' if is_json_output else 'Text mode'})...")
        self.update_idletasks()

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        if is_json_output:
            payload["generationConfig"] = {"responseMimeType": "application/json"}

        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={self.api_key}",
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )
            response.raise_for_status()
            
            response_json = response.json()
            if 'candidates' in response_json and response_json['candidates']:
                 content = response_json['candidates'][0]['content']['parts'][0]['text']
                 return content
            else:
                error_msg = response_json.get('error', {}).get('message', 'No valid candidates in response.')
                self.markdown_renderer.display_error(f"API Error: {error_msg}")
                return None

        except requests.exceptions.RequestException as e:
            self.markdown_renderer.display_error(f"Network error calling Gemini API: {e}")
            return None
        except Exception as e:
            self.markdown_renderer.display_error(f"An unexpected error occurred during API call: {e}")
            return None

    def handle_symptom_submission(self, event=None):
        """Handles the user submitting their symptoms."""
        symptoms = self.symptom_entry.get().strip()
        if not symptoms or "Please describe" in symptoms:
            return
            
        self.markdown_renderer.render(symptoms, sender="user")
        self.conversation_history.append({"role": "user", "parts": [{"text": symptoms}]})
        self.disable_chat_input("Thinking...")
        self.update_idletasks()

        self.run_retrieval_and_advice_flow(symptoms)
        
    def run_retrieval_and_advice_flow(self, symptoms):
        """Orchestrates the multi-step process of getting advice."""
        # Step 1: Get DB Schema
        schema = self.get_db_schema()
        if not schema:
            self.enable_chat_input("Could not read database schema. Please check the file.")
            return

        # Step 2: Ask Gemini for relevant categories
        prompt1 = self._create_categories_prompt(symptoms, schema)
        categories_json_str = self.call_gemini_api(prompt1, is_json_output=True)
        if not categories_json_str:
            self.enable_chat_input("Failed to get relevant categories. Please try again.")
            return

        try:
            categories = json.loads(categories_json_str).get("categories", [])
        except json.JSONDecodeError:
            self.markdown_renderer.display_error("Failed to parse categories from API response.")
            self.enable_chat_input("An error occurred. Please try again.")
            return
            
        # Step 3: Ask Gemini for specific SQL queries
        prompt2 = self._create_queries_prompt(categories, schema)
        queries_json_str = self.call_gemini_api(prompt2, is_json_output=True)
        if not queries_json_str:
            self.enable_chat_input("Failed to get SQL queries. Please try again.")
            return
            
        try:
            queries = json.loads(queries_json_str).get("queries", [])
        except json.JSONDecodeError:
            self.markdown_renderer.display_error("Failed to parse SQL queries from API response.")
            self.enable_chat_input("An error occurred. Please try again.")
            return

        # Step 4: Execute queries and display for confirmation
        self.retrieved_data = self.execute_db_queries(queries)
        self.display_retrieved_data_and_confirm()

    def _create_categories_prompt(self, symptoms, schema):
        return textwrap.dedent(f"""
            A user is reporting the following symptoms: "{symptoms}".
            Based on these symptoms, what categories of medical information would be most relevant to retrieve from their personal health record?
            The available tables and their schemas are:
            {schema}
            
            Please respond with a JSON object containing a single key "categories" which is a list of strings. Each string should be a brief, user-friendly description of a relevant data category.
            For example: ["Recent blood pressure readings", "Current active medications", "History of surgeries related to the abdomen"].
        """)

    def _create_queries_prompt(self, categories, schema):
        return textwrap.dedent(f"""
            Based on the need for the following information categories: {categories},
            and the following database schema:
            {schema}
            
            Generate the SQLite3 queries required to retrieve this information.
            **IMPORTANT**: The queries must be very specific to retrieve only the minimal necessary data. Do NOT use `SELECT *`. Select only the specific columns needed. For any query on a table that has a `patient_id` column, you **MUST** include `WHERE patient_id = ?` in the query. Use other `WHERE` clauses with dates or other conditions to further narrow down results where appropriate.
            
            Please respond with a JSON object containing a single key "queries" which is a list of strings, where each string is a single, valid SQLite3 query.
            Example of a good specific query: "SELECT medication_name, start_date FROM medications WHERE patient_id = ? AND status = 'active' ORDER BY start_date DESC LIMIT 5;"
        """)

    def get_db_schema(self):
        """Reads the schema of the user's database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                return "\n".join([table[0] for table in tables if table[0]])
        except sqlite3.Error as e:
            self.markdown_renderer.display_error(f"Database error reading schema: {e}")
            return ""
            
    def execute_db_queries(self, queries):
        """Executes a list of SQL queries and returns a formatted string of the results."""
        all_results = []
        if not queries:
            return "No relevant information found or no queries were generated."
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("SELECT id FROM patients LIMIT 1")
                patient_id_row = cursor.fetchone()
                if not patient_id_row:
                    return "Error: Could not find a patient record in the database."
                patient_id = patient_id_row[0]

                for query in queries:
                    try:
                        params = (patient_id,) if '?' in query else ()
                        cursor.execute(query, params)
                        rows = cursor.fetchall()
                        if rows:
                            header = list(rows[0].keys())
                            all_results.append(f"--- Query: {query} ---\n")
                            all_results.append(", ".join(header))
                            for row in rows:
                                all_results.append(", ".join(str(item) for item in row))
                            all_results.append("\n")
                    except sqlite3.Error as e:
                        all_results.append(f"--- Error running query: {query} ---\nError: {e}\n")
            return "\n".join(all_results) if all_results else "The queries ran successfully but returned no data."
        except sqlite3.Error as e:
            self.markdown_renderer.display_error(f"Database connection error: {e}")
            return "Error connecting to the database."

    def display_retrieved_data_and_confirm(self):
        """Shows the retrieved data to the user and asks for confirmation to proceed."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "System:\n", ("info", "bold"))
        self.chat_display.insert(tk.END, "I've retrieved the following information. Is it okay to send this with your symptoms to get advice?\n\n", "info")
        self.chat_display.insert(tk.END, self.retrieved_data, "code")
        self.chat_display.insert(tk.END, "\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
        # Add confirmation buttons in a frame
        confirm_frame = tk.Frame(self.chat_display, bg=self.colors["bg_chat"])
        
        yes_btn = ttk.Button(confirm_frame, text="✅ Yes, Get Advice", command=self.get_final_advice)
        yes_btn.pack(side=tk.LEFT, padx=10)
        
        no_btn = ttk.Button(confirm_frame, text="❌ No, Cancel", command=self.cancel_advice, style="Reset.TButton")
        no_btn.pack(side=tk.LEFT)
        
        self.chat_display.window_create(tk.END, window=confirm_frame)
        self.chat_display.insert(tk.END, '\n')

    def get_final_advice(self):
        """Sends all context to Gemini for the final advice."""
        self.clear_confirmation_buttons()
        self.markdown_renderer.display_info("Confirmed. Getting medical advice now...")
        
        symptoms = self.conversation_history[-1]['parts'][0]['text']
        
        prompt3 = self._create_final_advice_prompt(symptoms, self.retrieved_data)
        
        self.conversation_history.append({"role": "user", "parts": [{"text": prompt3}]})
        
        advice = self.call_gemini_api(prompt3)
        if advice:
            self.conversation_history.append({"role": "model", "parts": [{"text": advice}]})
            self.markdown_renderer.render(advice, sender="bot")
        else:
            self.markdown_renderer.display_error("Could not get a response. Please check your API key and network connection.")
            
        self.enable_chat_input("You can ask a follow-up question or start a new topic.")

    def _create_final_advice_prompt(self, symptoms, context_data):
        return textwrap.dedent(f"""
            You are a helpful and cautious AI medical assistant. A user has provided their symptoms and relevant data from their medical record.
            Your task is to provide a helpful, structured, and safe response.
            
            **IMPORTANT**: Start your response with a clear disclaimer that you are an AI and not a medical professional, and that the user should consult a real doctor for any serious concerns.
            
            Here is the information:
            
            SYMPTOMS REPORTED BY USER:
            "{symptoms}"
            
            RELEVANT MEDICAL DATA RETRIEVED FROM USER'S RECORD:
            ---
            {context_data}
            ---
            
            Based on all of this information, please provide a helpful analysis and potential next steps for the user. Structure your response using Markdown with headers, bold text, and lists to make it easy to read. Do not ask for more information, provide a complete response based on what is given.
        """)

    def cancel_advice(self):
        """Cancels the current operation and re-enables input."""
        self.clear_confirmation_buttons()
        self.markdown_renderer.display_info("Operation cancelled. You can ask another question or modify your symptoms.")
        self.enable_chat_input("Please describe your symptoms...")
        
    def clear_confirmation_buttons(self):
        """Removes the confirmation button frame from the chat window."""
        for child in self.chat_display.winfo_children():
            if isinstance(child, tk.Frame):
                child.destroy()


class MarkdownRenderer:
    """A simple parser and renderer for basic Markdown in a Tkinter Text widget."""
    def __init__(self, text_widget, colors, fonts):
        self.text = text_widget
        self.colors = colors
        self.fonts = fonts

    def render(self, markdown_text, sender="bot"):
        self.text.config(state=tk.NORMAL)
        
        sender_tag = "user_msg" if sender == "user" else "bot_msg"
        self.text.insert(tk.END, f"{sender.title()}:\n", (sender_tag))

        for line in markdown_text.split('\n'):
            if line.startswith('# '):
                self.text.insert(tk.END, line[2:] + '\n\n', 'h1')
            elif line.startswith('## '):
                self.text.insert(tk.END, line[3:] + '\n', 'h2')
            elif line.startswith('* '):
                self.text.insert(tk.END, f"  • {line[2:]}\n", 'bullet')
            else:
                self.process_inline_formatting(line + '\n')
        
        self.text.insert(tk.END, "\n" + "—"*80 + "\n\n")
        self.text.config(state=tk.DISABLED)
        self.text.see(tk.END)

    def process_inline_formatting(self, line):
        parts = line.split('**')
        for i, part in enumerate(parts):
            if i % 2 == 1 and part:
                self.text.insert(tk.END, part, 'bold')
            elif part:
                self.text.insert(tk.END, part)

    def display_info(self, message):
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, f"System: {message}\n\n", "info")
        self.text.config(state=tk.DISABLED)
        self.text.see(tk.END)
        
    def display_error(self, message):
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, f"ERROR: {message}\n\n", "error")
        self.text.config(state=tk.DISABLED)
        self.text.see(tk.END)

if __name__ == "__main__":
    app = PersonalMedicalAdvisorApp()
    app.mainloop()

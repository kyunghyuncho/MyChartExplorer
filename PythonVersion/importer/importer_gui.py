import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import json
import os
import textwrap
import platform
import xml.etree.ElementTree as ET
from datetime import datetime

# --- Configuration ---
NS = {'cda': 'urn:hl7-org:v3', 'sdtc': 'urn:hl7-org:sdtc'}

# --- Main Application Class ---
class MyChartImporterGUI(tk.Tk):
    """
    A standalone desktop application with a GUI for importing MyChart XML files
    into a structured SQLite database.
    """
    def __init__(self):
        super().__init__()
        self.title("MyChart XML Importer")
        self.geometry("800x600")
        self.minsize(600, 500)

        self.xml_files = []
        self.output_db_path = ""

        self._configure_styles()
        self._create_widgets()

    def _configure_styles(self):
        """Configures the visual style of the application using ttk."""
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        self.colors = {
            "bg_main": "#f0f4f8",
            "bg_card": "#ffffff",
            "bg_chat": "#f8f9fa",
            "text_primary": "#1e293b",
            "text_secondary": "#475569",
            "accent": "#0ea5e9",
            "accent_hover": "#0284c7",
            "border": "#e2e8f0",
            "success": "#16a34a",
            "error": "#dc2626"
        }

        self.configure(background=self.colors["bg_main"])
        self.style.configure("TFrame", background=self.colors["bg_main"])
        self.style.configure("Card.TFrame", background=self.colors["bg_card"], borderwidth=1, relief="solid", bordercolor=self.colors["border"])
        self.style.configure("TLabel", background=self.colors["bg_card"], foreground=self.colors["text_primary"], font=("Arial", 11))
        self.style.configure("Title.TLabel", font=("Arial", 18, "bold"), background=self.colors["bg_card"])
        self.style.configure("Step.TLabel", font=("Arial", 12, "bold"), foreground=self.colors["accent"], background=self.colors["bg_card"])
        self.style.configure("Status.TLabel", font=("Arial", 9, "italic"), foreground=self.colors["text_secondary"], background=self.colors["bg_card"])

        self.style.map("TButton",
            background=[('active', self.colors["accent_hover"]), ('!disabled', self.colors["accent"])],
            foreground=[('!disabled', 'white')]
        )
        self.style.configure("TButton", font=("Arial", 10, "bold"), padding=8, borderwidth=0, relief="flat")

    def _create_widgets(self):
        """Creates and arranges all the main widgets."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        controls_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self._create_controls_area(controls_frame)

        log_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=5)
        log_frame.grid(row=1, column=0, sticky="nsew")
        self._create_log_area(log_frame)

    def _create_controls_area(self, parent):
        """Populates the top control area with buttons and labels."""
        parent.columnconfigure(1, weight=1)
        
        title = ttk.Label(parent, text="MyChart Data Importer", style="Title.TLabel")
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 20))

        # --- Step 1: Select Files ---
        step1_label = ttk.Label(parent, text="Step 1: Select XML Files", style="Step.TLabel")
        step1_label.grid(row=1, column=0, sticky="w", columnspan=3)
        
        self.file_listbox = tk.Listbox(parent, height=5, selectmode=tk.EXTENDED, relief="solid", bd=1, bg=self.colors["bg_main"])
        self.file_listbox.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)

        btn_frame = ttk.Frame(parent, style="Card.TFrame")
        btn_frame.grid(row=3, column=0, columnspan=3, sticky="w")
        add_btn = ttk.Button(btn_frame, text="➕ Add Files", command=self.add_files)
        add_btn.pack(side=tk.LEFT, padx=(0, 10))
        clear_btn = ttk.Button(btn_frame, text="➖ Clear List", command=self.clear_files)
        clear_btn.pack(side=tk.LEFT)

        # --- Step 2: Choose Output ---
        step2_label = ttk.Label(parent, text="Step 2: Choose Output Database", style="Step.TLabel")
        step2_label.grid(row=4, column=0, sticky="w", columnspan=3, pady=(20, 0))
        
        self.db_path_label = ttk.Label(parent, text="No database file selected.", style="Status.TLabel", wraplength=500)
        self.db_path_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=5)
        
        db_btn = ttk.Button(parent, text="📁 Set Database", command=self.set_output_db)
        db_btn.grid(row=5, column=2, sticky="e")

        # --- Step 3: Run ---
        self.start_button = ttk.Button(parent, text="🚀 Start Import", command=self.start_import_process)
        self.start_button.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(20, 0))
        self.start_button.config(state=tk.DISABLED)

    def _create_log_area(self, parent):
        """Creates the text area for logging progress."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(parent, wrap=tk.WORD, state=tk.DISABLED, bg=self.colors["bg_chat"],
                                relief="flat", bd=0, padx=15, pady=15, font=("Courier New", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(parent, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text['yscrollcommand'] = scrollbar.set
        
        self.log_text.tag_configure("INFO", foreground=self.colors["text_secondary"])
        self.log_text.tag_configure("SUCCESS", foreground=self.colors["success"], font=("Courier New", 10, "bold"))
        self.log_text.tag_configure("ERROR", foreground=self.colors["error"], font=("Courier New", 10, "bold"))
        self.log_text.tag_configure("HEADER", foreground=self.colors["accent"], font=("Courier New", 10, "bold"))

    def log_message(self, message, level="INFO"):
        """Adds a message to the log text area with appropriate styling."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", level)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)
        self.update_idletasks()

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select XML files", filetypes=[("XML Files", "*.xml")])
        for f in files:
            if f not in self.xml_files:
                self.xml_files.append(f)
                self.file_listbox.insert(tk.END, os.path.basename(f))
        self.validate_inputs()

    def clear_files(self):
        self.xml_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.validate_inputs()

    def set_output_db(self):
        path = filedialog.asksaveasfilename(title="Set Output SQLite Database", defaultextension=".db", filetypes=[("SQLite Database", "*.db")])
        if path:
            self.output_db_path = path
            self.db_path_label.config(text=f"Output: {os.path.basename(path)}")
        self.validate_inputs()

    def validate_inputs(self):
        """Checks if all inputs are ready and enables/disables the start button."""
        if self.xml_files and self.output_db_path:
            self.start_button.config(state=tk.NORMAL)
        else:
            self.start_button.config(state=tk.DISABLED)

    def start_import_process(self):
        """The main entry point for the import logic."""
        self.log_message("Starting new import process...", "HEADER")
        self.start_button.config(state=tk.DISABLED)

        try:
            importer = DataImporter(self.output_db_path, self.log_message)
            importer.setup_database()

            for xml_file in self.xml_files:
                self.log_message(f"Processing file: {os.path.basename(xml_file)}")
                importer.process_xml_file(xml_file)
            
            self.log_message("Import process completed successfully!", "SUCCESS")

        except Exception as e:
            self.log_message(f"A critical error occurred: {e}", "ERROR")
            messagebox.showerror("Critical Error", f"An unexpected error stopped the import process: {e}")
        finally:
            self.start_button.config(state=tk.NORMAL)


# --- Data Importer Logic Class ---
class DataImporter:
    """
    Handles the core logic of parsing XML files and inserting data into the SQLite DB.
    Decoupled from the GUI to improve readability.
    """
    def __init__(self, db_path, logger):
        self.db_path = db_path
        self.log = logger
        self.conn = None
        self.cursor = None

    def setup_database(self):
        """Connects to the DB and creates tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self.cursor.executescript(SCHEMA)
            self.conn.commit()
            self.log("Database connection established and schema verified.", "SUCCESS")
        except sqlite3.Error as e:
            self.log(f"Database setup failed: {e}", "ERROR")
            raise

    def process_xml_file(self, xml_file):
        """Main processing function for a single XML file."""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            patient_id = self._ingest_patient(root)
            if patient_id is None:
                self.log(f"Could not find/create patient in {os.path.basename(xml_file)}. Skipping.", "ERROR")
                return
            
            # Ingest all other sections
            section_ingestors = {
                "Allergies": (self._ingest_allergies, '2.16.840.1.113883.10.20.22.2.6.1'),
                "Problems": (self._ingest_problems, '2.16.840.1.113883.10.20.22.2.5.1'),
                "Medications": (self._ingest_medications, '2.16.840.1.113883.10.20.22.2.1.1'),
                "Immunizations": (self._ingest_immunizations, '2.16.840.1.113883.10.20.22.2.2.1'),
                "Vitals": (self._ingest_vitals, '2.16.840.1.113883.10.20.22.2.4.1'),
                "Results": (self._ingest_results, '2.16.840.1.113883.10.20.22.2.3.1'),
                "Procedures": (self._ingest_procedures, '2.16.840.1.113883.10.20.22.2.7.1')
            }

            for name, (func, template_id) in section_ingestors.items():
                section = self._get_section(root, template_id)
                if section:
                    count = func(root, section, patient_id)
                    if count > 0:
                        self.log(f"  > Found {count} new record(s) in {name}.")
            
            self.conn.commit()

        except ET.ParseError as e:
            self.log(f"Error parsing XML file {os.path.basename(xml_file)}: {e}", "ERROR")
        except Exception as e:
            self.log(f"An unexpected error occurred with {os.path.basename(xml_file)}: {e}", "ERROR")

    # --- Helper Methods ---
    def _find_text(self, element, path):
        if element is None: return None
        el = element.find(path, NS)
        return el.text if el is not None else None

    def _find_attrib(self, element, path, attribute):
        if element is None: return None
        el = element.find(path, NS)
        return el.get(attribute) if el is not None else None

    def _get_section(self, root, template_id):
        for section in root.findall('.//cda:section', NS):
            if section.find(f"cda:templateId[@root='{template_id}']", NS) is not None:
                return section
        return None

    def _find_name_with_fallback(self, root, element, path_to_code_el):
        if element is None: return None
        code_el = element.find(path_to_code_el, NS)
        if code_el is None: return None
        
        name = code_el.get('displayName')
        if name: return name
        
        original_text_el = code_el.find('cda:originalText', NS)
        if original_text_el is not None:
            if original_text_el.text: return original_text_el.text
            reference_el = original_text_el.find('cda:reference', NS)
            if reference_el is not None:
                ref_id = reference_el.get('value')
                if ref_id and ref_id.startswith('#'):
                    referenced_el = root.find(f".//*[@ID='{ref_id[1:]}']")
                    if referenced_el is not None:
                        return ''.join(referenced_el.itertext()).strip()
        return None

    # --- Ingestion Logic ---
    # Each method now returns the count of new rows added.
    def _ingest_patient(self, root):
        patient_role = root.find('.//cda:recordTarget/cda:patientRole', NS)
        if patient_role is None: return None
        patient_el = patient_role.find('cda:patient', NS)
        
        given_name = self._find_text(patient_el, "cda:name/cda:given") or ""
        family_name = self._find_text(patient_el, "cda:name/cda:family") or ""
        full_name = f"{given_name} {family_name}".strip()

        dob = self._find_attrib(patient_el, 'cda:birthTime', 'value')
        mrn = self._find_attrib(patient_role, "cda:id", "extension")
        
        self.cursor.execute("SELECT id FROM patients WHERE mrn=? AND full_name=? AND dob=?", (mrn, full_name, dob))
        result = self.cursor.fetchone()
        if result:
            return result[0]
        else:
            self.cursor.execute("""
                INSERT INTO patients (mrn, full_name, dob, gender, marital_status, race, ethnicity, deceased, deceased_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (mrn, full_name, dob, self._find_attrib(patient_el, 'cda:administrativeGenderCode', 'displayName'), 
                  self._find_attrib(patient_el, 'cda:maritalStatusCode', 'displayName'), self._find_attrib(patient_el, 'cda:raceCode', 'displayName'),
                  self._find_attrib(patient_el, 'cda:ethnicGroupCode', 'displayName'), self._find_attrib(patient_el, 'sdtc:deceasedInd', 'value') == 'true',
                  self._find_attrib(patient_el, 'sdtc:deceasedTime', 'value')))
            return self.cursor.lastrowid

    def _ingest_allergies(self, root, section, patient_id):
        count = 0
        for entry in section.findall('.//cda:entry', NS):
            if entry.find('.//cda:observation[@negationInd="true"]', NS) is not None:
                continue
            substance = self._find_name_with_fallback(root, entry, './/cda:participant/cda:participantRole/cda:playingEntity/cda:code')
            self.cursor.execute("INSERT OR IGNORE INTO allergies (patient_id, substance, reaction, status, effective_date) VALUES (?, ?, ?, ?, ?)",
                (patient_id, substance, self._find_attrib(entry, './/cda:entryRelationship/cda:observation/cda:value', 'displayName'),
                 self._find_attrib(entry, './/cda:act/cda:statusCode', 'code'), self._find_attrib(entry, './/cda:effectiveTime/cda:low', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_problems(self, root, section, patient_id):
        count = 0
        for entry in section.findall('.//cda:entry', NS):
            obs = entry.find('.//cda:observation', NS)
            if obs is None: continue
            problem_name = self._find_name_with_fallback(root, obs, 'cda:value')
            self.cursor.execute("INSERT OR IGNORE INTO problems (patient_id, problem_name, status, onset_date, resolved_date) VALUES (?, ?, ?, ?, ?)",
                (patient_id, problem_name, self._find_attrib(obs, './/cda:entryRelationship/cda:observation/cda:value', 'displayName'),
                 self._find_attrib(obs, 'cda:effectiveTime/cda:low', 'value'), self._find_attrib(obs, 'cda:effectiveTime/cda:high', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_medications(self, root, section, patient_id):
        count = 0
        for entry in section.findall('.//cda:entry/cda:substanceAdministration', NS):
            med_name = self._find_name_with_fallback(root, entry, './/cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code')
            instructions = self._find_name_with_fallback(root, entry, 'cda:text')
            self.cursor.execute("INSERT OR IGNORE INTO medications (patient_id, medication_name, instructions, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
                (patient_id, med_name, instructions, self._find_attrib(entry, 'cda:statusCode', 'code'), 
                 self._find_attrib(entry, 'cda:effectiveTime/cda:low', 'value'), self._find_attrib(entry, 'cda:effectiveTime/cda:high', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_immunizations(self, root, section, patient_id):
        count = 0
        for entry in section.findall('.//cda:entry/cda:substanceAdministration', NS):
            vaccine_name = self._find_name_with_fallback(root, entry, 'cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code')
            self.cursor.execute("INSERT OR IGNORE INTO immunizations (patient_id, vaccine_name, date_administered) VALUES (?, ?, ?)",
                (patient_id, vaccine_name, self._find_attrib(entry, 'cda:effectiveTime', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_vitals(self, root, section, patient_id):
        count = 0
        for comp in section.findall('.//cda:component/cda:observation', NS):
            vital_sign = self._find_name_with_fallback(root, comp, 'cda:code')
            if not vital_sign: continue
            self.cursor.execute("INSERT OR IGNORE INTO vitals (patient_id, vital_sign, value, unit, effective_date) VALUES (?, ?, ?, ?, ?)",
                (patient_id, vital_sign, self._find_attrib(comp, 'cda:value', 'value'),
                 self._find_attrib(comp, 'cda:value', 'unit'), self._find_attrib(comp, 'cda:effectiveTime', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_results(self, root, section, patient_id):
        count = 0
        for comp in section.findall('.//cda:component/cda:observation', NS):
            test_name = self._find_name_with_fallback(root, comp, 'cda:code')
            if not test_name: continue
            value_el = comp.find('cda:value', NS)
            value, unit = None, None
            if value_el is not None:
                value = value_el.get('value') or value_el.get('displayName') or value_el.text
                unit = value_el.get('unit')
            self.cursor.execute("INSERT OR IGNORE INTO results (patient_id, test_name, value, unit, reference_range, interpretation, effective_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (patient_id, test_name, value, unit, self._find_text(comp, './/cda:referenceRange/cda:observationRange/cda:text'),
                 self._find_attrib(comp, 'cda:interpretationCode', 'displayName'), self._find_attrib(comp, 'cda:effectiveTime', 'value')))
            count += self.cursor.rowcount
        return count

    def _ingest_procedures(self, root, section, patient_id):
        count = 0
        for proc in section.findall('.//cda:entry/cda:procedure', NS):
            proc_name = self._find_name_with_fallback(root, proc, 'cda:code') or self._find_name_with_fallback(root, proc, './/cda:participant/cda:participantRole/cda:playingDevice/cda:code')
            self.cursor.execute("INSERT OR IGNORE INTO procedures (patient_id, procedure_name, date, provider) VALUES (?, ?, ?, ?)",
                (patient_id, proc_name, self._find_attrib(proc, 'cda:effectiveTime/cda:low', 'value') or self._find_attrib(proc, 'cda:effectiveTime', 'value'),
                 self._find_text(proc, './/cda:performer/cda:assignedEntity/cda:assignedPerson/cda:name')))
            count += self.cursor.rowcount
        return count

# --- Database Schema ---
SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY, mrn TEXT, full_name TEXT, dob TEXT, gender TEXT, marital_status TEXT, race TEXT, ethnicity TEXT, deceased BOOLEAN, deceased_date TEXT, UNIQUE(mrn, full_name, dob));
CREATE TABLE IF NOT EXISTS allergies (id INTEGER PRIMARY KEY, patient_id INTEGER, substance TEXT, reaction TEXT, status TEXT, effective_date TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, substance, effective_date));
CREATE TABLE IF NOT EXISTS problems (id INTEGER PRIMARY KEY, patient_id INTEGER, problem_name TEXT, status TEXT, onset_date TEXT, resolved_date TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, problem_name, onset_date));
CREATE TABLE IF NOT EXISTS medications (id INTEGER PRIMARY KEY, patient_id INTEGER, medication_name TEXT, instructions TEXT, status TEXT, start_date TEXT, end_date TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, medication_name, start_date));
CREATE TABLE IF NOT EXISTS immunizations (id INTEGER PRIMARY KEY, patient_id INTEGER, vaccine_name TEXT, date_administered TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, vaccine_name, date_administered));
CREATE TABLE IF NOT EXISTS vitals (id INTEGER PRIMARY KEY, patient_id INTEGER, vital_sign TEXT, value TEXT, unit TEXT, effective_date TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, vital_sign, effective_date));
CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY, patient_id INTEGER, test_name TEXT, value TEXT, unit TEXT, reference_range TEXT, interpretation TEXT, effective_date TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, test_name, effective_date));
CREATE TABLE IF NOT EXISTS procedures (id INTEGER PRIMARY KEY, patient_id INTEGER, procedure_name TEXT, date TEXT, provider TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, procedure_name, date));
"""

if __name__ == "__main__":
    app = MyChartImporterGUI()
    app.mainloop()
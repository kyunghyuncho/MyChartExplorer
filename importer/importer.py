#!/usr/bin/env python3
import argparse
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime

# --- Configuration ---
NS = {'cda': 'urn:hl7-org:v3', 'sdtc': 'urn:hl7-org:sdtc'}

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
CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, patient_id INTEGER, note_type TEXT, note_date TEXT, note_title TEXT, note_content TEXT, provider TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id), UNIQUE(patient_id, note_date, note_title));
"""

class DataImporter:
    """
    Handles the core logic of parsing XML files and inserting data into the SQLite DB.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def setup_database(self):
        """Connects to the DB and creates tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self.cursor.executescript(SCHEMA)
            self.conn.commit()
            logging.info("Database connection established and schema verified.")
        except sqlite3.Error as e:
            logging.error(f"Database setup failed: {e}")
            raise

    def process_xml_file(self, xml_file):
        """Main processing function for a single XML file."""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            patient_id = self._ingest_patient(root)
            if patient_id is None:
                logging.error(f"Could not find/create patient in {os.path.basename(xml_file)}. Skipping.")
                return
            
            # This dictionary maps a section name to its ingestion function and the templateId that identifies it.
            section_ingestors = {
                "Allergies": (self._ingest_allergies, '2.16.840.1.113883.10.20.22.2.6.1'),
                "Problems": (self._ingest_problems, '2.16.840.1.113883.10.20.22.2.5.1'),
                "Medications": (self._ingest_medications, '2.16.840.1.113883.10.20.22.2.1.1'),
                "Immunizations": (self._ingest_immunizations, '2.16.840.1.113883.10.20.22.2.2.1'),
                "Vitals": (self._ingest_vitals, '2.16.840.1.113883.10.20.22.2.4.1'),
                "Results": (self._ingest_results, '2.16.840.1.113883.10.20.22.2.3.1'),
                "Procedures": (self._ingest_procedures, '2.16.840.1.113883.10.20.22.2.7.1'),
                "Clinical Notes": (self._ingest_notes, '1.3.6.1.4.1.19376.1.5.3.1.3.4'),
            }
            
            # First, find all sections in the document
            all_sections = root.findall('.//cda:section', NS)

            for name, (func, template_id) in section_ingestors.items():
                # Manually filter sections to avoid unsupported XPath predicates
                relevant_sections = []
                for section in all_sections:
                    if section.find(f".//cda:templateId[@root='{template_id}']", NS) is not None:
                        relevant_sections.append(section)

                if not relevant_sections:
                    continue
                
                total_count = sum(func(root, section, patient_id) for section in relevant_sections)
                
                if total_count > 0:
                    logging.info(f"  > Found {total_count} new record(s) in {name}.")
            
            self.conn.commit()

        except ET.ParseError as e:
            logging.error(f"Error parsing XML file {os.path.basename(xml_file)}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred with {os.path.basename(xml_file)}: {e}", exc_info=True)

    def _find_text(self, element, path):
        if element is None: return None
        el = element.find(path, NS)
        return el.text if el is not None else None

    def _find_attrib(self, element, path, attribute):
        if element is None: return None
        el = element.find(path, NS)
        return el.get(attribute) if el is not None else None

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
            if entry.find('.//cda:observation[@negationInd="true"]', NS) is not None: continue
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
            value, unit = (None, None)
            if value_el is not None:
                value = value_el.get('value') or value_el.get('displayName') or value_el.text
                unit = value_el.get('unit')
            self.cursor.execute("INSERT OR IGNORE INTO results (patient_id, test_name, value, unit, reference_range, interpretation, effective_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (patient_id, test_name, value, unit, self._find_text(comp, './/cda:referenceRange/cda:observationRange/cda:text'),
                 self._find_attrib(comp, 'cda:interpretationCode', 'displayName'), self._find_attrib(comp, 'cda:effectiveTime', 'value')))
            count += self.cursor.rowcount
        count += self._ingest_notes(root, section, patient_id)
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
        
    def _ingest_notes(self, root, section, patient_id):
        count = 0
        text_el = section.find('cda:text', NS)
        if text_el is None: return 0
            
        note_content = "\n".join(line.strip() for line in text_el.itertext() if line.strip())
        if not note_content: return 0

        title_el = section.find('cda:title', NS)
        note_title = title_el.text.strip() if title_el is not None and title_el.text else "Clinical Note"
        
        note_type = self._find_attrib(section, 'cda:code', 'displayName') or 'Note'
        
        encounter_time_el = root.find('.//cda:encompassingEncounter/cda:effectiveTime/cda:low', NS)
        note_date = encounter_time_el.get('value') if encounter_time_el is not None else root.find('cda:effectiveTime', NS).get('value')

        provider_el = root.find('.//cda:encompassingEncounter//cda:assignedPerson/cda:name', NS)
        provider = ''.join(provider_el.itertext()).strip() if provider_el is not None else None

        self.cursor.execute("""
            INSERT OR IGNORE INTO notes (patient_id, note_type, note_date, note_title, note_content, provider)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (patient_id, note_type, note_date, note_title, note_content, provider))
        
        count += self.cursor.rowcount
        return count

def main():
    """Sets up the command-line interface, parses arguments, and runs the importer."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    
    parser = argparse.ArgumentParser(
        description="Parse Epic MyChart XML medical records and import them into a SQLite database.",
        epilog="Example: python importer_cli.py my_health.db path/to/records/*.xml"
    )
    parser.add_argument("db_file", help="Path to the SQLite database file to be created or updated.")
    parser.add_argument("xml_files", nargs='+', help="One or more paths to XML medical record files.")
    args = parser.parse_args()

    importer = DataImporter(args.db_file)
    importer.setup_database()

    for xml_file in args.xml_files:
        if os.path.exists(xml_file):
            logging.info(f"Processing file: {os.path.basename(xml_file)}")
            importer.process_xml_file(xml_file)
        else:
            logging.warning(f"File not found, skipping: {xml_file}")
    
    logging.info("Import process completed successfully!")

if __name__ == "__main__":
    main()
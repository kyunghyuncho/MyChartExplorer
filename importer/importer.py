import xml.etree.ElementTree as ET
import sqlite3
import argparse
import os
import logging

# --- Configuration ---
# Set up logging to see the script's progress and any potential issues.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the XML namespaces used in the MyChart CDA documents.
# This is crucial for correctly finding elements with ET.findall().
NS = {
    'cda': 'urn:hl7-org:v3',
    'sdtc': 'urn:hl7-org:sdtc'
}

# --- Database Schema ---
SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mrn TEXT,
    full_name TEXT,
    dob TEXT,
    gender TEXT,
    marital_status TEXT,
    race TEXT,
    ethnicity TEXT,
    deceased BOOLEAN,
    deceased_date TEXT,
    UNIQUE(mrn, full_name, dob)
);

CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    use TEXT,
    street TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    country TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, use, street, city, state, zip, country)
);

CREATE TABLE IF NOT EXISTS telecoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    use TEXT,
    value TEXT,
    type TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, use, value)
);

CREATE TABLE IF NOT EXISTS allergies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    substance TEXT,
    reaction TEXT,
    status TEXT,
    effective_date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, substance, effective_date)
);

CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    problem_name TEXT,
    status TEXT,
    onset_date TEXT,
    resolved_date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, problem_name, onset_date)
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    medication_name TEXT,
    instructions TEXT,
    status TEXT,
    start_date TEXT,
    end_date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, medication_name, start_date)
);

CREATE TABLE IF NOT EXISTS immunizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    vaccine_name TEXT,
    date_administered TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, vaccine_name, date_administered)
);

CREATE TABLE IF NOT EXISTS vitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    vital_sign TEXT,
    value TEXT,
    unit TEXT,
    effective_date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, vital_sign, effective_date)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    test_name TEXT,
    value TEXT,
    unit TEXT,
    reference_range TEXT,
    interpretation TEXT,
    effective_date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, test_name, effective_date)
);

CREATE TABLE IF NOT EXISTS procedures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    procedure_name TEXT,
    date TEXT,
    provider TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id),
    UNIQUE(patient_id, procedure_name, date)
);
"""

# --- Helper Functions ---
def find_text(element, path):
    """Safely find text in an element, returning None if not found."""
    if element is None: return None
    el = element.find(path, NS)
    return el.text if el is not None else None

def find_attrib(element, path, attribute):
    """Safely find an attribute in an element, returning None if not found."""
    if element is None: return None
    el = element.find(path, NS)
    return el.get(attribute) if el is not None else None

def get_section(root, template_id):
    """
    Find a specific section in the document by its templateId.
    This is implemented by iterating through sections because the standard
    xml.etree.ElementTree library does not support complex XPath predicates.
    """
    for section in root.findall('.//cda:section', NS):
        template_id_el = section.find(f"cda:templateId[@root='{template_id}']", NS)
        if template_id_el is not None:
            return section
    return None

def find_name_with_fallback(root, element, path_to_code_el):
    """
    Tries to find a descriptive name with multiple fallback strategies.
    1. Looks for a 'displayName' attribute.
    2. Looks for a direct 'originalText' child element.
    3. Looks for an 'originalText/reference' and resolves the ID in the document.
    """
    if element is None:
        return None
    
    code_el = element.find(path_to_code_el, NS)
    if code_el is None:
        return None
        
    # Primary method: displayName attribute
    name = code_el.get('displayName')
    if name:
        return name
        
    # Fallback method 1: Direct originalText element
    original_text_el = code_el.find('cda:originalText', NS)
    if original_text_el is not None and original_text_el.text:
        return original_text_el.text

    # Fallback method 2: Reference to another element
    if original_text_el is not None:
        reference_el = original_text_el.find('cda:reference', NS)
        if reference_el is not None:
            ref_id = reference_el.get('value')
            if ref_id and ref_id.startswith('#'):
                # Find the element with the matching ID anywhere in the document
                # Note: The sample XML uses uppercase 'ID'
                referenced_el = root.find(f".//*[@ID='{ref_id[1:]}']", NS)
                if referenced_el is not None:
                    # Get all text within the element, including children
                    return ''.join(referenced_el.itertext()).strip()

    return None

# --- Data Parsing and Ingestion Functions ---

def ingest_patient(cursor, root):
    """Parses patient demographic data, inserts it if it doesn't exist, and returns the patient's ID."""
    patient_role = root.find('.//cda:recordTarget/cda:patientRole', NS)
    if patient_role is None:
        logging.warning("No patientRole found in the document.")
        return None

    patient_el = patient_role.find('cda:patient', NS)
    
    given_name = find_text(patient_el, "cda:name/cda:given") or ""
    family_name = find_text(patient_el, "cda:name/cda:family") or ""
    full_name = f"{given_name} {family_name}".strip()

    dob = find_attrib(patient_el, 'cda:birthTime', 'value')
    gender = find_attrib(patient_el, 'cda:administrativeGenderCode', 'displayName')
    marital_status = find_attrib(patient_el, 'cda:maritalStatusCode', 'displayName')
    race = find_attrib(patient_el, 'cda:raceCode', 'displayName')
    ethnicity = find_attrib(patient_el, 'cda:ethnicGroupCode', 'displayName')
    mrn = find_attrib(patient_role, "cda:id", "extension")
    
    deceased_ind = find_attrib(patient_el, 'sdtc:deceasedInd', 'value') == 'true'
    deceased_date = find_attrib(patient_el, 'sdtc:deceasedTime', 'value') if deceased_ind else None

    cursor.execute("""
        INSERT OR IGNORE INTO patients (mrn, full_name, dob, gender, marital_status, race, ethnicity, deceased, deceased_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (mrn, full_name, dob, gender, marital_status, race, ethnicity, deceased_ind, deceased_date))
    
    cursor.execute("SELECT id FROM patients WHERE mrn=? AND full_name=? AND dob=?", (mrn, full_name, dob))
    result = cursor.fetchone()
    if result is None:
        logging.error("Failed to insert or find patient. This should not happen.")
        return None
    patient_id = result[0]
    logging.info(f"Using patient '{full_name}' with ID {patient_id}.")

    for addr in patient_role.findall('cda:addr', NS):
        cursor.execute("""
            INSERT OR IGNORE INTO addresses (patient_id, use, street, city, state, zip, country)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_id, addr.get('use'), find_text(addr, 'cda:streetAddressLine'),
            find_text(addr, 'cda:city'), find_text(addr, 'cda:state'),
            find_text(addr, 'cda:postalCode'), find_text(addr, 'cda:country')
        ))

    for telecom in patient_role.findall('cda:telecom', NS):
        value = telecom.get('value')
        type_ = value.split(':')[0] if value and ':' in value else 'tel'
        cursor.execute("""
            INSERT OR IGNORE INTO telecoms (patient_id, use, value, type) VALUES (?, ?, ?, ?)
        """, (patient_id, telecom.get('use'), value, type_))
        
    return patient_id

def ingest_allergies(cursor, root, patient_id):
    """Parses and inserts allergy data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.6.1')
    if section is None: return
    
    count = 0
    for entry in section.findall('.//cda:entry', NS):
        observation = entry.find('.//cda:observation', NS)
        # UPDATED: Skip entries that explicitly state "no known allergies"
        if observation is not None and observation.get('negationInd') == 'true':
            logging.info("Skipping 'No Known Allergies' entry.")
            continue
            
        substance = find_name_with_fallback(root, entry, './/cda:participant/cda:participantRole/cda:playingEntity/cda:code')
        reaction = find_attrib(entry, './/cda:entryRelationship/cda:observation/cda:value', 'displayName')
        status = find_attrib(entry, './/cda:act/cda:statusCode', 'code')
        effective_date = find_attrib(entry, './/cda:effectiveTime/cda:low', 'value')
        
        cursor.execute("""
            INSERT OR IGNORE INTO allergies (patient_id, substance, reaction, status, effective_date)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, substance, reaction, status, effective_date))
        count += cursor.rowcount
    if count > 0: logging.info(f"Processed Allergies section, added {count} new records.")

def ingest_problems(cursor, root, patient_id):
    """Parses and inserts problem/diagnosis data, ignoring duplicates."""
    # This covers both Active and Resolved problems by finding all matching sections
    problem_sections = [
        get_section(root, '2.16.840.1.113883.10.20.22.2.5.1'), # Active Problems
        get_section(root, '2.16.840.1.113883.10.20.22.2.20') # Resolved Problems
    ]
    
    count = 0
    for section in problem_sections:
        if section is None: continue
        
        for entry in section.findall('.//cda:entry', NS):
            observation = entry.find('.//cda:observation', NS)
            if observation is None: continue

            problem_name = find_name_with_fallback(root, observation, 'cda:value')
            status = find_attrib(observation, './/cda:entryRelationship/cda:observation/cda:value', 'displayName')
            onset_date = find_attrib(observation, 'cda:effectiveTime/cda:low', 'value')
            resolved_date = find_attrib(observation, 'cda:effectiveTime/cda:high', 'value')

            cursor.execute("""
                INSERT OR IGNORE INTO problems (patient_id, problem_name, status, onset_date, resolved_date)
                VALUES (?, ?, ?, ?, ?)
            """, (patient_id, problem_name, status, onset_date, resolved_date))
            count += cursor.rowcount
    if count > 0: logging.info(f"Processed Problems sections, added {count} new records.")

def ingest_medications(cursor, root, patient_id):
    """Parses and inserts medication data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.1.1')
    if section is None: return
    
    count = 0
    for entry in section.findall('.//cda:entry', NS):
        substance_admin = entry.find('cda:substanceAdministration', NS)
        if substance_admin is None: continue
        
        med_name = find_name_with_fallback(root, substance_admin, './/cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code')
        instructions_ref_el = substance_admin.find('cda:text/cda:reference', NS)
        if instructions_ref_el is not None: # Resolve reference for instructions
            ref_id = instructions_ref_el.get('value').replace('#', '')
            ref_el = root.find(f".//*[@ID='{ref_id}']")
            instructions = ''.join(ref_el.itertext()).strip() if ref_el is not None else None
        else: # Fallback for direct text
            instructions = find_text(substance_admin, 'cda:text')

        status = find_attrib(substance_admin, 'cda:statusCode', 'code')
        start_date = find_attrib(substance_admin, 'cda:effectiveTime/cda:low', 'value')
        end_date = find_attrib(substance_admin, 'cda:effectiveTime/cda:high', 'value')

        cursor.execute("""
            INSERT OR IGNORE INTO medications (patient_id, medication_name, instructions, status, start_date, end_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (patient_id, med_name, instructions, status, start_date, end_date))
        count += cursor.rowcount
    if count > 0: logging.info(f"Processed Medications section, added {count} new records.")

def ingest_immunizations(cursor, root, patient_id):
    """Parses and inserts immunization data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.2.1')
    if section is None: return

    count = 0
    for entry in section.findall('.//cda:entry', NS):
        substance_admin = entry.find('cda:substanceAdministration', NS)
        if substance_admin is None: continue
        
        vaccine_name = find_name_with_fallback(root, substance_admin, 'cda:consumable/cda:manufacturedProduct/cda:manufacturedMaterial/cda:code')
        date_administered = find_attrib(substance_admin, 'cda:effectiveTime', 'value')

        cursor.execute("""
            INSERT OR IGNORE INTO immunizations (patient_id, vaccine_name, date_administered)
            VALUES (?, ?, ?)
        """, (patient_id, vaccine_name, date_administered))
        count += cursor.rowcount
    if count > 0: logging.info(f"Processed Immunizations section, added {count} new records.")

def ingest_vitals(cursor, root, patient_id):
    """Parses and inserts vital signs data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.4.1')
    if section is None: return

    count = 0
    for organizer in section.findall('.//cda:organizer', NS):
        for component in organizer.findall('cda:component/cda:observation', NS):
            vital_sign = find_name_with_fallback(root, component, 'cda:code')
            value = find_attrib(component, 'cda:value', 'value')
            unit = find_attrib(component, 'cda:value', 'unit')
            effective_date = find_attrib(component, 'cda:effectiveTime', 'value')
            
            cursor.execute("""
                INSERT OR IGNORE INTO vitals (patient_id, vital_sign, value, unit, effective_date)
                VALUES (?, ?, ?, ?, ?)
            """, (patient_id, vital_sign, value, unit, effective_date))
            count += cursor.rowcount
    if count > 0: logging.info(f"Processed Vitals section, added {count} new records.")

def ingest_results(cursor, root, patient_id):
    """Parses and inserts lab result data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.3.1')
    if section is None: return

    count = 0
    for organizer in section.findall('.//cda:organizer', NS):
        for component in organizer.findall('cda:component/cda:observation', NS):
            test_name = find_name_with_fallback(root, component, 'cda:code')
            
            # UPDATED: Skip this entry if no valid test name is found
            if not test_name:
                continue

            value_el = component.find('cda:value', NS)
            value, unit = None, None
            if value_el is not None:
                value = value_el.get('value')
                if value is None: value = value_el.get('displayName', find_text(value_el, '.'))
                unit = value_el.get('unit')

            ref_range = find_text(component, './/cda:referenceRange/cda:observationRange/cda:text')
            interpretation = find_attrib(component, 'cda:interpretationCode', 'displayName')
            effective_date = find_attrib(component, 'cda:effectiveTime', 'value')

            cursor.execute("""
                INSERT OR IGNORE INTO results (patient_id, test_name, value, unit, reference_range, interpretation, effective_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, test_name, value, unit, ref_range, interpretation, effective_date))
            count += cursor.rowcount
    if count > 0: logging.info(f"Processed Results section, added {count} new records.")

def ingest_procedures(cursor, root, patient_id):
    """Parses and inserts procedure data, ignoring duplicates."""
    section = get_section(root, '2.16.840.1.113883.10.20.22.2.7.1')
    if section is None: return

    count = 0
    for entry in section.findall('.//cda:entry/cda:procedure', NS):
        procedure_name = find_name_with_fallback(root, entry, 'cda:code')
        if not procedure_name: # Fallback for devices/implants
            procedure_name = find_name_with_fallback(root, entry, './/cda:participant/cda:participantRole/cda:playingDevice/cda:code')

        date = find_attrib(entry, 'cda:effectiveTime/cda:low', 'value') or find_attrib(entry, 'cda:effectiveTime', 'value')
        provider = find_text(entry, './/cda:performer/cda:assignedEntity/cda:assignedPerson/cda:name')

        cursor.execute("""
            INSERT OR IGNORE INTO procedures (patient_id, procedure_name, date, provider)
            VALUES (?, ?, ?, ?)
        """, (patient_id, procedure_name, date, provider))
        count += cursor.rowcount
    if count > 0: logging.info(f"Processed Procedures section, added {count} new records.")


def process_xml_file(db_cursor, xml_file):
    """Main processing function for a single XML file."""
    try:
        logging.info(f"Processing file: {xml_file}")
        tree = ET.parse(xml_file)
        root = tree.getroot()

        patient_id = ingest_patient(db_cursor, root)
        if patient_id is None:
            logging.error(f"Could not find or create a patient record for {xml_file}. Skipping file.")
            return

        ingest_allergies(db_cursor, root, patient_id)
        ingest_problems(db_cursor, root, patient_id)
        ingest_medications(db_cursor, root, patient_id)
        ingest_immunizations(db_cursor, root, patient_id)
        ingest_vitals(db_cursor, root, patient_id)
        ingest_results(db_cursor, root, patient_id)
        ingest_procedures(db_cursor, root, patient_id)

    except ET.ParseError as e:
        logging.error(f"Error parsing XML file {xml_file}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing {xml_file}: {e}", exc_info=True)

# --- Main Execution ---
def main():
    """Sets up the command-line interface, database, and starts the processing."""
    parser = argparse.ArgumentParser(
        description="Parse Epic MyChart XML medical records and import them into a SQLite database.",
        epilog="Example: python import_mychart.py my_health.db records/*.xml"
    )
    parser.add_argument("db_file", help="Path to the SQLite database file to be created or updated.")
    parser.add_argument("xml_files", nargs='+', help="One or more paths to XML medical record files.")
    args = parser.parse_args()

    try:
        conn = sqlite3.connect(args.db_file)
        cursor = conn.cursor()
        cursor.executescript(SCHEMA)
        logging.info(f"Database '{args.db_file}' connected and schema verified.")
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return

    for xml_file in args.xml_files:
        if os.path.exists(xml_file):
            process_xml_file(cursor, xml_file)
        else:
            logging.warning(f"File not found: {xml_file}")

    conn.commit()
    conn.close()
    logging.info("Processing complete. Database has been updated.")

if __name__ == "__main__":
    main()
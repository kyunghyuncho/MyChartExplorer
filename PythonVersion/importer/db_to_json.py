#!/usr/bin/env python3
import sqlite3
import json
import argparse
import os
import logging

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def export_to_json(db_path, json_path):
    """Exports the entire database content to a single JSON file."""
    if not os.path.exists(db_path):
        logging.error(f"Database file not found at '{db_path}'.")
        return

    logging.info(f"Exporting data from '{db_path}' to '{json_path}'...")
    
    try:
        conn = sqlite3.connect(db_path)
        # Use the Row factory to get dictionary-like results
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch the first patient (assuming one patient per DB for this export structure)
        cursor.execute("SELECT * FROM patients LIMIT 1")
        patient_record = cursor.fetchone()

        if not patient_record:
            logging.warning("No patient found in the database. JSON file will be empty.")
            data = {}
        else:
            # Convert the patient record to a standard dictionary
            data = dict(patient_record)
            # Explicitly add the 'patient_id' key, which the viewer expects.
            data['patient_id'] = patient_record['id'] 
            
            # Fetch all related data for this patient
            # UPDATED: Added the 'notes' table to the list of tables to export.
            tables = [
                "addresses", "telecoms", "allergies", "problems", 
                "medications", "immunizations", "vitals", "results", 
                "procedures", "notes"
            ]
            for table in tables:
                try:
                    cursor.execute(f"SELECT * FROM {table} WHERE patient_id = ?", (data['patient_id'],))
                    records = cursor.fetchall()
                    # Convert each row object to a standard dictionary
                    data[table] = [dict(row) for row in records]
                    logging.info(f"Exported {len(records)} records from '{table}'.")
                except sqlite3.OperationalError:
                    logging.warning(f"Table '{table}' not found in the database. Skipping.")
                    data[table] = []


        # Write the collected data to the JSON file
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        logging.info(f"Successfully exported data to '{json_path}'.")
        conn.close()

    except sqlite3.Error as e:
        logging.error(f"Database error during JSON export: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during JSON export: {e}", exc_info=True)

# --- Main Execution ---
def main():
    """Sets up the command-line interface for the exporter."""
    parser = argparse.ArgumentParser(
        description="Export a MyChart SQLite database to a JSON file.",
        epilog="Example: python export_to_json.py my_health.db my_health.json"
    )
    parser.add_argument("db_file", help="Path to the source SQLite database file.")
    parser.add_argument("json_file", help="Path for the destination JSON file.")
    args = parser.parse_args()

    export_to_json(args.db_file, args.json_file)

if __name__ == "__main__":
    main()
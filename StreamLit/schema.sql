-- MyChart Explorer SQLite Schema
-- Generated from SQLAlchemy models in modules/database.py

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY,
  mrn TEXT,
  full_name TEXT,
  dob TEXT,
  gender TEXT,
  marital_status TEXT,
  race TEXT,
  ethnicity TEXT,
  deceased INTEGER,
  deceased_date TEXT,
  UNIQUE (mrn, full_name, dob)
);

CREATE TABLE IF NOT EXISTS allergies (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  substance TEXT,
  reaction TEXT,
  status TEXT,
  effective_date TEXT,
  UNIQUE (patient_id, substance, effective_date)
);

CREATE TABLE IF NOT EXISTS problems (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  problem_name TEXT,
  status TEXT,
  onset_date TEXT,
  resolved_date TEXT,
  UNIQUE (patient_id, problem_name, onset_date)
);

CREATE TABLE IF NOT EXISTS medications (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  medication_name TEXT,
  instructions TEXT,
  status TEXT,
  start_date TEXT,
  end_date TEXT,
  UNIQUE (patient_id, medication_name, start_date)
);

CREATE TABLE IF NOT EXISTS immunizations (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  vaccine_name TEXT,
  date_administered TEXT,
  UNIQUE (patient_id, vaccine_name, date_administered)
);

CREATE TABLE IF NOT EXISTS vitals (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  vital_sign TEXT,
  value TEXT,
  unit TEXT,
  effective_date TEXT,
  UNIQUE (patient_id, vital_sign, effective_date)
);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  test_name TEXT,
  value TEXT,
  unit TEXT,
  reference_range TEXT,
  interpretation TEXT,
  effective_date TEXT,
  UNIQUE (patient_id, test_name, effective_date)
);

CREATE TABLE IF NOT EXISTS procedures (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  procedure_name TEXT,
  date TEXT,
  provider TEXT,
  UNIQUE (patient_id, procedure_name, date)
);

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER REFERENCES patients(id),
  note_type TEXT,
  note_date TEXT,
  note_title TEXT,
  note_content TEXT,
  provider TEXT,
  UNIQUE (patient_id, note_date, note_title)
);

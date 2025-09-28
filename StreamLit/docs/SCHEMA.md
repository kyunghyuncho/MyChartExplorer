# Database Schema

This document describes the SQLite schema used by MyChart Explorer. It mirrors the SQLAlchemy models in `modules/database.py` and the DDL in `schema.sql`.

- All tables include an integer primary key `id`.
- Foreign keys reference `patients(id)`.
- Unique constraints prevent duplicate rows per patient.

## patients
Columns:
- id INTEGER PRIMARY KEY
- mrn TEXT
- full_name TEXT
- dob TEXT
- gender TEXT
- marital_status TEXT
- race TEXT
- ethnicity TEXT
- deceased INTEGER (0/1)
- deceased_date TEXT

Unique:
- (mrn, full_name, dob)

## allergies
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- substance TEXT
- reaction TEXT
- status TEXT
- effective_date TEXT

Unique:
- (patient_id, substance, effective_date)

## problems
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- problem_name TEXT
- status TEXT
- onset_date TEXT
- resolved_date TEXT

Unique:
- (patient_id, problem_name, onset_date)

## medications
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- medication_name TEXT
- instructions TEXT
- status TEXT
- start_date TEXT
- end_date TEXT

Unique:
- (patient_id, medication_name, start_date)

## immunizations
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- vaccine_name TEXT
- date_administered TEXT

Unique:
- (patient_id, vaccine_name, date_administered)

## vitals
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- vital_sign TEXT
- value TEXT
- unit TEXT
- effective_date TEXT

Unique:
- (patient_id, vital_sign, effective_date)

## results
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- test_name TEXT
- value TEXT
- unit TEXT
- reference_range TEXT
- interpretation TEXT
- effective_date TEXT

Unique:
- (patient_id, test_name, effective_date)

## procedures
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- procedure_name TEXT
- date TEXT
- provider TEXT

Unique:
- (patient_id, procedure_name, date)

## notes
- id INTEGER PRIMARY KEY
- patient_id INTEGER REFERENCES patients(id)
- note_type TEXT
- note_date TEXT
- note_title TEXT
- note_content TEXT
- provider TEXT

Unique:
- (patient_id, note_date, note_title)

---

See `../schema.sql` for the exact DDL.

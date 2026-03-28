import os
from sqlalchemy import (create_engine, Column, Integer, String, Boolean, Text,
                        ForeignKey, UniqueConstraint)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.engine import Engine
from sqlalchemy import event

# Define the base class for declarative models
Base = declarative_base()

class Patient(Base):
    __tablename__ = 'patients'
    id = Column(Integer, primary_key=True)
    mrn = Column(String)
    full_name = Column(String)
    dob = Column(String)
    gender = Column(String)
    marital_status = Column(String)
    race = Column(String)
    ethnicity = Column(String)
    deceased = Column(Boolean)
    deceased_date = Column(String)

    __table_args__ = (UniqueConstraint('mrn', 'full_name', 'dob'),)

    allergies = relationship("Allergy", back_populates="patient")
    problems = relationship("Problem", back_populates="patient")
    medications = relationship("Medication", back_populates="patient")
    immunizations = relationship("Immunization", back_populates="patient")
    vitals = relationship("Vital", back_populates="patient")
    results = relationship("Result", back_populates="patient")
    procedures = relationship("Procedure", back_populates="patient")
    notes = relationship("Note", back_populates="patient")


class Allergy(Base):
    __tablename__ = 'allergies'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    substance = Column(String)
    reaction = Column(String)
    status = Column(String)
    effective_date = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'substance', 'effective_date'),)
    patient = relationship("Patient", back_populates="allergies")


class Problem(Base):
    __tablename__ = 'problems'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    problem_name = Column(String)
    status = Column(String)
    onset_date = Column(String)
    resolved_date = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'problem_name', 'onset_date'),)
    patient = relationship("Patient", back_populates="problems")


class Medication(Base):
    __tablename__ = 'medications'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    medication_name = Column(String)
    instructions = Column(Text)
    status = Column(String)
    start_date = Column(String)
    end_date = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'medication_name', 'start_date'),)
    patient = relationship("Patient", back_populates="medications")


class Immunization(Base):
    __tablename__ = 'immunizations'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    vaccine_name = Column(String)
    date_administered = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'vaccine_name', 'date_administered'),)
    patient = relationship("Patient", back_populates="immunizations")


class Vital(Base):
    __tablename__ = 'vitals'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    vital_sign = Column(String)
    value = Column(String)
    unit = Column(String)
    effective_date = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'vital_sign', 'effective_date'),)
    patient = relationship("Patient", back_populates="vitals")


class Result(Base):
    __tablename__ = 'results'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    test_name = Column(String)
    value = Column(String)
    unit = Column(String)
    reference_range = Column(String)
    interpretation = Column(String)
    effective_date = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'test_name', 'effective_date'),)
    patient = relationship("Patient", back_populates="results")


class Procedure(Base):
    __tablename__ = 'procedures'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    procedure_name = Column(String)
    date = Column(String)
    provider = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'procedure_name', 'date'),)
    patient = relationship("Patient", back_populates="procedures")


class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'))
    note_type = Column(String)
    note_date = Column(String)
    note_title = Column(String)
    note_content = Column(Text)
    provider = Column(String)

    __table_args__ = (UniqueConstraint('patient_id', 'note_date', 'note_title'),)
    patient = relationship("Patient", back_populates="notes")


def get_db_engine(db_path: str, key: str | None = None) -> Engine:
    """
    Creates a SQLAlchemy engine for the given database path.
    If the directory for the db_path doesn't exist, it will be created.
    """
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    engine = create_engine(f'sqlite:///{db_path}')
    if key:
        # Attempt to enable SQLCipher; requires sqlite built with SQLCipher
        @event.listens_for(engine, "connect")
        def set_sqlcipher(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                # Escape single quotes in key to avoid breaking the PRAGMA literal
                safe_key = str(key).replace("'", "''")
                cursor.execute(f"PRAGMA key='{safe_key}';")
            except Exception:
                pass
            finally:
                cursor.close()
    return engine

def setup_database(engine: Engine):
    """
    Creates all tables in the database.
    """
    Base.metadata.create_all(engine)

def get_session(engine: Engine):
    """
    Creates a new SQLAlchemy session.
    """
    Session = sessionmaker(bind=engine)
    return Session()

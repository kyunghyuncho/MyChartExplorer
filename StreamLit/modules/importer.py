import logging
import os
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .database import (
    Patient, Allergy, Problem, Medication, Immunization, Vital, Result, Procedure, Note, get_session
)

class DataImporter:
    """
    Handles the core logic of parsing XML files and inserting data into the database using SQLAlchemy.
    """
    def __init__(self, db_engine):
        # Store engine; create a fresh session per file import
        self.engine = db_engine
        self.session = None

    def process_xml_file(self, xml_file: str):
        """Main processing function for a single XML file."""
        try:
            # Create a fresh session per file, so multiple files import cleanly
            self.session = get_session(self.engine)
            with open(xml_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'lxml-xml')

            patient = self._ingest_patient(soup)
            if patient is None:
                logging.error(f"Could not find/create patient in {os.path.basename(xml_file)}. Skipping.")
                return

            section_ingestors = {
                "Allergies": ("2.16.840.1.113883.10.20.22.2.6.1", self._ingest_allergies),
                "Problems": ("2.16.840.1.113883.10.20.22.2.5.1", self._ingest_problems),
                "Medications": ("2.16.840.1.113883.10.20.22.2.1.1", self._ingest_medications),
                "Immunizations": ("2.16.840.1.113883.10.20.22.2.2.1", self._ingest_immunizations),
                "Vitals": ("2.16.840.1.113883.10.20.22.2.4.1", self._ingest_vitals),
                "Results": ("2.16.840.1.113883.10.20.22.2.3.1", self._ingest_results),
                "Procedures": ("2.16.840.1.113883.10.20.22.2.7.1", self._ingest_procedures),
                "Clinical Notes": ("1.3.6.1.4.1.19376.1.5.3.1.3.4", self._ingest_notes),
            }

            for name, (template_id, func) in section_ingestors.items():
                sections = soup.select(f'section:has(templateId[root="{template_id}"])')
                if not sections:
                    continue
                
                total_count = sum(func(soup, section, patient) for section in sections)
                if total_count > 0:
                    logging.info(f"  > Found {total_count} new record(s) in {name}.")
            
            self.session.commit()

        except Exception as e:
            logging.error(f"An unexpected error occurred with {os.path.basename(xml_file)}: {e}", exc_info=True)
            if self.session is not None:
                self.session.rollback()
        finally:
            if self.session is not None:
                self.session.close()
                self.session = None

    def _find_text(self, element, tag_name):
        """Find text using a CSS selector or simple tag name; supports nested paths."""
        if element is None:
            return None
        if tag_name is None:
            return element.get_text(strip=True)
        el = None
        try:
            el = element.select_one(tag_name)
        except Exception:
            el = None
        if el is None:
            el = element.find(tag_name)
        return el.get_text(strip=True) if el and el.get_text() else None

    def _find_attrib(self, element, tag_name, attribute):
        """Find attribute using a CSS selector or simple tag name; supports nested paths."""
        if element is None:
            return None
        el = None
        try:
            el = element.select_one(tag_name)
        except Exception:
            el = None
        if el is None:
            el = element.find(tag_name)
        return el.get(attribute) if el else None

    def _find_name_with_fallback(self, soup, element, code_selector):
        """Resolve human-readable name for a coded element.
        Preference: displayName -> originalText text -> originalText reference (#ID) by ID/id.
        """
        if element is None:
            return None
        code_el = None
        try:
            code_el = element.select_one(code_selector)
        except Exception:
            code_el = element.find(code_selector)
        if code_el is None:
            return None

        # 1) Prefer displayName
        name = code_el.get('displayName')
        if name:
            return name

        # 2) originalText content or referenced content
        original_text_el = code_el.find('originalText')
        if original_text_el is not None:
            # direct text
            direct = original_text_el.get_text(strip=True)
            if direct:
                return direct
            # referenced by ID
            reference_el = original_text_el.find('reference')
            if reference_el is not None:
                ref_val = reference_el.get('value') or reference_el.get('VALUE')
                if ref_val and ref_val.startswith('#'):
                    ref_id = ref_val[1:]
                    # Some CDA docs use upper-case ID attribute
                    referenced_el = soup.find(attrs={"ID": ref_id}) or soup.find(id=ref_id)
                    if referenced_el is not None:
                        return referenced_el.get_text(strip=True)
        return None

    def _ingest_patient(self, soup):
        patient_role = soup.select_one('recordTarget > patientRole')
        if not patient_role: return None
        
        patient_el = patient_role.find('patient')
        given_name = self._find_text(patient_el, "given") or ""
        family_name = self._find_text(patient_el, "family") or ""
        full_name = f"{given_name} {family_name}".strip()
        dob = self._find_attrib(patient_el, 'birthTime', 'value')
        mrn = self._find_attrib(patient_role, "id", "extension")

        patient = self.session.query(Patient).filter_by(mrn=mrn, full_name=full_name, dob=dob).first()
        if patient:
            return patient
        
        new_patient = Patient(
            mrn=mrn, full_name=full_name, dob=dob,
            gender=self._find_attrib(patient_el, 'administrativeGenderCode', 'displayName'),
            marital_status=self._find_attrib(patient_el, 'maritalStatusCode', 'displayName'),
            race=self._find_attrib(patient_el, 'raceCode', 'displayName'),
            ethnicity=self._find_attrib(patient_el, 'ethnicGroupCode', 'displayName'),
            deceased=self._find_attrib(patient_el, 'sdtc:deceasedInd', 'value') == 'true',
            deceased_date=self._find_attrib(patient_el, 'sdtc:deceasedTime', 'value')
        )
        self.session.add(new_patient)
        self.session.flush() # Use flush to get the ID before commit
        return new_patient

    def _ingest_allergies(self, soup, section, patient):
        count = 0
        # Include nested entries to match PythonVersion behavior
        for entry in section.select('entry'):
            if entry.select_one('observation[negationInd="true"]'):
                continue
            substance = self._find_name_with_fallback(
                soup,
                entry,
                'participant[typeCode="CSM"] > participantRole > playingEntity > code',
            )
            effective_date = self._find_attrib(entry, 'effectiveTime low', 'value')

            if not self.session.query(Allergy).filter_by(
                patient_id=patient.id, substance=substance, effective_date=effective_date
            ).first():
                new_allergy = Allergy(
                    patient_id=patient.id,
                    substance=substance,
                    reaction=self._find_attrib(entry, 'observation value', 'displayName'),
                    status=self._find_attrib(entry, 'act > statusCode', 'code') or self._find_attrib(entry, 'statusCode', 'code'),
                    effective_date=effective_date,
                )
                self.session.add(new_allergy)
                count += 1
        return count

    def _ingest_problems(self, soup, section, patient):
        count = 0
        for entry in section.select('entry'):
            obs = entry.select_one('observation')
            if not obs:
                continue
            problem_name = self._find_name_with_fallback(soup, obs, 'value')
            onset_date = self._find_attrib(obs, 'effectiveTime low', 'value')

            if not self.session.query(Problem).filter_by(
                patient_id=patient.id, problem_name=problem_name, onset_date=onset_date
            ).first():
                new_problem = Problem(
                    patient_id=patient.id,
                    problem_name=problem_name,
                    onset_date=onset_date,
                    status=self._find_attrib(obs, 'entryRelationship observation value', 'displayName'),
                    resolved_date=self._find_attrib(obs, 'effectiveTime high', 'value'),
                )
                self.session.add(new_problem)
                count += 1
        return count

    def _ingest_medications(self, soup, section, patient):
        count = 0
        for entry in section.select('entry > substanceAdministration'):
            med_name = self._find_name_with_fallback(
                soup, entry, 'consumable > manufacturedProduct > manufacturedMaterial > code'
            )
            start_date = self._find_attrib(entry, 'effectiveTime low', 'value')

            # Instructions: prefer narrative text, resolving references when present
            instructions = None
            text_el = entry.select_one('text')
            if text_el is not None:
                # Try direct text
                instructions = text_el.get_text(strip=True)
                if not instructions:
                    ref_el = text_el.find('reference')
                    if ref_el is not None:
                        ref_val = ref_el.get('value') or ref_el.get('VALUE')
                        if ref_val and ref_val.startswith('#'):
                            ref_id = ref_val[1:]
                            ref_target = soup.find(attrs={"ID": ref_id}) or soup.find(id=ref_id)
                            if ref_target is not None:
                                instructions = ref_target.get_text(strip=True)

            if not self.session.query(Medication).filter_by(
                patient_id=patient.id, medication_name=med_name, start_date=start_date
            ).first():
                new_med = Medication(
                    patient_id=patient.id,
                    medication_name=med_name,
                    start_date=start_date,
                    instructions=instructions,
                    status=self._find_attrib(entry, 'statusCode', 'code'),
                    end_date=self._find_attrib(entry, 'effectiveTime high', 'value'),
                )
                self.session.add(new_med)
                count += 1
        return count

    def _ingest_immunizations(self, soup, section, patient):
        count = 0
        for entry in section.select('entry > substanceAdministration'):
            vaccine_name = self._find_name_with_fallback(
                soup, entry, 'consumable > manufacturedProduct > manufacturedMaterial > code'
            )
            # Some exports use a single value, others nested low/high
            date_administered = (
                self._find_attrib(entry, 'effectiveTime', 'value')
                or self._find_attrib(entry, 'effectiveTime > low', 'value')
            )

            if not self.session.query(Immunization).filter_by(
                patient_id=patient.id,
                vaccine_name=vaccine_name,
                date_administered=date_administered,
            ).first():
                new_imm = Immunization(
                    patient_id=patient.id,
                    vaccine_name=vaccine_name,
                    date_administered=date_administered,
                )
                self.session.add(new_imm)
                count += 1
        return count

    def _ingest_vitals(self, soup, section, patient):
        count = 0
        for comp in section.select('component > observation'):
            vital_sign = self._find_name_with_fallback(soup, comp, 'code')
            if not vital_sign: continue
            
            effective_date = self._find_attrib(comp, 'effectiveTime', 'value')
            if not self.session.query(Vital).filter_by(patient_id=patient.id, vital_sign=vital_sign, effective_date=effective_date).first():
                value_el = comp.find('value')
                new_vital = Vital(
                    patient_id=patient.id, vital_sign=vital_sign, effective_date=effective_date,
                    value=value_el.get('value') if value_el else None,
                    unit=value_el.get('unit') if value_el else None
                )
                self.session.add(new_vital)
                count += 1
        return count

    def _ingest_results(self, soup, section, patient):
        count = 0
        # Follow PythonVersion: iterate organizers, keep panel name
        for organizer in section.select('organizer'):
            panel_name = (
                self._find_text(organizer.find('code'), 'originalText')
                or self._find_name_with_fallback(soup, organizer, 'code')
            )
            for comp in organizer.select('observation'):
                test_name = self._find_name_with_fallback(soup, comp, 'code')
                if not test_name:
                    continue
                effective_date = self._find_attrib(comp, 'effectiveTime', 'value')
                if not self.session.query(Result).filter_by(
                    patient_id=patient.id, test_name=test_name, effective_date=effective_date
                ).first():
                    value_el = comp.find('value')
                    value, unit = (None, None)
                    if value_el:
                        value = value_el.get('value') or value_el.get('displayName') or value_el.text
                        unit = value_el.get('unit')
                    new_result = Result(
                        patient_id=patient.id,
                        test_name=f"{panel_name}: {test_name}" if panel_name else test_name,
                        effective_date=effective_date,
                        value=value,
                        unit=unit,
                        reference_range=self._find_text(comp, 'referenceRange observationRange text'),
                        interpretation=self._find_attrib(comp, 'interpretationCode', 'displayName'),
                    )
                    self.session.add(new_result)
                    count += 1
        # As in PythonVersion, also ingest any notes embedded in this section
        count += self._ingest_notes(soup, section, patient)
        return count

    def _ingest_procedures(self, soup, section, patient):
        count = 0
        for proc in section.select('entry > procedure'):
            proc_name = self._find_name_with_fallback(soup, proc, 'code') or self._find_name_with_fallback(soup, proc, 'participant[typeCode="DEV"] > participantRole > playingDevice > code')
            date = self._find_attrib(proc, 'effectiveTime low', 'value') or self._find_attrib(proc, 'effectiveTime', 'value')

            if not self.session.query(Procedure).filter_by(patient_id=patient.id, procedure_name=proc_name, date=date).first():
                new_proc = Procedure(
                    patient_id=patient.id, procedure_name=proc_name, date=date,
                    provider=self._find_text(proc, 'performer assignedEntity assignedPerson name')
                )
                self.session.add(new_proc)
                count += 1
        return count
        
    def _ingest_notes(self, soup, section, patient):
        count = 0
        text_el = section.find('text')
        if not text_el: return 0
            
        note_content = "\n".join(line.strip() for line in text_el.stripped_strings)
        if not note_content: return 0

        note_title = self._find_text(section, 'title') or "Clinical Note"
        note_date_el = soup.select_one('encompassingEncounter > effectiveTime > low') or soup.find('effectiveTime')
        note_date = note_date_el.get('value') if note_date_el else None

        if not self.session.query(Note).filter_by(patient_id=patient.id, note_date=note_date, note_title=note_title).first():
            provider_el = soup.select_one('encompassingEncounter performer assignedPerson name')
            provider = provider_el.get_text(strip=True) if provider_el else None
            
            new_note = Note(
                patient_id=patient.id,
                note_type=self._find_attrib(section, 'code', 'displayName') or 'Note',
                note_date=note_date,
                note_title=note_title,
                note_content=note_content,
                provider=provider
            )
            self.session.add(new_note)
            count += 1
        return count

"""FHIR importer: map DocumentReference (+Binary) into notes table.

Initial scope: Ingest clinical notes by reading DocumentReference resources,
resolving attachments via Binary or direct content, and inserting into the
existing SQLAlchemy `notes` table.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .database import Note, Patient, get_session


def _patient_row(session: Session) -> Optional[Patient]:
    # For now, assume singleton patient per user DB; take first row if present
    return session.query(Patient).first()


def _docref_title(doc: Dict[str, Any]) -> Optional[str]:
    # Prefer attachment.title; else description; else type.text
    contents = doc.get("content", []) or []
    for c in contents:
        att = c.get("attachment") or {}
        t = att.get("title")
        if t:
            return t
    return doc.get("description") or (doc.get("type") or {}).get("text")


def _docref_date(doc: Dict[str, Any]) -> Optional[str]:
    # Prefer attachment.creation; else DocumentReference.date; else indexed
    contents = doc.get("content", []) or []
    for c in contents:
        att = c.get("attachment") or {}
        creation = att.get("creation")
        if creation:
            return creation
    return doc.get("date") or doc.get("indexed")


def _docref_provider(doc: Dict[str, Any]) -> Optional[str]:
    custodian = (doc.get("custodian") or {}).get("display")
    author = None
    for a in doc.get("author", []) or []:
        author = a.get("display") or author
    return author or custodian


def _is_pdf_bytes(raw: bytes) -> bool:
    # PDF files typically start with %PDF
    return len(raw) >= 4 and raw[:4] == b"%PDF"


def _pdf_bytes_to_text(raw: bytes) -> Optional[str]:
    try:
        # Lazy import to avoid hard dependency during non-PDF flows
        from io import BytesIO
        from pdfminer.high_level import extract_text
        return extract_text(BytesIO(raw)) or None
    except Exception:
        return None


def _is_rtf_bytes(raw: bytes) -> bool:
    # RTF typically starts with {\rtf
    s = raw.lstrip()[:5]
    try:
        return s.decode("ascii", errors="ignore").startswith("{\\rtf")
    except Exception:
        return False


def _looks_like_html_or_xml(raw: bytes) -> bool:
    s = raw.lstrip()[:10]
    return s.startswith(b"<") or s.startswith(b"<?xml")


def _html_to_text(raw: bytes) -> Optional[str]:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "lxml")
        txt = soup.get_text("\n", strip=True)
        return txt or None
    except Exception:
        return None


def _xml_to_text(raw: bytes) -> Optional[str]:
    # Try XML parser first; fall back to HTML if needed
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "lxml-xml")
        txt = soup.get_text("\n", strip=True)
        if txt:
            return txt
    except Exception:
        pass
    return _html_to_text(raw)


def _rtf_to_text(raw: bytes) -> Optional[str]:
    try:
        from striprtf.striprtf import rtf_to_text
        return rtf_to_text(raw.decode("utf-8", errors="ignore")) or None
    except Exception:
        return None


def _bytes_to_note_text(raw: bytes, content_type: Optional[str]) -> Optional[str]:
    ct = (content_type or "").lower()
    # Content-type guided extraction
    if "pdf" in ct:
        return _pdf_bytes_to_text(raw) or None
    if "rtf" in ct:
        return _rtf_to_text(raw)
    if "html" in ct or "xhtml" in ct:
        return _html_to_text(raw)
    if ct in ("application/xml", "text/xml") or "xml" in ct:
        return _xml_to_text(raw)
    if ct.startswith("text/") or "plain" in ct:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None
    # Sniffers when ctype missing or generic
    if _is_pdf_bytes(raw):
        return _pdf_bytes_to_text(raw)
    if _is_rtf_bytes(raw):
        return _rtf_to_text(raw)
    if _looks_like_html_or_xml(raw):
        # Try XML then HTML
        return _xml_to_text(raw)
    # Last resort: try UTF-8 decode
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None

def _extract_note_text(doc: Dict[str, Any], binary_loader) -> Tuple[Optional[str], Optional[str]]:
    """Return (content_text, content_type). Supports:
    - content[].attachment.data (base64)
    - content[].attachment.url -> if starts with 'Binary/' then call binary_loader(id)
    - otherwise returns None to let caller skip
    """
    import base64
    contents = doc.get("content", []) or []
    for c in contents:
        att = c.get("attachment") or {}
        if not att:
            continue
        data_b64 = att.get("data")
        if data_b64:
            try:
                raw = base64.b64decode(data_b64)
                ctype = att.get("contentType")
                text = _bytes_to_note_text(raw, ctype)
                if text:
                    return text, ctype or "text/plain"
                # Fallbacks if extraction failed: try text then hex
                try:
                    return raw.decode("utf-8", errors="replace"), ctype
                except Exception:
                    return raw.hex(), ctype
            except Exception:
                continue
        url = att.get("url")
        if url:
            # Support Binary/{id} or absolute URLs that contain /Binary/{id} (with optional /$binary)
            bid: Optional[str] = None
            if url.startswith("Binary/"):
                bid = url.split("/", 1)[1]
            else:
                try:
                    import re
                    m = re.search(r"/Binary/([^/?#]+)", url)
                    if m:
                        bid = m.group(1)
                except Exception:
                    bid = None
            if bid:
                try:
                    data = binary_loader(bid)
                    ctype = att.get("contentType")
                    text = _bytes_to_note_text(data, ctype)
                    if text:
                        return text, ctype or "text/plain"
                    # Fallbacks if extraction failed: try text then hex
                    try:
                        return data.decode("utf-8", errors="replace"), ctype
                    except Exception:
                        return data.hex(), ctype
                except Exception:
                    # Fall through to next content if binary fetch fails
                    continue
    return None, None


def ingest_document_references(engine: Engine, docs: List[Dict[str, Any]], binary_loader) -> tuple[int, int]:
    """Insert notes from DocumentReference list.

    Returns (new_rows, skipped_no_content) for debugging/reporting.
    """
    session = get_session(engine)
    try:
        patient = _patient_row(session)
        if not patient:
            # Create a placeholder patient row if none exists yet
            patient = Patient(mrn=None, full_name=None, dob=None)
            session.add(patient)
            session.flush()
        new_count = 0
        skipped_no_content = 0
        for doc in docs:
            base_title = _docref_title(doc) or "Clinical Note"
            date = _docref_date(doc)
            provider = _docref_provider(doc)
            content_text, ctype = _extract_note_text(doc, binary_loader)
            if not content_text:
                skipped_no_content += 1
                continue
            # Primary check: (patient_id, date, title)
            title = base_title
            exists = session.query(Note).filter_by(
                patient_id=patient.id, note_date=date, note_title=title
            ).first()
            if exists:
                # Disambiguate with DocumentReference.id or content hash
                doc_id = doc.get("id")
                if isinstance(doc_id, str) and doc_id:
                    title = f"{base_title} [DR:{doc_id}]"
                else:
                    digest = hashlib.sha1(content_text.encode("utf-8", errors="replace")).hexdigest()[:8]
                    title = f"{base_title} [H:{digest}]"
                exists2 = session.query(Note).filter_by(
                    patient_id=patient.id, note_date=date, note_title=title
                ).first()
                if exists2:
                    # Consider true duplicate; skip
                    continue

            note = Note(
                patient_id=patient.id,
                note_type="FHIR DocumentReference",
                note_date=date,
                note_title=title,
                note_content=content_text,
                provider=provider,
            )

            session.add(note)
            new_count += 1
        session.commit()
        if skipped_no_content:
            try:
                import logging
                logging.info(f"Skipped {skipped_no_content} DocumentReference(s) with no accessible content.")
            except Exception:
                pass
        return new_count, skipped_no_content
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------- Additional ingesters for DB schema ---------------- #

def _code_text(d: Optional[Dict[str, Any]]) -> Optional[str]:
    if not d:
        return None
    t = d.get("text")
    if t:
        return t
    codings = (d.get("coding") or []) if isinstance(d.get("coding"), list) else d.get("coding") or []
    if isinstance(codings, list) and codings:
        c0 = codings[0] or {}
        return c0.get("display") or c0.get("code")
    return None


def upsert_patient(engine: Engine, patient_res: Optional[Dict[str, Any]]) -> Patient:
    session = get_session(engine)
    try:
        pat = _patient_row(session)
        if not pat:
            pat = Patient(mrn=None, full_name=None, dob=None)
            session.add(pat)
            session.flush()
        if patient_res:
            # Name
            name = (patient_res.get("name") or [{}])[0]
            given = " ".join(name.get("given") or []) if isinstance(name.get("given"), list) else (name.get("given") or "")
            family = name.get("family") or ""
            full_name = f"{given} {family}".strip() or pat.full_name
            # DOB, MRN
            dob = patient_res.get("birthDate") or pat.dob
            mrn = None
            for ident in patient_res.get("identifier", []) or []:
                if (ident.get("type") or {}).get("text") == "MRN" or (ident.get("system") or "").lower().find("mrn") >= 0:
                    mrn = ident.get("value")
                    break
            # Demographics
            gender = patient_res.get("gender") or pat.gender
            marital_status = _code_text(patient_res.get("maritalStatus")) or pat.marital_status
            # Race/Ethnicity (US Core extensions may be present)
            race = pat.race
            ethnicity = pat.ethnicity
            for ext in patient_res.get("extension", []) or []:
                url = ext.get("url") or ""
                if url.endswith("us-core-race"):
                    race = _code_text((ext.get("valueCodeableConcept") or {})) or race
                if url.endswith("us-core-ethnicity"):
                    ethnicity = _code_text((ext.get("valueCodeableConcept") or {})) or ethnicity
            deceased = None
            deceased_date = None
            if "deceasedBoolean" in patient_res:
                deceased = bool(patient_res.get("deceasedBoolean"))
            if patient_res.get("deceasedDateTime"):
                deceased = True
                deceased_date = patient_res.get("deceasedDateTime")

            pat.full_name = full_name
            pat.dob = dob
            pat.mrn = mrn or pat.mrn
            pat.gender = gender
            pat.marital_status = marital_status
            pat.race = race
            pat.ethnicity = ethnicity
            if deceased is not None:
                pat.deceased = deceased
            if deceased_date:
                pat.deceased_date = deceased_date
        session.commit()
        return pat
    finally:
        session.close()


def ingest_allergies(engine: Engine, items: List[Dict[str, Any]]) -> int:
    from .database import Allergy
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        new = 0
        for it in items:
            substance = _code_text(it.get("code"))
            # Choose first manifestation if present
            reaction = None
            if it.get("reaction"):
                r0 = (it.get("reaction") or [None])[0] or {}
                mans = r0.get("manifestation") or []
                if mans:
                    reaction = _code_text(mans[0]) or reaction
            status = _code_text(it.get("clinicalStatus")) or (it.get("verificationStatus") or {}).get("text")
            effective = it.get("onsetDateTime") or it.get("recordedDate")
            exists = session.query(Allergy).filter_by(patient_id=pat.id, substance=substance, effective_date=effective).first()
            if exists:
                continue
            row = Allergy(
                patient_id=pat.id,
                substance=substance,
                reaction=reaction,
                status=status,
                effective_date=effective,
            )
            session.add(row)
            new += 1
        session.commit()
        return new
    finally:
        session.close()


def ingest_conditions(engine: Engine, items: List[Dict[str, Any]]) -> int:
    from .database import Problem
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        new = 0
        for it in items:
            name = _code_text(it.get("code"))
            status = _code_text(it.get("clinicalStatus"))
            onset = it.get("onsetDateTime") or ((it.get("onsetPeriod") or {}).get("start"))
            resolved = it.get("abatementDateTime") or ((it.get("abatementPeriod") or {}).get("end"))
            exists = session.query(Problem).filter_by(patient_id=pat.id, problem_name=name, onset_date=onset).first()
            if exists:
                continue
            row = Problem(
                patient_id=pat.id,
                problem_name=name,
                status=status,
                onset_date=onset,
                resolved_date=resolved,
            )
            session.add(row)
            new += 1
        session.commit()
        return new
    finally:
        session.close()


def ingest_medications(engine: Engine, statements: List[Dict[str, Any]], requests: List[Dict[str, Any]]) -> int:
    from .database import Medication
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        new = 0

        def _med_fields(m: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
            name = _code_text(m.get("medicationCodeableConcept"))
            # Directions
            instr = None
            di = m.get("dosageInstruction") or []
            if di:
                instr = (di[0] or {}).get("text") or instr
            status = m.get("status")
            start = (m.get("effectivePeriod") or {}).get("start") or m.get("authoredOn") or m.get("dateAsserted")
            end = (m.get("effectivePeriod") or {}).get("end")
            return name, instr, status, start if start else None, end if end else None  # type: ignore

        for it in statements:
            name, instr, status, start, end = _med_fields(it)
            exists = session.query(Medication).filter_by(patient_id=pat.id, medication_name=name, start_date=start).first()
            if exists:
                continue
            row = Medication(patient_id=pat.id, medication_name=name, instructions=instr, status=status, start_date=start, end_date=end)
            session.add(row)
            new += 1

        for it in requests:
            name, instr, status, start, end = _med_fields(it)
            exists = session.query(Medication).filter_by(patient_id=pat.id, medication_name=name, start_date=start).first()
            if exists:
                continue
            row = Medication(patient_id=pat.id, medication_name=name, instructions=instr, status=status, start_date=start, end_date=end)
            session.add(row)
            new += 1

        session.commit()
        return new
    finally:
        session.close()


def ingest_immunizations(engine: Engine, items: List[Dict[str, Any]]) -> int:
    from .database import Immunization as Imm
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        new = 0
        for it in items:
            name = _code_text(it.get("vaccineCode"))
            date = it.get("occurrenceDateTime") or it.get("occurrenceString")
            exists = session.query(Imm).filter_by(patient_id=pat.id, vaccine_name=name, date_administered=date).first()
            if exists:
                continue
            row = Imm(patient_id=pat.id, vaccine_name=name, date_administered=date)
            session.add(row)
            new += 1
        session.commit()
        return new
    finally:
        session.close()


def ingest_observations(engine: Engine, items: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Return (new_vitals, new_results)."""
    from .database import Vital, Result
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        nv = 0
        nr = 0

        def _obs_category(o: Dict[str, Any]) -> List[str]:
            cats: List[str] = []
            cc = o.get("category") or []
            if isinstance(cc, dict):
                cc = [cc]
            for cat in cc:
                for c in cat.get("coding", []) or []:
                    code = (c or {}).get("code") or (c or {}).get("display")
                    if code:
                        cats.append(str(code).lower())
            return cats

        def _value(o: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
            if o.get("valueQuantity"):
                vq = o["valueQuantity"]
                return str(vq.get("value")) if vq.get("value") is not None else None, vq.get("unit")
            if o.get("valueString"):
                return o.get("valueString"), None
            if o.get("valueCodeableConcept"):
                return _code_text(o.get("valueCodeableConcept")), None
            return None, None

        for o in items:
            cats = _obs_category(o)
            code_name = _code_text(o.get("code")) or "Observation"
            eff = o.get("effectiveDateTime") or ((o.get("effectivePeriod") or {}).get("start"))
            # Components become additional results
            components = o.get("component") or []

            if "vital-signs" in cats:
                val, unit = _value(o)
                if val is not None:
                    exists = session.query(Vital).filter_by(patient_id=pat.id, vital_sign=code_name, effective_date=eff).first()
                    if not exists:
                        row = Vital(patient_id=pat.id, vital_sign=code_name, value=val, unit=unit, effective_date=eff)
                        session.add(row)
                        nv += 1
            elif "laboratory" in cats or "lab" in cats:
                val, unit = _value(o)
                if val is not None:
                    exists = session.query(Result).filter_by(patient_id=pat.id, test_name=code_name, effective_date=eff).first()
                    if not exists:
                        row = Result(
                            patient_id=pat.id,
                            test_name=code_name,
                            effective_date=eff,
                            value=val,
                            unit=unit,
                            reference_range=None,
                            interpretation=_code_text((o.get("interpretation") or [{}])[0]) if isinstance(o.get("interpretation"), list) else _code_text(o.get("interpretation")),
                        )
                        session.add(row)
                        nr += 1
                # Components as separate result rows
                for comp in components:
                    cname = _code_text(comp.get("code"))
                    cval, cunit = _value(comp)
                    if cname and cval is not None:
                        full_name = f"{code_name}: {cname}"
                        exists = session.query(Result).filter_by(patient_id=pat.id, test_name=full_name, effective_date=eff).first()
                        if not exists:
                            row = Result(patient_id=pat.id, test_name=full_name, effective_date=eff, value=cval, unit=cunit, reference_range=None, interpretation=None)
                            session.add(row)
                            nr += 1
            else:
                # Unknown category: attempt to store as results
                val, unit = _value(o)
                if val is not None:
                    exists = session.query(Result).filter_by(patient_id=pat.id, test_name=code_name, effective_date=eff).first()
                    if not exists:
                        row = Result(patient_id=pat.id, test_name=code_name, effective_date=eff, value=val, unit=unit, reference_range=None, interpretation=None)
                        session.add(row)
                        nr += 1
        session.commit()
        return nv, nr
    finally:
        session.close()


def ingest_procedures(engine: Engine, items: List[Dict[str, Any]]) -> int:
    from .database import Procedure
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        new = 0
        for it in items:
            name = _code_text(it.get("code"))
            date = it.get("performedDateTime") or ((it.get("performedPeriod") or {}).get("start"))
            provider = None
            if it.get("performer"):
                p0 = (it.get("performer") or [None])[0] or {}
                act = p0.get("actor") or {}
                provider = act.get("display")
            exists = session.query(Procedure).filter_by(patient_id=pat.id, procedure_name=name, date=date).first()
            if exists:
                continue
            row = Procedure(patient_id=pat.id, procedure_name=name, date=date, provider=provider)
            session.add(row)
            new += 1
        session.commit()
        return new
    finally:
        session.close()


def ingest_diagnostic_reports_as_notes(engine: Engine, reports: List[Dict[str, Any]], binary_loader) -> Tuple[int, int]:
    """Ingest DiagnosticReport.presentedForm as notes (similar to DocumentReference).

    Returns (new_rows, skipped_no_content).
    """
    new_total = 0
    skipped_total = 0
    # Convert each DR into a pseudo-DocumentReference-like structure and reuse _extract_note_text
    session = get_session(engine)
    try:
        pat = _patient_row(session) or upsert_patient(engine, None)
        for dr in reports:
            presented = dr.get("presentedForm") or []
            if not presented:
                skipped_total += 1
                continue
            # Build a minimal doc-like structure
            doc = {
                "content": [{"attachment": pf} for pf in presented],
                "date": dr.get("effectiveDateTime") or dr.get("issued"),
                "description": _code_text(dr.get("code")) or dr.get("category", [{}])[0].get("text") if isinstance(dr.get("category"), list) else _code_text(dr.get("code")),
                "id": dr.get("id"),
                "author": [{"display": (dr.get("performer") or [{}])[0].get("display")}],
            }
            title = _docref_title(doc) or "Diagnostic Report"
            date = _docref_date(doc)
            provider = _docref_provider(doc)
            content_text, ctype = _extract_note_text(doc, binary_loader)
            if not content_text:
                skipped_total += 1
                continue
            # Deduplicate using same logic as DocumentReference
            title_base = title
            exists = session.query(Note).filter_by(patient_id=pat.id, note_date=date, note_title=title_base).first()
            if exists:
                drid = dr.get("id")
                if isinstance(drid, str) and drid:
                    title = f"{title_base} [DR:{drid}]"
                else:
                    digest = hashlib.sha1(content_text.encode("utf-8", errors="replace")).hexdigest()[:8]
                    title = f"{title_base} [H:{digest}]"
                exists2 = session.query(Note).filter_by(patient_id=pat.id, note_date=date, note_title=title).first()
                if exists2:
                    continue
            note = Note(patient_id=pat.id, note_type="FHIR DiagnosticReport", note_date=date, note_title=title, note_content=content_text, provider=provider)
            session.add(note)
            new_total += 1
        session.commit()
        return new_total, skipped_total
    finally:
        session.close()

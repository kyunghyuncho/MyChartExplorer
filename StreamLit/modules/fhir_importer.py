"""FHIR importer: map DocumentReference (+Binary) into notes table.

Initial scope: Ingest clinical notes by reading DocumentReference resources,
resolving attachments via Binary or direct content, and inserting into the
existing SQLAlchemy `notes` table.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .database import Note, Patient, get_session


def _patient_row(session: Session) -> Optional[Patient]:
    # For now, assume singleton patient per user DB; take first row if present
    return session.query(Patient).first()


def _docref_title(doc: Dict[str, Any]) -> Optional[str]:
    title = doc.get("description") or doc.get("type", {}).get("text")
    return title


def _docref_date(doc: Dict[str, Any]) -> Optional[str]:
    return doc.get("date") or doc.get("indexed")


def _docref_provider(doc: Dict[str, Any]) -> Optional[str]:
    custodian = (doc.get("custodian") or {}).get("display")
    author = None
    for a in doc.get("author", []) or []:
        author = a.get("display") or author
    return author or custodian


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
                try:
                    return raw.decode("utf-8", errors="replace"), att.get("contentType")
                except Exception:
                    return raw.hex(), att.get("contentType")
            except Exception:
                continue
        url = att.get("url")
        if url:
            # Binary/{id} or full URL
            if url.startswith("Binary/"):
                bid = url.split("/", 1)[1]
                data = binary_loader(bid)
                try:
                    return data.decode("utf-8", errors="replace"), att.get("contentType")
                except Exception:
                    return data.hex(), att.get("contentType")
    return None, None


def ingest_document_references(engine: Engine, docs: List[Dict[str, Any]], binary_loader) -> int:
    """Insert notes from DocumentReference list. Returns number of new rows."""
    session = get_session(engine)
    try:
        patient = _patient_row(session)
        if not patient:
            # Create a placeholder patient row if none exists yet
            patient = Patient(mrn=None, full_name=None, dob=None)
            session.add(patient)
            session.flush()
        new_count = 0
        for doc in docs:
            title = _docref_title(doc) or "Clinical Note"
            date = _docref_date(doc)
            provider = _docref_provider(doc)
            content_text, ctype = _extract_note_text(doc, binary_loader)
            if not content_text:
                continue
            # Deduplicate by (patient_id, note_date, note_title)
            exists = session.query(Note).filter_by(
                patient_id=patient.id, note_date=date, note_title=title
            ).first()
            if exists:
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
        return new_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

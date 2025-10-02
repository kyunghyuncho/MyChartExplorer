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
            print(f'Fetching Binary resource from URL: {url}')
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
            print(f'Extracted Binary ID: {bid}')
            if bid:
                try:
                    data = binary_loader(bid)
                    print(f'!!!!!!!!')
                    ctype = att.get("contentType")
                    print(f'Fetched {len(data)} bytes for Binary/{bid}, contentType={ctype}')
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
            print(f'Extracted content type: {ctype}')
            print(f'Extracted content text: {content_text}')
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

            # Debug prints to help track import behavior
            print(f"Prepared note: {title}, exists={exists is not None}")

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

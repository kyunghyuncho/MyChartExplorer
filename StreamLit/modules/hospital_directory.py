"""Hospital directory utilities to help users find FHIR Base URLs.

This module provides curated entries and remote lookups (Epic Open Endpoints)
that can populate Base/Auth/Token URLs for SMART on FHIR.
"""
from __future__ import annotations

from typing import List, Dict, Iterable
import csv
import io
import re
import requests


def _curated_catalog() -> List[Dict[str, str]]:
    return [
        {
            "name": "Epic Public R4 Sandbox",
            "vendor": "Epic",
            "base_url": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
            "notes": "Supports SMART on FHIR; use Epic's OAuth endpoints discovered via .well-known.",
        },
        {
            "name": "HAPI Public R4 (no SMART)",
            "vendor": "HAPI FHIR",
            "base_url": "https://hapi.fhir.org/baseR4",
            "notes": "Public test server; typically does not provide SMART OAuth endpoints.",
        },
        {
            "name": "SMART Health IT R4 (simulator)",
            "vendor": "SMART",
            "base_url": "https://r4.smarthealthit.org",
            "notes": "FHIR server for testing; SMART launches are handled via the SMART Launcher, not the server itself.",
        },
    ]


def search_hospitals(query: str | None = None) -> List[Dict[str, str]]:
    q = (query or "").strip().lower()
    items = _curated_catalog()
    if not q:
        return items
    return [it for it in items if q in it.get("name", "").lower() or q in it.get("vendor", "").lower()]


# --- Vendor CSV helpers (optional) ---

def _guess_base_url(row: Dict[str, str]) -> str | None:
    url_cols = [
        r"fhir.*base.*url",
        r"fhir.*url",
        r"endpoint.*url",
        r"endpoint",
        r"url",
        r"api.*url",
    ]
    for k in row.keys():
        lk = (k or "").lower()
        if any(re.search(p, lk) for p in url_cols):
            v = (row.get(k) or "").strip()
            if v.startswith("http://") or v.startswith("https://"):
                return v
    for v in row.values():
        s = (v or "").strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return None


def _guess_name(row: Dict[str, str]) -> str | None:
    name_cols = [r"organization", r"organisation", r"facility", r"system", r"name", r"display"]
    for k in row.keys():
        lk = (k or "").lower()
        if any(re.search(p, lk) for p in name_cols):
            v = (row.get(k) or "").strip()
            if v:
                return v
    return None


def fetch_vendor_directory_csv(url: str, vendor_hint: str = "") -> List[Dict[str, str]]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.content
    try:
        text = data.decode("utf-8")
    except Exception:
        text = data.decode("latin-1", errors="replace")
    rdr = csv.DictReader(io.StringIO(text))
    results: List[Dict[str, str]] = []
    for row in rdr:
        base = _guess_base_url(row)
        if not base:
            continue
        nm = _guess_name(row) or "Healthcare Organization"
        results.append({
            "name": nm,
            "vendor": vendor_hint or "",
            "base_url": base,
        })
    return results


# --- Epic Open Endpoints (JSON) ---

def fetch_epic_open_endpoints_json(url: str = "https://open.epic.com/Endpoints/R4") -> List[Dict[str, str]]:
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    entries = resp.json()["entry"]
    results: List[Dict[str, str]] = []

    for ent in entries:
        resource = ent.get("resource") or {}
        if not isinstance(resource, dict):
            continue
        name = resource.get("name") or ""
        base_url = resource.get("address") or None

        # auth_url and token_url are retrieved from base_url/+".well-known/smart-configuration"
        # first read the xml file from base_url+".well-known/smart-configuration"
        xml_url = (base_url or "").rstrip("/") + "/.well-known/smart-configuration"
        try:
            xml_resp = requests.get(xml_url, headers={"Accept": "application/xml"}, timeout=15)
            xml_resp.raise_for_status()
            xml_text = xml_resp.text
            # Extract authorization_endpoint and token_endpoint from the XML content using regex
            auth_match = re.search(r'<authorization_endpoint>(.*?)</authorization_endpoint>', xml_text)
            token_match = re.search(r'<token_endpoint>(.*?)</token_endpoint>', xml_text)
            auth_url = auth_match.group(1) if auth_match else ""
            token_url = token_match.group(1) if token_match else ""
        except Exception:
            token_url = None
            auth_url = None

        if base_url and auth_url and token_url:
            results.append({
                "name": name,
                "vendor": "Epic",
                "base_url": base_url,
                "auth_url": auth_url,
                "token_url": token_url,
            })

    return results
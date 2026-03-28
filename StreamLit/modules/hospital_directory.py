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
    """Fetch Epic Open Endpoints and normalize quickly.

    Returns a list of dicts with fields: name, vendor (Epic), base_url.
    auth_url and token_url are intentionally left blank to be discovered lazily
    after the user selects a site (to keep loading fast).
    """
    # Accept JSON but tolerate HTML; we'll parse accordingly without heavy lookups
    resp = requests.get(url, headers={"Accept": "application/json, text/html;q=0.8"}, timeout=30)
    resp.raise_for_status()

    results: List[Dict[str, str]] = []

    def add_result(name: str, base: str) -> None:
        base = (base or "").strip()
        if not base:
            return
        # Deduplicate by base_url
        for r in results:
            if r.get("base_url") == base:
                return
        # If name is empty, use hostname as a friendly label
        label = name or re.sub(r"^https?://", "", base).split("/")[0]
        results.append({
            "name": label,
            "vendor": "Epic",
            "base_url": base,
            "auth_url": "",
            "token_url": "",
        })

    # Try JSON first
    parsed = None
    try:
        parsed = resp.json()
    except Exception:
        parsed = None

    if parsed is not None:
        # Many public directories return either a list or a dict with a list under common keys
        items = None
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            for k in [
                "endpoints", "Endpoints", "data", "resources", "organizations", "Organizations", "entry", "Entry"
            ]:
                if isinstance(parsed.get(k), list):
                    items = parsed[k]
                    break
            # FHIR Bundle style: { entry: [ { resource: {...} } ] }
            if items is None and isinstance(parsed.get("entry"), list):
                items = parsed.get("entry")
        if isinstance(items, list):
            for it in items:
                # Support both plain dict entries and FHIR Bundle entries with {resource:{}}
                row = it
                if isinstance(it, dict) and "resource" in it and isinstance(it["resource"], dict):
                    row = it["resource"]
                if not isinstance(row, dict):
                    continue
                # Try a variety of plausible keys
                name = None
                for key in ["OrganizationName", "DisplayName", "Name", "Organization", "name"]:
                    if isinstance(row.get(key), str) and row.get(key).strip():
                        name = row.get(key).strip()
                        break
                base = None
                for key in [
                    "FHIRPatientFacingURI", "FHIRBaseURL", "FHIRBaseUrl", "BaseURL", "BaseUrl", "URL", "Url", "address"
                ]:
                    if isinstance(row.get(key), str) and row.get(key).strip():
                        base = row.get(key).strip()
                        break
                # Sometimes base is nested
                if base is None and isinstance(row.get("endpoint"), dict):
                    maybe = row["endpoint"].get("url") or row["endpoint"].get("href")
                    if isinstance(maybe, str):
                        base = maybe
                if base:
                    add_result(name or "", base)

    # Fallback: scrape from HTML/text via regex if JSON route yielded nothing
    if not results:
        text = resp.text
        # Look for common Epic FHIR base URL patterns
        patterns = [
            r"https?://[^\s'\"]+/interconnect-fhir-oauth/api/FHIR/R4",
            r"https?://[^\s'\"]+/api/FHIR/R4",
            r"https?://[^\s'\"]+/FHIR/R4",
        ]
        found: set[str] = set()
        for pat in patterns:
            for m in re.findall(pat, text):
                found.add(m.rstrip("/"))
        for base in sorted(found):
            add_result("", base)

    return results
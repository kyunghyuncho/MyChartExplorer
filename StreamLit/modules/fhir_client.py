"""Minimal SMART on FHIR client with PKCE for Epic sandbox.

This module provides:
- PKCE generation (code_verifier, code_challenge)
- Authorization URL builder
- Token exchange and refresh
- Simple GET helper with paging (Bundle.next)
- Convenience fetchers for DocumentReference and Binary resources

Tokens are not persisted here; callers should manage them in session_state.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float  # epoch seconds when access token expires
    token_type: str = "Bearer"
    scope: Optional[str] = None
    patient_id: Optional[str] = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 using S256."""
    verifier = _b64url(os.urandom(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_authorize_url(
    auth_url: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    state: str,
    aud: Optional[str] = None,
    response_mode: str = "query",
) -> str:
    from urllib.parse import urlencode
    q = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        # SMART extras (optional): aud (FHIR base)
    }
    if aud:
        q["aud"] = aud
    if response_mode:
        q["response_mode"] = response_mode
    return f"{auth_url}?{urlencode(q)}"


def exchange_token(token_url: str, code: str, client_id: str, redirect_uri: str, code_verifier: str) -> OAuthTokens:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    resp = requests.post(token_url, data=data, headers={"Accept": "application/json"}, timeout=30)
    if not resp.ok:
        # Surface Epic error details for easier debugging
        try:
            j = resp.json()
            err = j.get("error")
            desc = j.get("error_description") or j.get("message")
            raise requests.HTTPError(f"{resp.status_code} {resp.reason}: {err or 'error'} - {desc or resp.text}")
        except ValueError:
            resp.raise_for_status()
    t = resp.json()
    expires_in = int(t.get("expires_in", 3600))
    return OAuthTokens(
        access_token=t["access_token"],
        refresh_token=t.get("refresh_token"),
        expires_at=time.time() + max(60, expires_in - 30),
        token_type=t.get("token_type", "Bearer"),
        scope=t.get("scope"),
        patient_id=t.get("patient"),
    )


def refresh_token(token_url: str, refresh_token: str, client_id: str) -> OAuthTokens:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    resp = requests.post(token_url, data=data, headers={"Accept": "application/json"}, timeout=30)
    if not resp.ok:
        try:
            j = resp.json()
            err = j.get("error")
            desc = j.get("error_description") or j.get("message")
            raise requests.HTTPError(f"{resp.status_code} {resp.reason}: {err or 'error'} - {desc or resp.text}")
        except ValueError:
            resp.raise_for_status()
    t = resp.json()
    expires_in = int(t.get("expires_in", 3600))
    return OAuthTokens(
        access_token=t["access_token"],
        refresh_token=t.get("refresh_token", refresh_token),
        expires_at=time.time() + max(60, expires_in - 30),
        token_type=t.get("token_type", "Bearer"),
        scope=t.get("scope"),
    )


def _auth_header(tokens: OAuthTokens) -> Dict[str, str]:
    return {"Authorization": f"{tokens.token_type} {tokens.access_token}", "Accept": "application/fhir+json"}


def get_json(url: str, tokens: OAuthTokens, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resp = requests.get(url, headers=_auth_header(tokens), params=params or {}, timeout=30)
    if not resp.ok:
        # Try to surface FHIR OperationOutcome or JSON error details
        try:
            data = resp.json()
            msg = None
            if isinstance(data, dict):
                # OperationOutcome per FHIR
                if data.get("resourceType") == "OperationOutcome":
                    issues = data.get("issue") or []
                    if issues:
                        diag = issues[0].get("diagnostics") or issues[0].get("details", {}).get("text")
                        msg = f"OperationOutcome: {diag}"
                # Generic error fields
                msg = msg or data.get("error_description") or data.get("message") or str(data)
            raise requests.HTTPError(f"{resp.status_code} {resp.reason} - {msg}")
        except ValueError:
            resp.raise_for_status()
    return resp.json()


def paged_get(base_url: str, resource_type: str, tokens: OAuthTokens, params: Optional[Dict[str, Any]] = None, max_pages: int = 10) -> List[Dict[str, Any]]:
    """Fetch a FHIR Bundle in pages, returning list of entries' resources."""
    url = f"{base_url.rstrip('/')}/{resource_type}"
    results: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    next_params = params or {}
    pages = 0
    while next_url and pages < max_pages:
        data = get_json(next_url, tokens, params=next_params)
        next_params = None  # encoded in next link
        pages += 1
        if data.get("resourceType") == "Bundle":
            for e in data.get("entry", []) or []:
                r = e.get("resource")
                if r:
                    results.append(r)
            next_url = None
            for link in data.get("link", []) or []:
                if link.get("relation") == "next":
                    next_url = link.get("url")
                    break
        else:
            # Single resource response
            results.append(data)
            next_url = None
    return results


def fetch_document_references(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    if categories:
        params["category"] = ",".join(categories)
    return paged_get(base_url, "DocumentReference", tokens, params=params)


def fetch_binary(base_url: str, tokens: OAuthTokens, binary_id: str) -> bytes:
    """Fetch raw content for a Binary resource.

    Tries standard Binary/{id}, and on 403/404 falls back to Binary/{id}/$binary.
    Uses Accept: */* to prefer raw content over JSON.
    """
    base = base_url.rstrip('/')
    url = f"{base}/Binary/{binary_id}"
    headers_raw = {"Authorization": f"{tokens.token_type} {tokens.access_token}", "Accept": "*/*"}
    resp = requests.get(url, headers=headers_raw, timeout=60)
    print(f'Fetching Binary resource from URL: {url}')
    print(f'Response status code: {resp.status_code}')
    if resp.status_code in (403, 404):
        alt = f"{url}/$binary"
        resp2 = requests.get(alt, headers=headers_raw, timeout=60)
        resp2.raise_for_status()
        return resp2.content
    resp.raise_for_status()
    # Some servers return JSON Binary instead of raw bytes when Accept is */*
    ctype = resp.headers.get("Content-Type", "")
    print(f'Fetched Binary/{binary_id}, contentType={ctype}')
    if "json" in ctype.lower() or (resp.content[:1] in b"[{"):
        try:
            jb = resp.json()
            # FHIR Binary resource with base64-encoded 'data'
            data_b64 = jb.get("data")
            if isinstance(data_b64, str):
                import base64
                return base64.b64decode(data_b64)
            # No inline data found; try $binary endpoint as a fallback
            alt = f"{url}/$binary"
            resp2 = requests.get(alt, headers=headers_raw, timeout=60)
            resp2.raise_for_status()
            return resp2.content
        except ValueError:
            # Not valid JSON; fall through to raw bytes
            pass
    return resp.content


def discover_smart_configuration(base_url: str) -> Dict[str, Any]:
    """Fetch the SMART on FHIR discovery document for the given FHIR base.

    Returns the JSON dict from {base}/.well-known/smart-configuration.
    Raises requests.HTTPError on HTTP errors and ValueError if payload is not JSON.
    """
    url = f"{base_url.rstrip('/')}/.well-known/smart-configuration"
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("SMART configuration response is not a JSON object")
    return data

# --- Additional resource fetchers for broader ingestion ---

def fetch_patient(base_url: str, tokens: OAuthTokens, patient_id: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/Patient/{patient_id}"
    return get_json(url, tokens)


def fetch_allergy_intolerances(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "AllergyIntolerance", tokens, params=params)


def fetch_conditions(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "Condition", tokens, params=params)


def fetch_medication_statements(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    # Some servers (including Epic Public R4) may not implement MedicationStatement search and return 404
    try:
        return paged_get(base_url, "MedicationStatement", tokens, params=params)
    except requests.HTTPError as e:
        status = getattr(getattr(e, 'response', None), 'status_code', None)
        if status == 404:
            # Treat as not supported; caller can rely on MedicationRequest instead
            return []
        raise


def fetch_medication_requests(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    try:
        return paged_get(base_url, "MedicationRequest", tokens, params=params)
    except requests.HTTPError as e:
        status = getattr(getattr(e, 'response', None), 'status_code', None)
        if status == 404:
            return []
        raise


def fetch_immunizations(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "Immunization", tokens, params=params)


def fetch_observations(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, category: Optional[str] = None, codes: Optional[List[str]] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if category:
        params["category"] = category
    if codes:
        params["code"] = ",".join(codes)
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "Observation", tokens, params=params)


def fetch_procedures(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "Procedure", tokens, params=params)


def fetch_diagnostic_reports(base_url: str, tokens: OAuthTokens, patient_id: Optional[str] = None, category: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if patient_id:
        params["patient"] = patient_id
    if category:
        params["category"] = category
    if since:
        params["_lastUpdated"] = f"ge{since}"
    return paged_get(base_url, "DiagnosticReport", tokens, params=params)

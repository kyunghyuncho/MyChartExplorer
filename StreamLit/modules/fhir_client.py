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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 using S256."""
    verifier = _b64url(os.urandom(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_authorize_url(auth_url: str, client_id: str, redirect_uri: str, scope: str, code_challenge: str, state: str) -> str:
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
    resp.raise_for_status()
    t = resp.json()
    expires_in = int(t.get("expires_in", 3600))
    return OAuthTokens(
        access_token=t["access_token"],
        refresh_token=t.get("refresh_token"),
        expires_at=time.time() + max(60, expires_in - 30),
        token_type=t.get("token_type", "Bearer"),
        scope=t.get("scope"),
    )


def refresh_token(token_url: str, refresh_token: str, client_id: str) -> OAuthTokens:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    resp = requests.post(token_url, data=data, headers={"Accept": "application/json"}, timeout=30)
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
    url = f"{base_url.rstrip('/')}/Binary/{binary_id}"
    resp = requests.get(url, headers=_auth_header(tokens), timeout=60)
    resp.raise_for_status()
    return resp.content

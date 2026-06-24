"""WS-E: ThoughtSpot REST client - auth + TML import (verified against ps-internal).

Auth uses Trusted Authentication: a `secret_key` mints a full-access token on demand
(POST /api/rest/2.0/auth/token/full), so tokens never go stale mid-run. Falls back to a
static `token` if no secret_key is configured. TML import is POST /metadata/tml/import.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

# Internal cluster certs may not chain in a plain script; the cluster is the user's own.
_CTX = ssl._create_unverified_context()


def get_token(ts_cfg: dict) -> str:
    """Mint a full-access token from a trusted-auth secret_key, else use a static token."""
    base = ts_cfg["base_url"].rstrip("/")
    if ts_cfg.get("secret_key"):
        body = {"username": ts_cfg["username"], "secret_key": ts_cfg["secret_key"],
                "org_id": ts_cfg.get("org_id"),
                "validity_time_in_sec": ts_cfg.get("token_validity_sec", 3600)}
        body = {k: v for k, v in body.items() if v is not None}
        req = urllib.request.Request(
            base + "/api/rest/2.0/auth/token/full", data=json.dumps(body).encode(),
            method="POST", headers={"Content-Type": "application/json", "Accept": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=40, context=_CTX).read().decode())["token"]
    return ts_cfg["token"]


def import_tml(base_url: str, token: str, tmls: list[str], policy: str = "ALL_OR_NONE") -> list:
    """Import TML strings. policy: ALL_OR_NONE | PARTIAL | VALIDATE_ONLY."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/rest/2.0/metadata/tml/import",
        data=json.dumps({"metadata_tmls": tmls, "import_policy": policy}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + token})
    return json.loads(urllib.request.urlopen(req, timeout=180, context=_CTX).read().decode())


def status_of(item: dict) -> tuple[str, str, str]:
    """Pull (status_code, object_name, guid) out of one import-response item."""
    resp = item.get("response") or {}
    st = resp.get("status") or item.get("status") or {}
    hdr = resp.get("header") or {}
    return st.get("status_code", "?"), hdr.get("name", "?"), hdr.get("id_guid", "")

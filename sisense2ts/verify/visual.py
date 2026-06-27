"""H8 visual-QA gate: render a migrated ThoughtSpot Liveboard/Answer to an image and
confirm it actually drew (validates is not renders, the recurring lesson).

The numeric parity gate proves the values; this proves the page renders to a real,
non-trivial image rather than a blank/errored canvas. The saved artifact is then read
against the Sisense source (the human-read step, same as the Sigma visual-QA gate); a
pixel diff is intentionally out of scope (different chart engines never match byte-for-byte).
"""
from __future__ import annotations

import json
import ssl
import urllib.request

_CTX = ssl._create_unverified_context()
_MAGIC = {"PNG": b"\x89PNG\r\n\x1a\n", "PDF": b"%PDF"}


def render(base_url: str, token: str, identifier: str, fmt: str = "PNG", kind: str = "liveboard") -> bytes:
    """Render a Liveboard/Answer to PNG/PDF bytes via POST /api/rest/2.0/report/{kind}."""
    req = urllib.request.Request(
        base_url.rstrip("/") + f"/api/rest/2.0/report/{kind}",
        data=json.dumps({"metadata_identifier": identifier, "file_format": fmt}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/octet-stream",
                 "Authorization": "Bearer " + token})
    return urllib.request.urlopen(req, timeout=120, context=_CTX).read()


def valid_image(data: bytes, fmt: str = "PNG", min_bytes: int = 10000) -> tuple[bool, str]:
    """A rendered report is 'real' when it has the right magic bytes and is not trivially
    small (a blank or errored render comes back tiny). Pure: unit-tested without a cluster."""
    magic = _MAGIC.get(fmt.upper(), b"")
    if not data or not data.startswith(magic):
        return False, f"not a valid {fmt} (bad header)"
    if len(data) < min_bytes:
        return False, f"{fmt} only {len(data)} bytes - likely blank or errored"
    return True, f"{fmt} {len(data)} bytes"

"""WS-E: ThoughtSpot REST client. Imports generated TML into the trial.

Auth: bearer token (POST /api/rest/2.0/auth/token/full with username + secret_key,
or paste a token from the trial). Import: POST /api/rest/2.0/metadata/tml/import.

Import all related objects in ONE call (connection/tables/model/answers/liveboard)
so references resolve. Use import_policy=VALIDATE_ONLY for a dry run, ALL_OR_NONE for
the real import. Export with FQNs and feed them back to disambiguate same-named objects.
"""
from __future__ import annotations

import requests


class ThoughtSpotClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def import_tml(self, tmls: list[str], policy: str = "ALL_OR_NONE", create_new: bool = False) -> list:
        """POST /api/rest/2.0/metadata/tml/import. `tmls` is a list of TML strings
        (YAML or JSON). policy in {PARTIAL, ALL_OR_NONE, VALIDATE_ONLY, PARTIAL_OBJECT}."""
        r = self._session.post(
            f"{self.base_url}/api/rest/2.0/metadata/tml/import",
            json={"metadata_tmls": tmls, "import_policy": policy, "create_new": create_new},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    def validate_tml(self, tmls: list[str]) -> list:
        """Dry run: import with VALIDATE_ONLY to surface errors without creating objects."""
        return self.import_tml(tmls, policy="VALIDATE_ONLY")

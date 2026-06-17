"""WS-A: Sisense REST client. Pulls raw JSON; no IR shaping here (see parse.py).

Endpoints below are verified from the Sisense REST docs + PySense. Auth is a Bearer
token. Use a service/admin account on the trial. Do NOT commit tokens; read them
from config (see config.example.yaml).

Day-1 spike (P1): get auth working against the trial, then pull ONE dashboard and
the datamodel schema and drop them into tests/fixtures/ as real samples.
"""
from __future__ import annotations

import requests


class SisenseClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool = True):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        self._verify = verify_tls

    # -- auth ---------------------------------------------------------------- #
    @classmethod
    def login(cls, base_url: str, username: str, password: str) -> "SisenseClient":
        """POST /api/v1/authentication/login -> {access_token}. For SSO users use a
        pre-issued token from GET /api/v1/authentication/tokens/api instead."""
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/v1/authentication/login",
            data={"username": username, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        return cls(base_url, resp.json()["access_token"])

    def _get(self, path: str, **params) -> dict | list:
        r = self._session.get(f"{self.base_url}{path}", params=params, verify=self._verify, timeout=60)
        r.raise_for_status()
        return r.json()

    # -- dashboards (v1) ----------------------------------------------------- #
    def list_dashboards(self) -> list:
        """GET /api/v1/dashboards"""
        return self._get("/api/v1/dashboards")  # type: ignore[return-value]

    def get_dashboard(self, oid: str) -> dict:
        """GET /api/v1/dashboards/{oid} (full JSON incl. widgets + layout)."""
        return self._get(f"/api/v1/dashboards/{oid}")  # type: ignore[return-value]

    def get_widgets(self, oid: str) -> list:
        """GET /api/v1/dashboards/{oid}/widgets"""
        return self._get(f"/api/v1/dashboards/{oid}/widgets")  # type: ignore[return-value]

    def export_dash(self, oid: str) -> dict:
        """GET /api/v1/dashboards/export?dashboardIds={oid} -> importable .dash JSON."""
        return self._get("/api/v1/dashboards/export", dashboardIds=oid)  # type: ignore[return-value]

    # -- data model (v2) ----------------------------------------------------- #
    def list_datamodels(self) -> list:
        """GET /api/v2/datamodels/schema?fields=oid,title"""
        return self._get("/api/v2/datamodels/schema", fields="oid,title")  # type: ignore[return-value]

    def export_datamodel(self, datamodel_id: str) -> dict:
        """GET /api/v2/datamodel-exports/schema?datamodelId=..&type=schema-latest
        Returns the full schema: datasets -> tables -> columns, plus relations."""
        return self._get(
            "/api/v2/datamodel-exports/schema",
            datamodelId=datamodel_id,
            type="schema-latest",
        )  # type: ignore[return-value]

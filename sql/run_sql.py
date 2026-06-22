#!/usr/bin/env python3
"""Run a .sql file against Databricks via the SQL Statement Execution API.

Reads databricks host/warehouse_id/token/catalog/schema from config.yaml (gitignored, so
no secret lives in this file). Splits on ';', skips USE/comment lines, runs CREATE SCHEMA
without a schema context and everything else with catalog+schema set per statement (the
API has no persistent session across calls).

    python sql/run_sql.py sql/databricks_sample_ecommerce.sql
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(open("config.yaml"))["databricks"]
HOST = cfg["host"].rstrip("/").replace("http://", "https://")
WID, TOK, CAT, SCH = cfg["warehouse_id"], cfg["token"], cfg["catalog"], cfg["schema"]


def _api(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        HOST + path, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"status": {"state": f"HTTP_{e.code}", "error": e.read().decode()[:400]}}


def _get(statement_id: str) -> dict:
    req = urllib.request.Request(HOST + "/api/2.0/sql/statements/" + statement_id,
                                 headers={"Authorization": "Bearer " + TOK})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"status": {"state": f"HTTP_{e.code}", "error": e.read().decode()[:400]}}


def run_stmt(stmt: str, use_schema: bool = True):
    body = {"warehouse_id": WID, "statement": stmt, "catalog": CAT,
            "wait_timeout": "50s", "disposition": "INLINE", "format": "JSON_ARRAY"}
    if use_schema:
        body["schema"] = SCH
    r = _api("/api/2.0/sql/statements", body)
    status = r.get("status") or {}
    state, sid, tries = status.get("state"), r.get("statement_id"), 0
    while state in ("PENDING", "RUNNING") and sid and tries < 40:  # wait out a cold warehouse
        time.sleep(3)
        tries += 1
        r = _get(sid)
        status = r.get("status") or {}
        state = status.get("state")
    return state, status.get("error"), r.get("result")


def main(path: str) -> int:
    lines = [l for l in Path(path).read_text().splitlines() if not l.strip().startswith("--")]
    stmts = [s.strip() for s in " ".join(lines).split(";") if s.strip()]
    ok = fail = 0
    for s in stmts:
        if s.upper().startswith("USE "):
            continue
        state, err, result = run_stmt(s, use_schema=not s.upper().startswith("CREATE SCHEMA"))
        label = " ".join(s.split())[:64]
        if state == "SUCCEEDED":
            ok += 1
            print(f"  OK   {label}")
            if result and result.get("data_array"):
                print("       result:", result["data_array"])
        else:
            fail += 1
            print(f"  FAIL {label}\n       {state}: {err}")
    print(f"\n{ok} ok, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "sql/databricks_sample_ecommerce.sql"))

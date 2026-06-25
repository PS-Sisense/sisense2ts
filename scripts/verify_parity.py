#!/usr/bin/env python3
"""Phase 5 parity gate — prove the migrated ThoughtSpot answers return the SAME
numbers as the warehouse ground truth (and Sisense, when a live source token is
available).

    PYTHONPATH=. .venv/bin/python scripts/verify_parity.py

Anchors on ThoughtSpot /searchdata vs Databricks SQL (no Sisense access needed).
The Sisense JAQL leg turns on automatically if config.yaml has a live
`sisense.token` AND a `sisense.datasource` id; otherwise it is reported skipped.
Exits non-zero if any metric is RED — so it can hard-gate a release.
"""
import json
import ssl
import sys
import urllib.request

import yaml

from sisense2ts.load import ts_client
from sisense2ts.verify import parity

CTX = ssl._create_unverified_context()
MODEL_NAME = "Sample ECommerce (Sisense)"

# Ground-truth SQL runs with catalog+schema already set (workspace.sisense_demo),
# so table names are unqualified. Each check pairs a ThoughtSpot search query with
# the equivalent warehouse aggregate.
CHECKS = [
    parity.ParityCheck("Total Revenue", "[Revenue]", "SELECT sum(Revenue) FROM Commerce", dims=0),
    parity.ParityCheck("Total Quantity", "[Quantity]", "SELECT sum(Quantity) FROM Commerce", dims=0),
    parity.ParityCheck("Total Cost", "[Cost]", "SELECT sum(Cost) FROM Commerce", dims=0),
    parity.ParityCheck("Revenue by Category", "[Category] [Revenue]",
                       "SELECT c.Category, sum(m.Revenue) FROM Commerce m "
                       "JOIN Category c ON m.Category_ID=c.Category_ID GROUP BY c.Category", dims=1),
    parity.ParityCheck("Revenue by Country", "[Country] [Revenue]",
                       "SELECT c.Country, sum(m.Revenue) FROM Commerce m "
                       "JOIN Country c ON m.Country_ID=c.Country_ID GROUP BY c.Country", dims=1),
    parity.ParityCheck("Revenue by Brand", "[Brand] [Revenue]",
                       "SELECT b.Brand, sum(m.Revenue) FROM Commerce m "
                       "JOIN Brand b ON m.Brand_ID=b.Brand_ID GROUP BY b.Brand", dims=1),
    parity.ParityCheck("Revenue by Gender", "[Gender] [Revenue]",
                       "SELECT Gender, sum(Revenue) FROM Commerce GROUP BY Gender", dims=1),
    parity.ParityCheck("Units Sold by Age Range", "[Age Range] [Quantity]",
                       "SELECT Age_Range, sum(Quantity) FROM Commerce GROUP BY Age_Range", dims=1),
]


def find_model_id(base, token):
    req = urllib.request.Request(
        base.rstrip("/") + "/api/rest/2.0/metadata/search",
        data=json.dumps({"metadata": [{"type": "LOGICAL_TABLE", "name_pattern": MODEL_NAME}],
                         "record_size": 50}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + token})
    rows = json.loads(urllib.request.urlopen(req, timeout=60, context=CTX).read().decode())
    hits = [(r.get("metadata_id"), (r.get("metadata_header") or {}).get("modified", 0))
            for r in rows if r.get("metadata_name") == MODEL_NAME]
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits[0][0] if hits else None


def main():
    cfg = yaml.safe_load(open("config.yaml"))
    T, D, S = cfg["thoughtspot"], cfg["databricks"], cfg.get("sisense", {})
    token = ts_client.get_token(T)

    model_id = find_model_id(T["base_url"], token)
    if not model_id:
        raise SystemExit(f"no Model named {MODEL_NAME!r} on the cluster")
    ts = {"base_url": T["base_url"], "token": token, "model_id": model_id}
    print(f"model {MODEL_NAME!r} -> {model_id}")

    # Sisense leg only if both a token and a datasource id are configured.
    sisense = None
    if S.get("token") and S.get("datasource"):
        sisense = {"base_url": S["base_url"], "token": S["token"], "datasource": S["datasource"]}
    else:
        print("sisense leg: skipped (no live source token + datasource in config)\n")

    results = [parity.run_check(c, ts=ts, dbx=D, sisense=sisense) for c in CHECKS]
    print(parity.render(results))
    return 0 if parity.all_green(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

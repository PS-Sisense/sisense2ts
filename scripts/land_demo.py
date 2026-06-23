#!/usr/bin/env python3
"""End-to-end demo runner: Sisense Sample ECommerce -> ThoughtSpot Model + Liveboard.

Extracts the Sisense data model over REST, generates Table + Model TML and imports it,
then builds a Liveboard of Answers on that Model and imports it. The objects query
Databricks live. Reads all hosts/tokens from config.yaml (gitignored).

    python scripts/land_demo.py

Note: the Liveboard here uses a curated set of Answers on the model (proven working).
Full per-widget mapping from the Sisense dashboard lives in map/content.dashboard_to_tml
and is still being hardened (C1/C2).
"""
import json
import ssl
import urllib.error
import urllib.request

import yaml

from sisense2ts.extract import parse
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.map.content import answer_tml, liveboard_tml
from sisense2ts.map.model import model_to_tml

MODEL_NAME = "Sample ECommerce (Sisense)"
# (name, search_query, ordered column display names, chart type)
LIVEBOARD_SPECS = [
    ("Revenue by Country", "[Country] [Revenue]", ["Country", "Total Revenue"], "COLUMN"),
    ("Revenue by Brand", "[Brand] [Revenue]", ["Brand", "Total Revenue"], "COLUMN"),
    ("Revenue by Category", "[Category] [Revenue]", ["Category", "Total Revenue"], "BAR"),
    ("Revenue by Gender", "[Gender] [Revenue]", ["Gender", "Total Revenue"], "PIE"),
    ("Units Sold by Age Range", "[Age Range] [Quantity]", ["Age Range", "Total Quantity"], "COLUMN"),
    ("Revenue Trend", "[Date] [Revenue]", ["Date", "Total Revenue"], "LINE"),
]
_CTX = ssl._create_unverified_context()


def ts_import(ts, tmls, policy="ALL_OR_NONE"):
    req = urllib.request.Request(
        ts["base_url"].rstrip("/") + "/api/rest/2.0/metadata/tml/import",
        data=json.dumps({"metadata_tmls": tmls, "import_policy": policy}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + ts["token"]})
    return json.loads(urllib.request.urlopen(req, timeout=180, context=_CTX).read().decode())


def main():
    cfg = yaml.safe_load(open("config.yaml"))
    S, D, T = cfg["sisense"], cfg["databricks"], cfg["thoughtspot"]

    # 1. extract the Sample ECommerce data model from Sisense
    sc = SisenseClient(S["base_url"], S["token"])
    models = sc.list_datamodels()
    models = models if isinstance(models, list) else models.get("datamodels", [])
    mt = next(m for m in models if "ecommerce" in (m.get("title", "") or "").lower())
    sm = parse.parse_datamodel(sc.export_datamodel(mt["oid"]))
    print(f"extracted '{sm.name}': {len(sm.tables)} tables, {len(sm.relations)} joins")

    # 2. generate + import the Model (Tables + Model)
    out = model_to_tml(sm, D["connection_name"], D["connection_fqn"], D["catalog"], D["schema"],
                       model_name=MODEL_NAME)
    tmls = [yaml.safe_dump(t, sort_keys=False) for t in out["tables"]] + [yaml.safe_dump(out["model"], sort_keys=False)]
    model_fqn = None
    for r in ts_import(T, tmls):
        h = (r.get("response") or {}).get("header") or {}
        st = ((r.get("response") or {}).get("status") or {}).get("status_code")
        print(f"  model: {st} {h.get('type')} {h.get('name')}")
        if (h.get("name") == MODEL_NAME):
            model_fqn = h.get("id_guid")
    if not model_fqn:
        raise SystemExit("model import did not return a guid")

    # 3. build + import the Liveboard on the model
    answers = [answer_tml(n, MODEL_NAME, model_fqn, q, cols, ct) for (n, q, cols, ct) in LIVEBOARD_SPECS]
    lb = yaml.safe_dump(liveboard_tml(MODEL_NAME, answers), sort_keys=False)
    for r in ts_import(T, [lb]):
        h = (r.get("response") or {}).get("header") or {}
        st = ((r.get("response") or {}).get("status") or {}).get("status_code")
        print(f"  liveboard: {st} {h.get('name')} guid={h.get('id_guid')}")


if __name__ == "__main__":
    main()

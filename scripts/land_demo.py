#!/usr/bin/env python3
"""End-to-end demo runner: Sisense Sample ECommerce -> ThoughtSpot Model + Liveboard.

Extracts the Sisense data model over REST, generates Table + Model TML and imports it,
then builds a Liveboard (KPIs + charts) on that Model and imports it. The objects query
Databricks live. Auth mints a fresh token from the trusted-auth secret_key in config.yaml.

    python scripts/land_demo.py

Note: the Liveboard uses a curated set of Answers on the model (proven working). Full
per-widget mapping from the Sisense dashboard lives in map/content.dashboard_to_tml and
is still being hardened (C1/C2).
"""
import yaml

from sisense2ts.extract import parse
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.load import ts_client
from sisense2ts.map.content import answer_tml, liveboard_tml
from sisense2ts.map.model import model_to_tml

MODEL_NAME = "Sample ECommerce (Sisense)"
# (name, search_query, ordered column display names, chart type)
LIVEBOARD_SPECS = [
    ("Total Revenue", "[Revenue]", ["Total Revenue"], "KPI"),
    ("Total Units Sold", "[Quantity]", ["Total Quantity"], "KPI"),
    ("Total Cost", "[Cost]", ["Total Cost"], "KPI"),
    ("Total Brands", "unique count [Brand]", ["Unique Number of Brand"], "KPI"),
    ("Revenue by Country", "[Country] [Revenue]", ["Country", "Total Revenue"], "COLUMN"),
    ("Revenue by Brand", "[Brand] [Revenue]", ["Brand", "Total Revenue"], "COLUMN"),
    ("Revenue by Category", "[Category] [Revenue]", ["Category", "Total Revenue"], "BAR"),
    ("Revenue by Gender", "[Gender] [Revenue]", ["Gender", "Total Revenue"], "PIE"),
    ("Units Sold by Age Range", "[Age Range] [Quantity]", ["Age Range", "Total Quantity"], "COLUMN"),
    ("Revenue Trend", "[Date] [Revenue]", ["Date", "Total Revenue"], "LINE"),
]


def main():
    cfg = yaml.safe_load(open("config.yaml"))
    S, D, T = cfg["sisense"], cfg["databricks"], cfg["thoughtspot"]
    token = ts_client.get_token(T)

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
    for item in ts_client.import_tml(T["base_url"], token, tmls):
        code, name, guid = ts_client.status_of(item)
        print(f"  model: {code} {name}")
        if name == MODEL_NAME:
            model_fqn = guid
    if not model_fqn:
        raise SystemExit("model import did not return a guid")

    # 3. build + import the Liveboard on the model (skip any viz type that fails validation)
    answers = []
    for n, q, cols, ct in LIVEBOARD_SPECS:
        a = answer_tml(n, MODEL_NAME, model_fqn, q, cols, ct)
        res = ts_client.import_tml(T["base_url"], token, [yaml.safe_dump(liveboard_tml("v", [a]), sort_keys=False)], "VALIDATE_ONLY")
        if ts_client.status_of(res[0])[0] != "ERROR":
            answers.append(a)
        else:
            print(f"  skip viz '{n}' ({ct}) - failed validation")
    lb = yaml.safe_dump(liveboard_tml(MODEL_NAME, answers), sort_keys=False)
    for item in ts_client.import_tml(T["base_url"], token, [lb]):
        code, name, guid = ts_client.status_of(item)
        print(f"  liveboard: {code} {name} ({len(answers)} viz) guid={guid}")


if __name__ == "__main__":
    main()

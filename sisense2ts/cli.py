"""WS-E: end-to-end runner. This is the demo command on June 26.

    python -m sisense2ts.cli --config config.yaml --dashboard <oid> --out ./out

Pipeline:  extract (Sisense) -> parse to IR -> map to TML -> validate+import (TS)
           -> write coverage report.

Right now every stage calls into stubs that raise NotImplementedError. As each
workstream lands, this wiring lights up stage by stage. Keep the stage boundaries
exactly as below so partial progress is demoable (e.g. M1 = stop after model import).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from sisense2ts.extract import parse
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.ir.models import CoverageReport
from sisense2ts.load import ts_client
from sisense2ts.map import content as map_content
from sisense2ts.map import model as map_model
from sisense2ts.report.coverage import render_markdown


def _aslist(x, key):
    return x if isinstance(x, list) else (x or {}).get(key, [])


def run(config: dict, dashboard_oid: str, out_dir: Path, dry_run: bool = False,
        faithful_layout: bool = False) -> None:
    """Extract a Sisense dashboard -> TML, import in TWO phases (Model, then content bound
    to the read-back Model GUID), and write a coverage report. Auth mints a fresh token
    from the trusted-auth secret_key. --dry-run validates the Model only (no GUID to bind
    content to without an import) but still computes + writes the coverage report."""
    report = CoverageReport()
    out_dir.mkdir(parents=True, exist_ok=True)
    S, D, T = config["sisense"], config["databricks"], config["thoughtspot"]

    # 1. EXTRACT (WS-A): dashboard + its widgets (a separate call) + the backing data model.
    sis = SisenseClient(S["base_url"], S["token"])
    raw_dash = sis.get_dashboard(dashboard_oid)
    ir_dash = parse.parse_dashboard(raw_dash, _aslist(sis.get_widgets(dashboard_oid), "widgets"))
    ds_title = (raw_dash.get("datasource") or {}).get("title", "")
    models = _aslist(sis.list_datamodels(), "datamodels")
    mt = next((m for m in models if (m.get("title", "") or "") == ds_title), None)
    model_oid = (mt or {}).get("oid") or S.get("datamodel_id")
    ir_model = parse.parse_datamodel(sis.export_datamodel(model_oid))
    model_name = f"{ir_model.name} (Sisense)"
    print(f"extracted '{ir_dash.title}': {len(ir_model.tables)} tables, {len(ir_dash.widgets)} widgets")

    # 2. MAP + LOAD the Model (WS-B), then read back its GUID.
    mb = map_model.model_to_tml(ir_model, D["connection_name"], D.get("connection_fqn", ""),
                                D["catalog"], D["schema"], model_name=model_name, report=report)
    model_tmls = [yaml.safe_dump(t, sort_keys=False) for t in (*mb["tables"], mb["model"])]
    token = ts_client.get_token(T)
    base = T["base_url"]
    policy = "VALIDATE_ONLY" if dry_run else "ALL_OR_NONE"
    model_fqn = None
    for item in ts_client.import_tml(base, token, model_tmls, policy):
        code, nm, guid = ts_client.status_of(item)
        print(f"  model: {code} {nm}")
        if nm == model_name and guid:
            model_fqn = guid

    # 3. MAP content (WS-C/D) bound to the read-back Model GUID, then LOAD it.
    content = map_content.dashboard_to_tml(ir_dash, model_name, model_fqn or "PENDING",
                                           mb["model"]["model"]["columns"], report=report,
                                           faithful_layout=faithful_layout)
    board_url = ""
    if model_fqn and not dry_run:
        # the Liveboard embeds the Answers as visualizations -> import it alone, not the bare answers
        content_tmls = [yaml.safe_dump(content["liveboard"], sort_keys=False)]
        for item in ts_client.import_tml(base, token, content_tmls):
            code, nm, guid = ts_client.status_of(item)
            if guid and nm == (ir_dash.title or model_name):
                board_url = f"{base.rstrip('/')}/#/pinboard/{guid}"
            print(f"  content: {code} {nm}{('  ' + board_url) if board_url and code != 'ERROR' else ''}")
    else:
        print("  content: skipped (dry-run / no model GUID); coverage still computed")

    # 4. REPORT (WS-E) - self-contained: source, target board, model, timestamp in the header
    meta = {
        "Source": f'Sisense dashboard "{ir_dash.title}" (data model: {ds_title})',
        "Target": f"ThoughtSpot Liveboard - {board_url}" if board_url
                  else ("validated only (dry-run, not imported)" if dry_run else "not imported"),
        "Model": f"{model_name}" + (f" ({model_fqn})" if model_fqn else ""),
        "Generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    cov = out_dir / "coverage.md"
    cov.write_text(render_markdown(report, f"Coverage: {ir_dash.title}", meta=meta))
    print(f"coverage -> {cov}  {report.counts()}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sisense2ts")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--dashboard", required=True, help="Sisense dashboard oid")
    ap.add_argument("--out", default=Path("./out"), type=Path)
    ap.add_argument("--dry-run", action="store_true", help="validate TML, do not create objects")
    ap.add_argument("--faithful-layout", action="store_true",
                    help="replicate the Sisense grid placement instead of the story-flow reflow")
    args = ap.parse_args(argv)

    config = yaml.safe_load(args.config.read_text())
    try:
        run(config, args.dashboard, args.out, dry_run=args.dry_run,
            faithful_layout=args.faithful_layout)
    except NotImplementedError as e:
        print(f"[not yet implemented] {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from pathlib import Path

import yaml

from sisense2ts.extract import parse
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.ir.models import CoverageReport
from sisense2ts.load.ts_client import ThoughtSpotClient
from sisense2ts.map import content as map_content
from sisense2ts.map import model as map_model
from sisense2ts.report.coverage import render_markdown


def run(config: dict, dashboard_oid: str, out_dir: Path, dry_run: bool = False) -> None:
    report = CoverageReport()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. EXTRACT (WS-A)
    sis = SisenseClient(config["sisense"]["base_url"], config["sisense"]["token"])
    raw_dash = sis.get_dashboard(dashboard_oid)
    raw_model = sis.export_datamodel(config["sisense"]["datamodel_id"])
    ir_model = parse.parse_datamodel(raw_model)
    ir_dash = parse.parse_dashboard(raw_dash)

    # 2. MAP (WS-B / WS-C / WS-D)
    # NOTE: scripts/land_demo.py is the proven end-to-end runner today. This CLI is the
    # A7 target; it still needs dashboard_to_tml (content auto-mapping) to be finished.
    dbx = config["databricks"]
    model_bundle = map_model.model_to_tml(
        ir_model, dbx["connection_name"], dbx.get("connection_fqn", ""),
        dbx["catalog"], dbx["schema"], report=report,
    )
    content_tml = map_content.dashboard_to_tml(ir_dash, ir_model.name, report)  # TODO(C1/C2): WIP

    # 3. LOAD (WS-E)
    tmls = [yaml.safe_dump(t, sort_keys=False) for t in (*model_bundle["tables"], model_bundle["model"])]
    tmls += [yaml.safe_dump(t, sort_keys=False) for t in (*content_tml["answers"], content_tml["liveboard"])]
    ts = ThoughtSpotClient(config["thoughtspot"]["base_url"], config["thoughtspot"]["token"])
    result = ts.validate_tml(tmls) if dry_run else ts.import_tml(tmls)
    print("Import result:", result)

    # 4. REPORT (WS-E)
    (out_dir / "coverage.md").write_text(render_markdown(report, f"Coverage: {ir_dash.title}"))
    print(f"Coverage report -> {out_dir / 'coverage.md'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sisense2ts")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--dashboard", required=True, help="Sisense dashboard oid")
    ap.add_argument("--out", default=Path("./out"), type=Path)
    ap.add_argument("--dry-run", action="store_true", help="validate TML, do not create objects")
    args = ap.parse_args(argv)

    config = yaml.safe_load(args.config.read_text())
    try:
        run(config, args.dashboard, args.out, dry_run=args.dry_run)
    except NotImplementedError as e:
        print(f"[not yet implemented] {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

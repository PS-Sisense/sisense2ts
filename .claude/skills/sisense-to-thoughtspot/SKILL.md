---
name: sisense-to-thoughtspot
description: >-
  Migrate Sisense to ThoughtSpot. Use when the user has a Sisense instance —
  ElastiCube or Live data models and dashboards — and wants to recreate them in
  ThoughtSpot. Pulls the source live over the Sisense REST API (data model
  schema export + dashboards/widgets), converts the model to ThoughtSpot Table +
  Model TML and the dashboards to Answer + Liveboard TML (indicator→KPI,
  chart/*→chart, pivot2→pivot, tablewidget→table, filters→filters), translates
  JAQL formulas to ThoughtSpot formulas, imports over the v2
  metadata/tml/import API, and verifies parity by running the source JAQL
  against Sisense and /searchdata against ThoughtSpot. Translates what maps
  cleanly and flags what doesn't (custom JAQL, BloX/plugin widgets, columns not
  exposed on the model) instead of emitting confidently-wrong logic.
user-invocable: true
---

# Sisense → ThoughtSpot migration

Convert a **Sisense** data model + dashboards into a ThoughtSpot **Model** +
**Liveboard**. Pull the model schema export and the widget definitions over
REST, translate JAQL / widget types / filters, emit TML, import it, then
**verify parity** against numbers from Sisense's own JAQL engine. Translate what
maps cleanly; **flag what doesn't** (custom JAQL functions, BloX/plugin/scripted
widgets, columns the model doesn't expose) — never emit confidently-wrong logic.

> **Status — LIVE-VALIDATED (2026-06-24).** A full end-to-end migration of the
> Sisense *Sample ECommerce* model + dashboard runs against a live ThoughtSpot
> cluster. The model lands as Tables + a Model querying Databricks
> (`workspace.sisense_demo`), and a Liveboard of KPIs + charts builds on it.
> The converter is the `sisense2ts` Python package; this skill is the conductor
> over it. Layout (Phase 4), the parity gate (Phase 5), and JAQL formula
> translation (`translate_formula`) are built. Remaining gap: landing the source
> data in the warehouse so the 3-way parity gate goes truly GREEN (today the
> Databricks oracle is a synthetic sample, not the ElastiCube data).

> Read `refs/` before relying on shapes: **`refs/tml-gotchas.md`** (import API,
> auth/token minting, Databricks naming, the Answer `table` block that stops the
> "Index: 0" error), **`refs/chart-types.md`** (widget → TML chart type + the
> validate-then-template method + the exact axis configs we derived per type),
> **`refs/jaql-mapping.md`** (JAQL → ThoughtSpot formula + what's flagged).

---

## How this skill is structured

The skill is the **conductor**; the deterministic conversion lives in the
`sisense2ts` Python package at the repo root (the dir holding `config.yaml`):

- `sisense2ts/extract/` — Sisense REST client + `parse.py` (raw JSON → frozen IR)
- `sisense2ts/ir/models.py` — the FROZEN IR contract (the team's source-neutral types)
- `sisense2ts/map/` — IR → TML (`model.py`, `content.py`, `formula.py`)
- `sisense2ts/load/ts_client.py` — token minting + TML import over v2 REST
- `sisense2ts/report/coverage.py` — the coverage / flag report
- `scripts/land_demo.py` — the proven end-to-end runner (model + Liveboard)
- `sisense2ts/cli.py` — the general CLI (extract → map → import → coverage)

**Run everything from the repo root**, with the package on the path:

```sh
cd /path/to/sisense2ts          # the dir that holds config.yaml
PYTHONPATH=. .venv/bin/python scripts/land_demo.py
```

## Prerequisites

- **Sisense access** — a bearer API token (Settings → REST API). Stored in
  `config.yaml` under `sisense.token`. NOT an access-key public key (that's for
  SSO/embed).
- **ThoughtSpot access** — base_url, org, and **trusted-auth `secret_key`** in
  `config.yaml` under `thoughtspot`. The skill mints a fresh bearer token per
  run from the secret_key (`/api/rest/2.0/auth/token/full`), so token expiry is
  a non-issue. A static `token` is the fallback. See `refs/tml-gotchas.md`.
- **A ThoughtSpot connection to the warehouse holding the source data.** Parity
  only means something when ThoughtSpot reads the same data Sisense did. For
  this demo the Sample ECommerce data is landed in Databricks
  (`workspace.sisense_demo`) via `sql/databricks_sample_ecommerce.sql`; the
  connection name + fqn are in `config.yaml` under `databricks`.
- **Python 3** with deps installed in `.venv` (PyYAML; stdlib urllib otherwise).
- `config.yaml` is **gitignored — it holds every secret. Never commit it.**

## Phase 0 — Assess (optional)
Inventory the Sisense estate and score converter coverage before committing to a
conversion (which dashboards, which widget/JAQL features, the manual tail). The
dedicated `sisense-assessment` skill is the post-demo home for this; until then,
`discover` (Phase 1) + the coverage report give a first-cut readout.

## Phase 1 — Discover  ✅ working
Pull the source model and dashboards/widgets over REST and parse to the IR:

```python
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.extract import parse
sc = SisenseClient(S["base_url"], S["token"])
sm   = parse.parse_datamodel(sc.export_datamodel(model_oid))     # SourceModel
dash = parse.parse_dashboard(sc.get_dashboard(oid), sc.get_widgets(oid))
```

VERIFIED Sisense shapes (live trial): tables live at
`datasets[].schema.tables[]` (NOT `datasets[].tables`); widgets are a SEPARATE
`get_widgets(oid)` call, not embedded in the dashboard; relations reference
columns by `oid`. `parse.py` already handles all three. See its module
docstring. If `list_datamodels()` / the oid export 404s on an older build, fall
back to `GET /api/v2/datamodels/schema?title=<title>` (the title-keyed export).

## Phase 2 — Convert + import the Model  ✅ live-validated
`map.model.model_to_tml(...)` → Table TMLs (one per source table) + a Model TML
(`joins_with`, `model_tables`, `columns`). Then import and **read back the Model
GUID** — content in Phase 3 must bind to that GUID (`fqn`), never a guessed id.

```python
out = model_to_tml(sm, conn_name, conn_fqn, catalog, schema, model_name=MODEL_NAME)
# import tables + model, then capture the model's guid from the import result
```

Naming gotchas (see `refs/tml-gotchas.md`): Databricks folds table names to
lowercase (`db_table=.lower()`), physical columns use underscores (`Country_ID`,
not `Country ID`), numeric-ID columns map to ATTRIBUTE not a SUM measure.

## Phase 3 — Build content  ✅ working (hardening)
`map.content.dashboard_to_tml(dash, model_name, model_fqn, model_columns, report)`
→ `{answers: [...], liveboard: {...}}`. Each widget → an Answer on the Model;
the dashboard → a Liveboard wrapping those Answers. Bind to the **read-back**
`model_fqn` from Phase 2.

Per-widget rules that are load-bearing (all in `content.py`, detailed in
`refs/chart-types.md`):
- **Answers need a `table` block + `display_mode: CHART_MODE`** or the import
  fails with `Index: 0`.
- Drop fields whose source panel is `filters` — they are filters, not plotted columns.
- Axis configs differ by type: KPI → `y=[measure]`; SCATTER → `x/y` measures +
  first dim as `color`; COLUMN/BAR/LINE/AREA → `x=[dim]`, `y=[measures]`, extra
  dims → `color`.
- Dedupe columns (a dim used as both category and break-by appears once).
- Flag (don't emit) widgets that use a calculated JAQL formula (pending
  `translate_formula`) or reference a column the model doesn't expose.

## Phase 4 — Layout  ✅ built
By default the Liveboard is reflowed into a **progressive-disclosure story**
(`content.story_layout`): KPIs (summary) across the top, then trend (over time),
then composition (top/bottom, share) two-up, then detail tables at the bottom —
an intuitive flow rather than a copy of the source grid. (Follows the Position +
Progressive Disclosure principles from ThoughtSpot's visualization guide.)
`--faithful-layout` instead replicates the Sisense
`layout.columns[].cells[].subcells[].elements[]` grid via `content.liveboard_layout`
(proportional widths from the `TilePosition`s `parse._parse_layout` carries), for
customers who want their original arrangement preserved. Layout is the last write.

## Phase 5 — Verify parity  ✅ built (`scripts/verify_parity.py`)
Do NOT declare success on "TML validated + imported" — validating is not
rendering, and importing is not correct numbers. The gate compares, per metric,
three reference points and is GREEN only when the available ones agree:

    A  Sisense (source)    -> POST /api/datasources/{ds}/jaql      (optional leg)
    B  ThoughtSpot (target)-> POST /api/rest/2.0/searchdata
    C  warehouse (oracle)  -> Databricks SQL Statement Execution API

Because Sisense (Live) and ThoughtSpot read the SAME warehouse, **C is the
common ground truth**: the gate anchors on **B vs C** (needs no Sisense access,
so it runs even when the source token is dead) and treats the **Sisense JAQL leg
(A) as an optional third comparison** that turns on automatically when
`config.yaml` has a live `sisense.token` + `sisense.datasource`.

Engine: `sisense2ts/verify/parity.py` — pure `normalize`/`compare` core
(unit-tested in `tests/test_parity.py`) plus `thoughtspot_rows` / `databricks_rows`
/ `sisense_rows` legs. Run:

```sh
PYTHONPATH=. .venv/bin/python scripts/verify_parity.py   # exits non-zero on any RED
```

Live-validated 2026-06-24: 8/8 GREEN on Sample ECommerce (3 KPI totals + 5
breakdowns) against Databricks, Sisense leg skipped (trial token expired).
(Pattern borrowed from the Sigma migration skills' parity gate.)

## Coverage report
`report.coverage.render_markdown(report, title)` writes a per-object
AUTO/PARTIAL/MANUAL readout. Every flagged item is surfaced loudly, never
silently dropped.

## Run it

```sh
cd /path/to/sisense2ts
PYTHONPATH=. .venv/bin/python scripts/land_demo.py                 # proven E2E demo
PYTHONPATH=. .venv/bin/python -m sisense2ts.cli \                  # general CLI
    --config config.yaml --dashboard <oid> --out ./out [--dry-run]
.venv/bin/pytest -q                                                # creds-free regression
```

## Flag, never fake
Custom JAQL functions, BloX/plugin/scripted widgets, treemap/sunburst (no clean
ThoughtSpot equivalent), and any column not exposed on the Model are surfaced as
loud flags in the coverage report — never silently approximated. A widget we
cannot translate correctly is reported MANUAL, not emitted wrong.

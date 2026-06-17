# Build plan: 3 owners, deadline Friday 2026-06-26

Re-balanced from 4 to 3 contributors. Six workstreams (A extract, B model, C calc,
D content, E load/CLI, F embed) collapse into three coherent lanes. F (embed) is
deferred past the demo.

## Owners

| Owner | Lane | Workstreams | Files |
|---|---|---|---|
| **Dev A** | Pipes & Data | A (extract) + E-import + Snowflake/TS infra | `extract/*`, `load/ts_client.py` |
| **Dev B** | Semantic (long pole) | C (calc/filter) + B (model TML) | `map/formula.py`, `map/model.py` |
| **Dev C** | Content & Delivery | D (content) + E-CLI/report + QA + demo | `map/content.py`, `cli.py`, `report/*`, `tests/*` |
| **Lead (you)** | Coordinate | IR sign-off, access/creds, demo narration | `ir/models.py` (freeze) |

Dev B owns the critical path (formula translation is the long pole and B's model
formulas depend on it), so start B1 first and hardest. Dev A is critical-path early
(real fixtures + the Snowflake data layer = risk #1). Dev C integrates late.

## Milestones

- **M1 - Fri 6/19:** data model imported into ThoughtSpot, queryable against Snowflake.
  Needs: A5 (Snowflake+connection), A6 (import client), B3+B4 (Table+Model TML).
- **M2 - Tue 6/23:** one full dashboard end-to-end rendering in TS + coverage report.
- **Wed-Thu 6/24-25:** broaden to 2-3 dashboards, harden, bug-bash, demo dry-run.
- **Demo - Fri 6/26.**

## Task list (see tasks.csv for import)

### Shared / setup (Day 1)
- **S1 [Lead]** Freeze the IR contract (`ir/models.py`). Blocks finalization of B/C/D.
- **S2 [Lead]** Provision access: Sisense trial token + datamodel_id, Snowflake admin, TS trial admin.
- **S3 [Lead]** Create git remote, push scaffold, add the 3 as collaborators.
- **S4 [All]** Local setup: clone, venv, `pip install -e ".[dev]"`, `pytest` green.

### Dev A - Pipes & Data
- **A1** Sisense auth + smoke: list dashboards, pull one dashboard + datamodel via REST. [dep S2]
- **A2** Save the trial's sample exports into `tests/fixtures/` (replace synthetic). [dep A1]
- **A3** Implement `parse_datamodel` (raw -> SourceModel) against fixtures.
- **A4** Implement `parse_dashboard` + `classify_filter` (raw -> SourceDashboard).
- **A5** [infra, risk #1] Load Sisense sample data into Snowflake; create the TS Connection. [dep S2]
- **A6** Implement TS import client (`ts_client`) + auth; import a hand-written trivial TML. [dep A5]
- **A7** With Dev C: wire end-to-end import in `cli.py`; M2 dry-run. [dep B,C outputs]

### Dev B - Semantic (start now)
- **B1** Implement `translate_formula` for the supported subset; flag UNSUPPORTED as MANUAL. [dep S1] LONG POLE
- **B2** Implement filter translation (member/range/relative/top-N/exclude).
- **B3** `model_to_tml`: one Table TML per table (types + connection binding). [dep S1]
- **B4** `model_to_tml`: Model TML (model_tables, joins + cardinality default, column_ids). [dep B3]
- **B5** Calculated columns -> formulas (uses B1) + coverage items. [dep B1,B4]
- **B6** Unit tests for formula + model; remove the `xfail` in test_formula.py.

### Dev C - Content & Delivery
- **C1** `dashboard_to_tml`: widget -> Answer (CHART_TYPE_MAP, fields, measures via B1). [dep S1, soft B1]
- **C2** `dashboard_to_tml`: Liveboard TML (visualizations + layout.tiles).
- **C3** Coverage report: wire CoverageItems from all map stages; polish output.
- **C4** CLI end-to-end wiring + `--dry-run` UX + writing TML/report to `out/`. [dep A,B]
- **C5** QA: run end-to-end on the real dashboard; fix import errors via VALIDATE_ONLY.
- **C6** Demo script + a one-page known-limitations sheet. [dep M2]

## Dependency rule
B/C/D never wait on A: they build against the fixtures in `tests/fixtures/`. A swaps in
the real trial exports (A2) so the same code runs on real data. The IR is the only shared
surface and it is frozen Day 1.

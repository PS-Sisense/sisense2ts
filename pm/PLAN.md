# Build plan: 3 owners, deadline Friday 2026-06-26

Re-balanced from 4 to 3 contributors. Six workstreams (A extract, B model, C calc,
D content, E load/CLI, F embed) collapse into three coherent lanes. F (embed) is
deferred past the demo.

## Owners

| Owner | Lane | Workstreams | Files |
|---|---|---|---|
| **Dev A = you** | Pipes & Data + coordinate | A (extract) + load-import + Databricks/TS infra; plus IR sign-off, access/creds, demo. You are Databricks + GitHub admin, so the infra critical path never waits on permissions. | `extract/*`, `load/ts_client.py`, freeze `ir/models.py` |
| **Dev B** | Semantic (long pole) | C (calc/filter) + B (model TML) | `map/formula.py`, `map/model.py` |
| **Dev C** | Content & Delivery + relief valve | D (content) + CLI/report + QA + demo; absorbs overflow (e.g. take A4 parse_dashboard if A's infra runs long) | `map/content.py`, `cli.py`, `report/*`, `tests/*` |

Dev B owns the algorithmic long pole (formula translation; B's model formulas depend on
it), so start B1 first and hardest. Dev A owns the infra critical path (Databricks + TS
Connection = risk #1) and is the relief target's source of overflow. Dev C integrates late
and is the relief valve.

## Parallelism (is this actually parallel?)

Yes. Most "Depends On" entries in tasks.csv are WITHIN one person's queue (A1 -> A2 -> A3),
which is just that person's order of work, not a cross-person block. Real cross-person
blocking is tiny:

- **One sync point up front (Day 1):** freeze the IR (S1) + provision access (S2) + start
  the Databricks load (A5). After that, all three lanes run independently for days against
  the fixtures in `tests/fixtures/`.
- **One convergence at the end (Day 4-5):** the CLI (C4/A7) wires together the import
  client (A6), the Model TML (B4), and the Liveboard (C2). That is integration, by design.
- **Soft handoff:** C needs B1 (translate_formula) for measures. C builds dimensions +
  chart types first and drops B1 in when it lands (~Day 2). Not a hard block.

The only true critical path is **A5 (Databricks load + ThoughtSpot Connection)**. It gates
M1 and infra always slips, so Dev A does it Day 1 before touching code. Days 2-4 are three
independent lanes.

## Milestones

- **M1 - Fri 6/19:** data model imported into ThoughtSpot, queryable against Databricks.
  Needs: A5 (Databricks+connection), A6 (import client), B3+B4 (Table+Model TML).
- **M2 - Tue 6/23:** one full dashboard end-to-end rendering in TS + coverage report.
- **Wed-Thu 6/24-25:** broaden to 2-3 dashboards, harden, bug-bash, demo dry-run.
- **Demo - Fri 6/26.**

## Task list (see tasks.csv for import)

### Shared / setup (Day 1)
- **S1 [Lead]** Freeze the IR contract (`ir/models.py`). Blocks finalization of B/C/D.
- **S2 [Lead]** Provision access: Sisense trial token + datamodel_id, Databricks admin, TS trial admin.
- **S3 [Lead]** Create git remote, push scaffold, add the 3 as collaborators.
- **S4 [All]** Local setup: clone, venv, `pip install -e ".[dev]"`, `pytest` green.

### Dev A - Pipes & Data
- **A1** Sisense auth + smoke: list dashboards, pull one dashboard + datamodel via REST. [dep S2]
- **A2** Save the trial's sample exports into `tests/fixtures/` (replace synthetic). [dep A1]
- **A3** Implement `parse_datamodel` (raw -> SourceModel) against fixtures.
- **A4** Implement `parse_dashboard` + `classify_filter` (raw -> SourceDashboard).
- **A5** [infra, risk #1] Load Sisense sample data into Databricks; create the TS Connection. [dep S2]
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

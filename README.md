# sisense2ts

Convert Sisense BI assets (data model + dashboards) into ThoughtSpot TML, import them
into a ThoughtSpot instance, and report what converted automatically versus what needs
a human. Built to accelerate Sisense to ThoughtSpot migrations in Professional Services.

## The target (demo, Friday June 26)

> Run one command against a dashboard in the Sisense trial. The tool extracts the data
> model and dashboard over REST, generates TML, imports it into the ThoughtSpot trial,
> and the converted **Model + Liveboard render with real data**, plus a **coverage
> report** of what converted automatically versus what needs manual work.

Embedded (Visual Embed SDK) is deliberately **deferred** to after the demo. Sisense is
embedded-first, so that re-platform is the real follow-on project, but it is not in this
sprint.

## Quickstart

```bash
cd sisense2ts
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                       # baseline must be green
cp config.example.yaml config.yaml   # then fill in trial creds (gitignored)
python -m sisense2ts.cli --config config.yaml --dashboard <oid> --out ./out --dry-run
```

## Architecture

```
extract/  ->  ir/  ->  map/  ->  load/ + report/
(Sisense)   (the      (TML       (ThoughtSpot import
            contract)  builders)  + coverage report)
```

The whole pipeline is decoupled by one thing: the **frozen IR** in
[`sisense2ts/ir/models.py`](sisense2ts/ir/models.py). Extraction turns Sisense JSON into
IR; mapping turns IR into TML. Nothing downstream of `extract/` ever sees raw Sisense
JSON. This is what lets four people work in parallel without blocking each other, and
what lets us add Power BI / Tableau later by writing a new `extract/` only.

**Rule: do not change the IR shapes without lead sign-off.** Everyone codes against them.

## Who owns what (4 contributors)

| Owner | Workstream | Files | Starts on |
|---|---|---|---|
| **P1** (pipes) | **A. Extract** then **E. Load/CLI** | `extract/sisense_client.py`, `extract/parse.py`, `load/ts_client.py`, `cli.py` | Sisense REST spike + Snowflake/TS setup |
| **P2** | **B. Data model** | `map/model.py` | Table + Model TML from fixtures |
| **P3** (strongest) | **C. Calc + filter** | `map/formula.py` | `translate_formula` from fixtures (isolated, test-first) |
| **P4** | **D. Content** | `map/content.py` | widget -> Answer, dashboard -> Liveboard |
| **Lead** | IR freeze, unblock, Snowflake/TS access, demo | - | sign off `ir/models.py` |

P3 (calc translation) is the long pole and is pure and isolated, so start it now and
hardest. P1 is critical-path early (real fixtures) and integrates everyone late.

## Milestones

| Day | Milestone |
|---|---|
| Wed 6/17 | Scaffold + **IR frozen** + owners assigned + Snowflake/TS connection task kicked off |
| Thu 6/18 | Spike done: auth to trial, one real dashboard + datamodel pulled into `tests/fixtures/`, trivial TML import confirmed |
| Fri 6/19 | **M1: model lands** -- data model imported into TS, queryable against Snowflake |
| Mon 6/22 | Simple measures + filters translated; first generated Liveboard |
| Tue 6/23 | **M2: one dashboard end-to-end** rendering in TS + coverage report v1 |
| Wed 6/24 | Broaden to 2-3 dashboards; harden chart-type map; CLI polish |
| Thu 6/25 | Bug-bash, validation, full demo dry-run, freeze |
| Fri 6/26 | **Demo + handoff** |

## Day-1 checklist

- **Lead:** review and freeze `ir/models.py`. Confirm Snowflake account + ThoughtSpot
  trial admin access. Decide the demo dashboard(s).
- **P1:** authenticate to the Sisense trial; pull one dashboard (`get_dashboard`) and the
  datamodel (`export_datamodel`); save both into `tests/fixtures/` (overwrite samples).
  Load that dashboard's data into Snowflake and create the ThoughtSpot Connection.
  Confirm a hand-written trivial TML imports via `load/ts_client.py`.
- **P2/P3/P4:** build against the fixtures immediately. Do not wait for live extraction.

## Scope

**In:** model (tables/columns/joins) to Table+Model TML; common JAQL subset (dimensions,
agg measures, ~20 functions, member/range filters); widget to Answer (chart-type map);
dashboard to Liveboard; import + coverage report + CLI.

**Stretch:** theme to CSS variables; Visual Embed sample app.

**Out (flag in coverage report, do not build):** time-intelligence / RANK / measured-value
/ R functions; BloX, custom JS, plugins; multi-tenant Orgs/ABAC data security; ElastiCube
data movement; pixel-perfect layout; programmatic/runtime dashboard composition.

## Project management

Tasks for the 3-person sprint are in [`pm/PLAN.md`](pm/PLAN.md). Pick ONE source of truth
to avoid double-maintenance:

- **ClickUp (the visual board we use):** import [`pm/clickup_tasks.csv`](pm/clickup_tasks.csv).
  It has real due dates, owners, priorities, and a Workstream field to group/color by. In
  ClickUp: make a List, Import > CSV, map the columns. Then view it as a Board grouped by
  Assignee plus a Calendar/Timeline against the 2026-06-26 deadline.
- **GitHub Issues (code-linked, already created):** 21 issues + the `Demo 2026-06-26`
  milestone + `ws:*` labels live at github.com/anujseth2/sisense2ts/issues (created via
  [`pm/create_github_issues.sh`](pm/create_github_issues.sh)). Use these instead if you want
  tasks tied to commits and PRs. `pm/tasks.csv` is the generic-importer version.

## Sample assets

- `tests/fixtures/datamodel_sample.json` + `dashboard_sample.json` -- minimal, for unit tests.
- `tests/fixtures/dashboard_rich.json` -- a broader dashboard (column/line/pie/indicator/
  table widgets, all filter kinds, a translatable calc and one unsupported YoY-growth calc)
  to develop and demo against before live data is wired.
- **Real assets:** Dev A exports the trial's built-in sample dashboards (Sample ECommerce /
  Sample Healthcare) on Day 1 (tasks A1/A2) and drops them here, replacing the synthetic ones.

## Conventions / gotchas

- **Target Model TML, not Worksheet TML.** Worksheets are deprecated and their import is
  blocked on current ThoughtSpot versions.
- **The data must live in Snowflake** and be reachable by a ThoughtSpot Connection before
  an import will render. This is risk #1; P1 + lead own it on Day 1.
- **Never commit tokens.** `config.yaml` and `*.token` are gitignored.
- Generate TML with the `thoughtspot_tml` library; do not hand-write YAML.
- Import all related objects (connection/tables/model/answers/liveboard) in one
  `tml/import` call so references resolve.
- Sisense `subtype` strings drift by version/plugin; derive them from real exports.

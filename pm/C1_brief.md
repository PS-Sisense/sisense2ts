# C1/C2 brief — `dashboard_to_tml` (Apratim / Dev C)

## Goal
Implement `dashboard_to_tml` in [`sisense2ts/map/content.py`](../sisense2ts/map/content.py):
take a parsed Sisense dashboard (IR `SourceDashboard` with its widgets) plus the converted
Model, and **auto-generate** the Answer + Liveboard TML — one Answer per widget, assembled
into a Liveboard. Today the live Liveboard uses a hand-picked set; your job is to derive it
from the real widgets.

You are **not** starting cold. `answer_tml` and `liveboard_tml` are already implemented and
proven live (they built the 10-tile Liveboard). `dashboard_to_tml` mostly orchestrates them.

## What you have to work against (in the repo)
- **IR** (`ir/models.py`): `SourceDashboard.widgets`, `SourceWidget(wtype, subtype, fields, filters)`,
  `Field(kind=dimension|measure, dim, agg, title, formula)`, `SourceFilter`, `TilePosition`.
- **Builders + map** in `map/content.py`: `answer_tml(...)`, `liveboard_tml(...)`,
  `CHART_TYPE_MAP` + `widget_chart_type()` (Sisense type → TML chart type).
- **Import/validate**: `load/ts_client.py` (`get_token`, `import_tml`, `status_of`).
- **Fixtures**: `tests/fixtures/real_widgets.json` (the real 9 widgets, gitignored — regenerate via A1),
  `dashboard_rich.json` (committed: column/line/pie/indicator/table, all filter kinds).
- **The model to bind to**: name `Sample ECommerce (Sisense)` + its fqn (from the Model import).

## Suggested signature
`dashboard_to_tml(dash, model_name, model_fqn, report=None) -> {"answers": [...], "liveboard": {...}}`
(adjust the existing stub; `cli.py` calls it.)

## The mapping (the real work)
For each `SourceWidget`:
1. `chart_type = widget_chart_type(widget.wtype)` (indicator → KPI, chart/pie → PIE, etc.).
2. Build `search_query` + ordered `columns` from `widget.fields`:
   - dimensions → `[<model column name>]`; measures (have `agg`) → `[<model column name>]`.
   - **Map the Sisense field `dim` to the MODEL's column display name** — answers reference
     model columns (e.g. `Country`, `Revenue`), not Sisense dims like `[Commerce.Revenue]`.
     Build a lookup from the converted model's columns (the part after the dot in the dim).
   - A measure surfaces in the answer as `Total <col>` (e.g. `Total Revenue`) — use that in
     `columns`/`answer_columns`, while the `search_query` uses `[Revenue]`.
3. `answer_tml(title, model_name, model_fqn, search_query, columns, chart_type)`.
4. Assemble all answers via `liveboard_tml(dash.title, answers)`.

## Method (the standing rule)
**Validate every answer before assembling** (`import_tml(..., "VALIDATE_ONLY")`); skip + flag
any that fail. For a new chart type, template off a real export from an accessible liveboard;
if a type appears in none of them, ask the lead for the TML. (This is exactly how KPI got solved.)

## In scope / out of scope
- **In**: simple-aggregation widgets (dimension(s) + agg measure) → COLUMN/BAR/LINE/PIE/KPI;
  dashboard + widget filters as runtime filters where straightforward; layout tiles from `TilePosition`.
- **Out → flag MANUAL in the coverage report**: formula-based measures until B1
  (`translate_formula`) lands; scatter/bubble, BloX, custom-JS widgets; exotic subtypes;
  pixel-perfect layout.

## Definition of done
- `dashboard_to_tml` on `real_widgets.json` (or `dashboard_rich.json`) returns answers + a
  Liveboard that **validates and imports**; widgets it can't map are skipped and logged as
  `CoverageItem`s (MANUAL) rather than breaking the import.
- A unit test on `dashboard_rich.json` asserting the expected answer count + chart types.
- `cli.py` then wires extract → model → `dashboard_to_tml` → import (that finishes A7).

## Gotchas
- Answers bind to **model column names**, not Sisense dims — the dim→column lookup is the crux.
- Indicator widgets carry gauge-junk jaql items (`formula: "0"`) — `parse` already drops them; don't re-add.
- KPI needs `axis_configs` with the measure under `y` — `answer_tml` already handles it.
- Re-running creates new objects unless you set `guid:` on the Liveboard to update in place.

## Running it with Claude (per CONTRIBUTING.md)
> "Implement `dashboard_to_tml` in `map/content.py` per `pm/C1_brief.md`: map each IR widget
> to an Answer via `answer_tml`, bind to model columns, validate each before assembling,
> skip+flag what can't map. Make it import on `dashboard_rich.json`."

Then comment + flip status with `python pm/clickup_task.py`.

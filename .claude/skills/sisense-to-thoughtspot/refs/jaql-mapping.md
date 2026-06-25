# JAQL → ThoughtSpot formula mapping (and what gets flagged)

Source: `map/formula.py`. Strategy: **deterministically translate the common
subset; flag everything else MANUAL with the original Sisense formula preserved
verbatim.** Do not chase the long tail (time-intelligence, RANK/ORDERING,
measured-value scoping, R). Flag, never fake.

## Simple aggregations — `translate_simple_agg(agg)` ✅ implemented

A JAQL item with a plain `agg` (no formula) maps to a TML aggregation keyword:

| JAQL `agg`        | TML aggregation   | Coverage |
|-------------------|-------------------|----------|
| `sum`             | `SUM`             | AUTO |
| `avg`             | `AVERAGE`         | AUTO |
| `count`           | `COUNT`           | AUTO |
| `min` / `max`     | `MIN` / `MAX`     | AUTO |
| `stdev` / `var`   | `STD_DEVIATION` / `VARIANCE` | AUTO |
| `countduplicates` | `COUNT`           | PARTIAL (approx of DupCount) |
| `median`, `stdevp`, `varp`, `mode` | — | MANUAL (no clean TML agg) |

## Calculated formulas — `translate_formula(formula)` 🔜 WIP (B1 / Pooja)

Not yet implemented (`raise NotImplementedError`). When built, the plan:

1. Resolve `context` placeholders (e.g. `[users]` → its dim/agg) to a flat
   expression over real column references.
2. Tokenize the formula; map function names via `FUNCTION_MAP`.
3. Any token in `UNSUPPORTED` (or unknown) → **MANUAL**, `expr=None`, note the
   offending function, keep `source`.
4. Plain arithmetic + supported funcs → **AUTO**.
5. `case`/conditional or `countduplicates` → **PARTIAL** with a note.

**Supported function subset** (`FUNCTION_MAP`, confident 1:1 only): `sum avg
count min max abs round(→round) ceiling(→ceil) floor power(→pow) sqrt exp mod
if isnull(→is_null)`.

**Explicitly unsupported → MANUAL** (`UNSUPPORTED`): `rank ordering rsum prev
next all now past* growth* diff* ytd*/mtd*/qtd*/wtd* rpsum rpavg percentile
quartile correl covar slope rdouble rint`. These are time-intelligence / window
/ statistical functions with no confident TML 1:1.

## Date dimensions carry a `level` (granularity) — current IR gap

A JAQL date dimension item looks like
`{ "jaql": { "dim": "[Commerce.Date]", "level": "months" } }`. The `level`
(`days`/`weeks`/`months`/`quarters`/`years`) is the time bucketing the widget
plots by. Our IR `Field` does NOT capture `level` today, so a "Revenue by Month"
trend loses its bucket and falls back to raw date. Additive IR fix: add
`level: Optional[str]` to `Field`, set it in `parse._jaql_to_field`, and emit the
matching ThoughtSpot date bucket in the search query. (Cross-checked against the
sisense-to-sigma `jaql-mapping.md`, which documents the same item shape.)

## Where formulas get flagged in the pipeline

`map/content.dashboard_to_tml` flags a widget **MANUAL** (and does not emit it)
when any of its fields carries a JAQL formula — calculated measures wait on
`translate_formula`. Until B1 lands, those widgets are surfaced in the coverage
report, never silently dropped or faked. Wiring `translate_formula` into
`dashboard_to_tml` is what recovers the flagged formula indicators.

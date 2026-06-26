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

## Calculated formulas — `translate_formula(formula)` ✅ implemented (B1 / Pooja)

Implemented in `map/formula.py`. Full function table, caveats, and examples:
[`sisense-formula-translation.md`](sisense-formula-translation.md). The logic:

1. Resolve `context` placeholders (e.g. `[users]` → its dim/agg) to a flat
   expression over real column references (nested formulas recurse).
2. Map function names via `FUNCTION_MAP`.
3. Any token in `UNSUPPORTED` (or unknown) → **MANUAL**, `expr=None`, note the
   offending function, keep `source`.
4. Plain arithmetic + supported funcs → **AUTO**.
5. `case`/conditional or `countduplicates` → **PARTIAL** with a note.

**Supported function subset** (`FUNCTION_MAP`, confident 1:1 only): `sum avg
average count min max median abs round ceiling(→ceil) floor power(→pow) sqrt exp
mod ln log10 sign stdev(→stddev) var(→variance) if isnull ifnull`. (TS spells it
`isnull`, not `is_null`.) Full table: [`sisense-formula-translation.md`](sisense-formula-translation.md).

**Explicitly unsupported → MANUAL** (`UNSUPPORTED`): `rank ordering rsum prev
next all now past* growth* diff* ytd*/mtd*/qtd*/wtd* rpsum rpavg percentile
quartile correl covar slope rdouble rint`. These are time-intelligence / window
/ statistical functions with no confident TML 1:1.

## Date dimensions carry a `level` (granularity) — H2 ✅ implemented

A JAQL date dimension item looks like
`{ "jaql": { "dim": "[Commerce.Date]", "level": "months" } }`. The `level` is the
time grain the widget plots by. The IR `Field` now carries it
(`level: Optional[str]`, additive — set in `parse._jaql_to_field`), and
`map/content.py` emits the matching **ThoughtSpot date keyword** as its own bracketed
token right after the date column in the search query. Two flavours:

**Bucket** — continuous granularity, keeps chronology (a time series). `DATE_BUCKET_MAP`:

| Sisense `level` | TS token | so "Revenue Trend" emits |
|---|---|---|
| `days` | `[daily]` | `[Order Date] [daily] [Revenue]` |
| `weeks` | `[weekly]` | … |
| `months` | `[monthly]` | `[Order Date] [monthly] [Revenue]` (was `[Order Date] [Revenue]`) |
| `quarters` | `[quarterly]` | … |
| `years` | `[yearly]` | … |
| `hours` | `[hourly]` | (DateTime only) |

**Date part** — cyclic extraction, collapses across periods (all Januaries together)
for seasonality. `DATE_PART_MAP`:

| Sisense `level` (+ aliases) | TS token |
|---|---|
| `dayofweek` / `weekday` | `[day of week]` |
| `dayofmonth` / `dayinmonth` | `[day of month]` |
| `dayofquarter` | `[day of quarter]` |
| `dayofyear` | `[day of year]` |
| `monthofyear` | `[month of year]` |
| `weekofyear` | `[week of year]` |
| `hourofday` | `[hour of day]` |

The keyword is a **search modifier**, not an extra answer column. A level with no
mapping (e.g. an unrecognised spelling) emits no token and the widget is flagged
**PARTIAL** ("emitted ungrouped"), never silently dropped or faked. Sisense `level`
spellings vary by version, so common aliases are included — confirm the exact strings
against real exports. Keywords confirmed against the
[Keyword reference](https://docs.thoughtspot.com/cloud/26.6.0.cl/keywords) and
[Time series analysis](https://docs.thoughtspot.com/cloud/latest/search-time) docs.

## Where formulas get flagged in the pipeline

`map/content.dashboard_to_tml` flags a widget **MANUAL** (and does not emit it)
when any of its fields carries a JAQL formula — calculated measures wait on
`translate_formula`. Until B1 lands, those widgets are surfaced in the coverage
report, never silently dropped or faked. Wiring `translate_formula` into
`dashboard_to_tml` is what recovers the flagged formula indicators.

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
`map/content.py` (`date_bucket_suffix`) emits the grain as a **suffix attached to the
date column token**, NOT a standalone keyword.

**Bucket** — continuous granularity, keeps chronology (a time series). `DATE_BUCKET_MAP`:

| Sisense `level` | TS column suffix | so "Revenue Trend" emits |
|---|---|---|
| `days` | `.DAILY` | `[Order Date].DAILY [Revenue]` |
| `weeks` | `.WEEKLY` | … |
| `months` | `.MONTHLY` | `[Order Date].MONTHLY [Revenue]` (was `[Order Date] [Revenue]`) |
| `quarters` | `.QUARTERLY` | … |
| `years` | `.YEARLY` | … |
| `hours` | `.HOURLY` | (DateTime only) |

⚠️ **Live-validated:** the suffix attaches to the column (`[Order Date].MONTHLY`). A
standalone `[monthly]` token is read as a missing column and **400s** — do not emit it.

**Date part** — cyclic extraction (day-of-week, month-of-year, etc., in
`DATE_PART_LEVELS`) collapses across periods for seasonality. Its ThoughtSpot search
syntax is **not yet verified**, so these levels emit no suffix and the widget is flagged
**PARTIAL** ("date level not applied (cyclic part / unmapped)") — never guessed at.

The suffix is a **search modifier**, not an extra answer column. Any unmapped level
(unrecognised spelling, or a cyclic part) emits no suffix and is flagged PARTIAL, never
silently dropped or faked. Sisense `level` spellings vary by version — confirm exact
strings against real exports. Buckets confirmed against the
[Keyword reference](https://docs.thoughtspot.com/cloud/26.6.0.cl/keywords) and
[Time series analysis](https://docs.thoughtspot.com/cloud/latest/search-time) docs.

## Filters carry a per-attribute top-N rank — subquery filter ✅ implemented

A JAQL filter can rank one attribute by a measure:
`{ "dim": "[Category.Category]", "filter": { "top": 3, "by": { "dim": "[Commerce.Revenue]", "agg": "sum" } } }`
— i.e. "keep the **top 3 Categories by Revenue**", then chart the rest normally (e.g.
Revenue by Age Range, stacked by Category). The IR captures it as
`SourceFilter(TOP_N, dim, values=[n], raw={top, by})`.

⚠️ **Plain search `top N` is a ROW cap, not a per-attribute rank.** Every variant
(`top 3 [Revenue] [Category] [Age Range]`, ranked dim first, trailing, NL) returns 3 total
rows — empirically verified. It is faithful ONLY when the ranked attribute is the **single**
plotted dimension.

`dashboard_to_tml` (pure, no network) emits the rank in two tiers:

| Case | Output | Coverage |
|---|---|---|
| Single plotted dim | leading `top N` (the row cap = exactly the top-N members) | AUTO |
| Ranked dim is one of ≥2 plotted dims | a **subquery filter** (below) | AUTO |
| Ranked column / rank measure didn't map | not applied | PARTIAL |

For the multi-dim case, the faithful, **dynamic** form is a subquery that ranks the attribute
globally and keeps it as a plotted column so the other dimensions retain their full breakdown:

```
[Age Range] [Revenue] [Category] [Category] in ( [Category] top 3 [Category] sort by [Revenue] )
```

Live-validated: this returns exactly the global top-3 Categories by Revenue
(Electronics/Home/Apparel) across all Age Ranges, and re-ranks with the data (no convert-time
snapshot, no resolver). It beats the earlier approaches that all fail here: plain `top N` caps
rows; `[Category] = '…'` and `[Category] in '…'` drop the column (killing the stack/break-by);
`top N by [m] for each [dim]` is a *windowed* (per-group) rank, a different analytic than a
global dimension filter. Requires ThoughtSpot's in-subquery search (modern clusters).

## Where formulas get flagged in the pipeline

`map/content.dashboard_to_tml` flags a widget **MANUAL** (and does not emit it)
when any of its fields carries a JAQL formula — calculated measures wait on
`translate_formula`. Until B1 lands, those widgets are surfaced in the coverage
report, never silently dropped or faked. Wiring `translate_formula` into
`dashboard_to_tml` is what recovers the flagged formula indicators.

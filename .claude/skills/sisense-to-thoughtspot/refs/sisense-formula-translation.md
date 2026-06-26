<!-- currency: sisense — 2026-06-26 (every mapping verified against the COMPLETE ThoughtSpot 26.6.0 formula reference: operators, aggregate, conversion, date, mixed, number, text, and connections-passthrough functions. All target names confirmed; no code changes required on this pass.) -->

# Sisense → ThoughtSpot Formula Translation Reference

Reference for converting **Sisense JAQL formula expressions** to **ThoughtSpot TML formula
expressions**. Modeled on the Tableau→ThoughtSpot translation reference in
`thoughtspot/thoughtspot-agent-skills`. Implemented by [`map/formula.py`](../../../../sisense2ts/map/formula.py);
pairs with [`jaql-mapping.md`](jaql-mapping.md) (JAQL item/agg/level mapping) and
[`tml-gotchas.md`](tml-gotchas.md).

**Strategy (same as the Tableau reference): deterministically translate the confident common
subset; flag everything else MANUAL with the original Sisense formula preserved verbatim.
Flag, never fake.** A plausible-but-wrong formula is worse than an honest MANUAL flag in the
coverage report.

Sources: Sisense function catalog
<https://docs.sisense.com/win/SisenseWin/introduction-to-forumlas.htm> · ThoughtSpot 26.6.0
formula reference <https://docs.thoughtspot.com/cloud/26.6.0.cl/formula-reference> (incl. its
Number functions section). All names — ThoughtSpot targets and Sisense sources — are
confirmed against their docs; there are no remaining `verify` items. See **Behavioral
differences** below for `round`, the one mapping where a blind rename gives wrong numbers.

---

## How a Sisense formula reaches the translator

A Sisense JAQL calculation is an **expression string** plus a **context** map. Context keys
are referenced inside the expression in `[brackets]`; each entry resolves to a column
(`dim`) with an optional aggregation (`agg`), or to a nested formula (recurse):

```jsonc
{
  "formula": "sum([rev]) / count([ord])",
  "context": {
    "rev": { "dim": "[Orders.Revenue]",  "agg": "sum" },
    "ord": { "dim": "[Orders.Order ID]", "agg": "count" }
  }
}
```

Translation: resolve each `[key]` to its column ref, map the JAQL functions to TML
functions, and classify the result `AUTO` / `PARTIAL` / `MANUAL`.

- A `{dim, agg}` placeholder already **wrapped** by an aggregation in the expression
  (`sum([rev])`) → substitute the bare column `[Revenue]`; the wrapping function is mapped
  in the function pass.
- A `{dim, agg}` placeholder appearing **bare** (`[rev] / [ord]`) → emit `agg([Column])`
  using the context `agg`.
- Sisense `dim` `[Table.Column]` → TML column ref `[Column]` (the `Table.` qualifier is
  dropped; display name, spaces and all, is kept in brackets).
- Context keys may be bracketed (`"[rev]"`) or bare (`"rev"`); both resolve to `[rev]` in
  the expression.

---

## Function mapping

Columns: **Sisense** function · **ThoughtSpot** equivalent · **Coverage** · **Notes**.
Coverage values match `map/formula.py`: `AUTO` (clean 1:1), `PARTIAL` (maps with a caveat
worth review), `MANUAL` (not auto-translated — flagged for a human, `expr=None`).

### Aggregation

| Sisense | ThoughtSpot | Coverage | Notes |
|---|---|---|---|
| `Sum(x)`        | `sum(x)`            | AUTO | |
| `Avg(x)` / `Average(x)` | `average(x)` | AUTO | |
| `Count(x)`      | `count(x)`          | AUTO | |
| `Min(x)` / `Max(x)` | `min(x)` / `max(x)` | AUTO | |
| `DupCount(x)` / `countduplicates` | `count(x)` | PARTIAL | Sisense `DupCount` counts non-distinct values; `count` is the closest TML approximation (TS's distinct count is `unique_count`, the opposite). Review. |
| `Median(x)`     | `median(x)`         | AUTO | Confirmed in TS 26.6.0 as a formula function. (Note: as a *simple* JAQL agg it is still MANUAL — there is no `MEDIAN` model aggregation enum; see the surface note below.) |
| `Mode(x)`       | —                   | MANUAL | No TML equivalent. |
| `Largest(x, n)` / `Smallest(x, n)` | — | MANUAL | Top-N selection has no clean formula form; model as a filter/RANK instead. |

> **Model-column aggregation vs. formula function.** When a *simple* JAQL `agg` (no formula)
> drives a Model column, it maps to the TML **aggregation enum** (uppercase): `SUM`,
> `AVERAGE`, `COUNT`, `MIN`, `MAX`, `STD_DEVIATION`, `VARIANCE` — see `AGG_MAP` /
> `translate_simple_agg` and `jaql-mapping.md`. Inside a **formula expression** the same
> operation is a lowercase function call: `sum([x])`. Don't conflate the two surfaces.

### Mathematical

| Sisense | ThoughtSpot | Coverage | Notes |
|---|---|---|---|
| `Abs(x)`        | `abs(x)`            | AUTO | |
| `Round(x)`      | `round(x)`          | AUTO | Single-arg rounds to integer in both. |
| `Round(x, n)`   | `round(x, 10^-n)`   | PARTIAL | **Semantics differ.** TS's 2nd arg is a rounding *increment* (`round(x, .01)` = 2 decimals), Sisense's is a decimal-place *count* (`Round(x, 2)`). The translator flags 2-arg `round` PARTIAL; convert the arg by hand (`n` places → `10^-n`). See Behavioral differences. |
| `Ceiling(x)`    | `ceil(x)`           | AUTO | Name change. |
| `Floor(x)`      | `floor(x)`          | AUTO | |
| `Power(x, y)`   | `pow(x, y)`         | AUTO | Name change. |
| `Sqrt(x)`       | `sqrt(x)`           | AUTO | |
| `Exp(x)`        | `exp(x)`            | AUTO | |
| `Mod(x, y)`     | `mod(x, y)`         | AUTO | |
| `Log(x)`        | `ln(x)`             | AUTO | Sisense `Log` is the **natural** logarithm (confirmed in the Sisense math-functions doc; Sisense has no separate `Ln`). |
| `Log10(x)`      | `log10(x)`          | AUTO | Base-10. |
| `Sign(x)`       | `sign(x)`           | AUTO | |
| `Int(x)`        | `floor(x)`          | PARTIAL | Truncation toward zero vs. floor differs for negatives; review. |

### Logical / conditional

| Sisense | ThoughtSpot | Coverage | Notes |
|---|---|---|---|
| `If(cond, a, b)` | `if (cond) then a else b` | AUTO | ThoughtSpot uses `if … then … else`, not a 3-arg function. |
| `Case … When … Then … Else … End` | nested `if (…) then … else …` | PARTIAL | Mechanical but not 1:1; review the generated nesting. |
| `IsNull(x)`     | `isnull(x)`         | AUTO | TS spells it `isnull` — **not** `is_null`. |
| `IfNull(x, y)`  | `ifnull(x, y)`      | AUTO | TS has a native `ifnull` operator (confirmed 26.6.0); 1:1, no compose needed. |
| arithmetic `a / b` (risk of ÷0) | `if (b = 0) then null else a / b` | PARTIAL | Sisense returns null on ÷0. Note TS `safe_divide(a, b)` returns **0** (not null) on ÷0, so it does not match Sisense exactly — use the explicit `if` for null parity. |
| `Contains` / `StartsWith` / `EndsWith` | `contains(x, y)` / `strpos(x, y) = 1` / `right(x, n) = y` | MANUAL | In Sisense these are **filter** predicates, not measure functions — route via filter mapping. TS does have the building blocks (`contains`, `strpos`, `left`, `right`); there is no `startswith`/`endswith`, so compose with `strpos … = 1`. |

### Statistical

| Sisense | ThoughtSpot | Coverage | Notes |
|---|---|---|---|
| `Stdev(x)`      | `stddev(x)`         | AUTO | Sample standard deviation (confirmed 26.6.0). |
| `Var(x)`        | `variance(x)`       | AUTO | Sample variance (confirmed 26.6.0). |
| `StdevP(x)` / `VarP(x)` | —          | MANUAL | Population variants have no confirmed TML 1:1. |
| `Percentile(x, p)` / `Quartile(x, q)` | `percentile(measure, N, 'asc')` | MANUAL | TS signature is `percentile(x, N, 'asc'|'desc')` where **N is 0–100** and a sort direction is required. Sisense `Percentile` takes a 0–1 fraction (so `0.99` → `99`) and `Quartile` q=0–4 (→ `q*25`). Kept MANUAL: needs an arg-scale rewrite **and** an added sort arg — a wrong percentile is worse than a flag. |
| `Correl` / `Covar` / `Slope` | —       | MANUAL | Regression/correlation — out of scope. |
| `RDouble` / `RInt` (R integration) | — | MANUAL | R execution does not port. |

### Time intelligence — **NOT translated** (always MANUAL)

Sisense time-intelligence has no deterministic 1:1 with TML formulas; it depends on a date
dimension and a period grain that must be re-modeled by hand in ThoughtSpot. All of the
following are flagged MANUAL with the original formula preserved:

| Sisense | Notes |
|---|---|
| `YTDSum` `QTDSum` `MTDSum` `WTDSum`, `YTDAvg` `QTDAvg` `MTDAvg` | Period-to-date — rebuild with a ThoughtSpot cumulative/period measure. |
| `PastYear` `PastQuarter` `PastMonth` `PastWeek` `PastDay` | Prior-period reference. |
| `Growth` `GrowthRate` `DiffPastYear` `DiffPastMonth` | Trend / delta. |
| `YDiff` `QDiff` `MDiff` `DDiff` `HDiff` `MnDiff` `SDiff` | Period-difference family. |
| `Prev` `Next` | Row/period offset. |
| `RSum` `RPSum` `RPAvg` | Running / running-period aggregations. |
| `Rank` `Ordering` | Window ranking — model via a RANK/ORDERING measure by hand. |
| `All` `Now` | Scope/context functions. |

> **Manual-rebuild path exists.** ThoughtSpot's date function family (`add_days`,
> `add_months`, `add_years`, `diff_days`/`diff_months`/`diff_quarters`/`diff_years`,
> `start_of_week`/`start_of_month`/`start_of_quarter`/`start_of_year`, `today`, `now`) plus
> the `cumulative_*` / `moving_*` aggregates give a consultant the building blocks to
> re-create most of these by hand. They are still flagged MANUAL here because there is no
> *deterministic* 1:1 — the rebuild needs the date dimension and grain in context.

---

## Operators

| Sisense | ThoughtSpot | Coverage | Notes |
|---|---|---|---|
| `+` `-` `*` `/` | `+` `-` `*` `/` | AUTO | Wrap `/` against ÷0 (see logical table). |
| `=` `>` `<` `>=` `<=` | same | AUTO | Spaces required around operators in TML. |
| `!=` / `<>`     | `!=`               | AUTO | |
| `between`       | `a >= lo and a <= hi` | AUTO | Compose. |
| `AND` `OR` `NOT` | `and` `or` `not`  | AUTO | Lowercase keywords in TML. |

---

## Behavioral differences (translate, but the numbers can diverge)

These map syntactically yet behave differently — the analogue of the Tableau reference's
`DATEDIFF` arg-order / `LEFT` indexing caveats. Translate with care and review.

- **`round` second argument.** TS `round(x, n)` rounds to the nearest *increment* `n`
  (`round(35.65, 10) = 40`, `round(48.67, .1) = 48.7`). Sisense `Round(x, n)` rounds to `n`
  *decimal places*. So Sisense `Round(x, 2)` → TS `round(x, .01)`, **not** `round(x, 2)`.
  The translator flags any 2-arg `round` PARTIAL rather than emit a wrong number.
- **Division by zero.** Sisense `a / b` → null when `b = 0`. TS raw `/` may error and
  TS `safe_divide` returns **0**. For null parity emit `if ( b = 0 ) then null else a / b`.
- **`Int` vs `floor`.** Sisense `Int` truncates toward zero; `floor` rounds down. They
  differ for negatives (`Int(-1.5) = -1`, `floor(-1.5) = -2`).

## ThoughtSpot TML syntax rules (target conventions)

- Column references use square brackets: `[Revenue]`, optionally table-qualified
  `[Orders::Revenue]`. The Sisense `[Table.Column]` qualifier is dropped to the column name.
- Conditionals are `if ( cond ) then a else b` — **not** a function call.
- Keep **spaces around operators** and inside parentheses (`if ( [b] = 0 )`).
- Boolean / logical keywords are lowercase: `true`, `false`, `and`, `or`, `not`, `null`.
- **Model formulas** may reference unaggregated columns and aggregate them inline;
  **Answer/Liveboard formulas** reference model column display names.

---

## Fallback strategy (tiered, mirrors the Tableau reference)

1. **Native equivalent** — direct 1:1 (`Sum`→`sum`). → AUTO.
2. **Composite formula** — chain TML functions (`IfNull`→`if (is_null(x)) then y else x`,
   `between`→two comparisons). → PARTIAL with a note.
3. **Omit and log** — anything in the time-intelligence / statistical / R / window families,
   or any unknown function: emit **no expression**, set `Coverage.MANUAL`, record the
   offending function in the note, and preserve the original Sisense formula as `source` so
   the coverage report shows the consultant exactly what to rebuild.

ThoughtSpot **does** provide a SQL pass-through tier — the connections-passthrough functions
`sql_double_op`, `sql_int_op`, `sql_bool_op`, `sql_date_op`, `sql_string_op` (+ their
`*_aggregate_op` variants), which embed a warehouse function via `"fn ({0}, {1})"` templates
(same idea as the Tableau reference's wrappers). We intentionally **do not use it for v1**:
the demo scope ends at the confident subset, and a Databricks-specific passthrough is harder
to validate than an honest MANUAL flag. Revisit post-demo for the long tail.

---

## Worked examples

```text
# AUTO — aggregations + arithmetic
Sisense:     sum([rev]) / count([ord])
             context: rev={dim:[Orders.Revenue], agg:sum}, ord={dim:[Orders.Order ID], agg:count}
ThoughtSpot: sum([Revenue]) / count([Order ID])

# AUTO — bare placeholders take their context agg
Sisense:     [rev] / [ord]   (same context as above)
ThoughtSpot: sum([Revenue]) / count([Order ID])

# PARTIAL — DupCount approximated, flagged for review
Sisense:     DupCount([Customer ID]) * 2
ThoughtSpot: count([Customer ID]) * 2          # note: countduplicates approximated as count

# MANUAL — time intelligence, not translated
Sisense:     growth(sum([rev]))
ThoughtSpot: (none) — Coverage.MANUAL, note "unsupported function 'growth'", source preserved
```

---

## Coverage notes & caveats

- **All ThoughtSpot target names are confirmed** against the *complete* TS 26.6.0 formula
  reference (operators, aggregate, conversion, date, mixed, number, text, passthrough).
  Corrections this surfaced over earlier passes: `is_null`→`isnull`, `ceil` (not `ceiling`),
  `pow` (not `power`), `round`'s increment-vs-decimal-places semantics, `safe_divide`
  returning 0 (not null), and Sisense `Log` confirmed as the natural log (→ `ln`, AUTO).
  No `verify` items remain.
- **Available-but-unused TS functions** (room to grow the auto-translated subset later):
  filtered aggregates `sum_if`/`count_if`/`average_if`/… (for Sisense measures that carry a
  filter context), `greatest`/`least` (scalar min/max of args), and the text family
  (`concat`/`contains`/`left`/`right`/`strpos`/`substr`/`strlen`). None are wired into
  `FUNCTION_MAP` yet because the Sisense JAQL measure formulas in scope don't exercise them.
- **Aggregation surface matters.** A bare JAQL `agg` → uppercase TML aggregation enum; the
  same op inside a formula → lowercase function. The same `countduplicates` is therefore
  PARTIAL on both surfaces (`COUNT` enum / `count(...)` function).
- **Division by zero diverges.** Sisense yields null; raw TML division can error. Composite
  translations should wrap division (`safe_divide` or an explicit `if`).
- **`Contains`/`StartsWith`/`EndsWith` are filters, not measures.** They surface as JAQL
  filter predicates — route them through filter mapping, not `translate_formula`.
- **Nested formulas recurse.** A context entry that is itself a `formula`+`context` is
  translated recursively; if any nested leg is MANUAL, the whole formula is MANUAL.

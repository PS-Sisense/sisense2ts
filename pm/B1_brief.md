# B1 brief — `translate_formula` (Pooja / Dev B)

## Goal
Implement `translate_formula` in [`sisense2ts/map/formula.py`](../sisense2ts/map/formula.py):
convert a Sisense JAQL calculation (a `Formula` = expression + context) into a ThoughtSpot
TML formula expression, returning a `TranslationResult(expr, coverage, note, source)`.

You are **not** covering every JAQL function — just the common subset. Everything else is
flagged `MANUAL` so the coverage report surfaces it. This is the 80/20, not the universe.

## What you have to work against (it's all in the repo)
- **IR types** (`sisense2ts/ir/models.py`): `Formula(expression, context)`, `TranslationResult`,
  `Coverage` (AUTO / PARTIAL / MANUAL). Frozen — code against these.
- **Seed maps** (already in `map/formula.py`): `AGG_MAP` (JAQL agg → TML), `FUNCTION_MAP`
  (JAQL func → TML func), `UNSUPPORTED` (flag these MANUAL). `translate_simple_agg` is a
  worked example to mirror.
- **Fixtures**: `tests/fixtures/dashboard_rich.json` has a **translatable** calc
  (`sum([rev]) / count([ord])`) and an **unsupported** one (`growth(...)`).
  `dashboard_sample.json` has the Avg Order Value calc.
- **Tests**: `tests/test_formula.py` — 3 passing + 1 `xfail` (`test_translate_simple_formula`)
  that defines expected behavior. Make it pass and remove the strict `xfail` marker.

## The JAQL formula shape
`expression` is a string that references `context` keys inside `[brackets]`, e.g.
`"sum([rev]) / count([ord])"`, with
`context = {"rev": {"dim": "[Orders.Revenue]", "agg": "sum"}, "ord": {"dim": "[Orders.Order ID]", "agg": "count"}}`.
A context value can itself be a nested `formula` + `context` (recurse).

## What to implement
1. **Resolve placeholders**: for each context key `K`, substitute `[K]` in the expression
   with its TML form — a `{dim, agg}` fragment becomes `agg(Column)` (use `AGG_MAP` + the
   column name from `dim`); nested `formula` fragments recurse.
2. **Map functions** via `FUNCTION_MAP` (sum→sum, if→if, …).
3. **Coverage**:
   - `AUTO` — every function/agg maps cleanly.
   - `PARTIAL` — maps with a caveat (e.g. `countduplicates`→COUNT approximation; `case`→nested `if`).
   - `MANUAL` — any function in `UNSUPPORTED` or unknown → `expr=None`, note the offender, keep `source`.
4. Return `TranslationResult(expr, coverage, note, source=formula.expression)`.

## In scope / out of scope
- **In**: aggregations (sum/avg/count/min/max), math (abs/round/ceil/floor/pow/sqrt/exp/mod),
  logical (if/isnull; case→if), arithmetic operators.
- **Out → flag MANUAL** (already in `UNSUPPORTED`, extend as needed): time-intelligence
  (`PAST*`/`GROWTH*`/`DIFFPAST*`/`*TD*`), `RANK`/`ORDERING`, measured-value scoping,
  `RSUM`/`PREV`/`NEXT`, R functions, percentile/quartile/correl/etc.

## Definition of done
- `pytest tests/test_formula.py` green; flip the `xfail` to a real pass (remove the marker).
- Add tests: a translatable formula → AUTO with the right `expr`; `growth(...)` → MANUAL
  (`expr is None`); a partial (case or countduplicates) → PARTIAL.
- Feed `CoverageItem`s so the report shows AUTO/PARTIAL/MANUAL counts.

## Two gotchas
- **Context-key brackets**: real Sisense JAQL uses **unbracketed** context keys
  (`context: {"rev": ...}`) referenced as `[rev]` in the expression. Some fixtures/tests
  currently use bracketed keys. Make `translate_formula` robust to both (strip brackets
  from keys, then replace `"[" + key + "]"` in the expression), and fix the fixture if it
  bothers you.
- **The live sample didn't exercise this.** The Sample ECommerce dashboard's "formulas"
  were trivial (gauge bounds / simple aggregations), so the working demo model uses plain
  `SUM` measures, not translated JAQL. Develop against `dashboard_rich.json` + the Sisense
  function catalog, not the live sample.

## Running it with Claude (per CONTRIBUTING.md)
> "Implement `translate_formula` in `map/formula.py` per `pm/B1_brief.md`; make
> `tests/test_formula.py` pass; flag UNSUPPORTED functions as MANUAL; stay within the IR."

Then post a comment and flip status with `python pm/clickup_task.py`.

`translate_formula` is consumed by **B5** (calculated columns → Model formulas) and by
content measures, so it unblocks the rest of the model work.

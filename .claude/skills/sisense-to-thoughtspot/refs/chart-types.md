# Widget → ThoughtSpot chart type, and how to get a new type right

## The method (standing rule)

For each chart type, **template off a real exported TML** from an accessible
Liveboard on the target cluster — do not hand-write axis configs from memory.
ThoughtSpot's Answer `chart` shape has many type-specific required keys, and they
drift by version. Workflow:

1. Build the Answer with the columns + chart type.
2. Import with policy `VALIDATE_ONLY`. If it errors, the message names the gap.
3. If you don't know the right shape, export a working Answer of that exact
   chart type from an accessible Liveboard (`/api/rest/2.0/metadata/tml/export`)
   and **diff** your generated TML against it.
4. If that chart type is in **no** accessible Liveboard, ask the user to grab
   one exported TML of that type. (`Index: 0` in a validation error == a
   malformed viz; diff against a known-good export.)

This is exactly the gap-scout / "flag, never fake" discipline: a type we can't
template correctly is flagged, not emitted wrong.

## The map (`CHART_TYPE_MAP` in `map/content.py`)

| Sisense `type`     | TML `chart_type` | Notes |
|--------------------|------------------|-------|
| `indicator`        | `KPI`            | gauge-bound JAQL items are skipped in parse |
| `chart/column`     | `COLUMN`         | |
| `chart/bar`        | `BAR`            | |
| `chart/line`       | `LINE`           | |
| `chart/area`       | `AREA`           | |
| `chart/pie`        | `PIE`            | |
| `chart/scatter`    | `SCATTER`        | |
| `chart/bubble`     | `SCATTER`        | approx (no native bubble; size dim flagged) |
| `chart/polar`      | `COLUMN`         | approx |
| `pivot` / `pivot2` | `PIVOT_TABLE`    | |
| `tablewidget`      | `TABLE`          | |
| `treemap`          | `TREEMAP`        | |
| `chart/boxplot`    | `TABLE`          | no equiv → fall back + flag PARTIAL |
| `sunburst`         | `TABLE`          | approx → flag |
| `richtexteditor`   | `None`           | text widget → no Answer; flag MANUAL |

Unknown types fall back to `TABLE`.

## Axis configs we derived live (the part that makes charts actually render)

Validation passing is NOT rendering. These are the configs that render on the
live cluster (`measures` = columns starting `Total `/agg-prefixed; `dims` = the rest):

- **KPI** — `axis_configs: [{ y: [measure] }]`. The measure MUST be under `y`
  even with no dimension. Templated off the "User Adoption" Liveboard.
- **SCATTER** — `axis_configs: [{ x: [measure0], y: [measure1 or measure0],
  color: [dim0] }]`. x/y are measures; the first dimension becomes color.
  Templated off "Performance Tracking". Bubble adds a size measure (flagged; not
  yet placed).
- **COLUMN / BAR / LINE / AREA / STACKED_*** — `axis_configs: [{ x: [dim0],
  y: [measures], color: [extra dims] }]`. The first dim is the category;
  measures go on y; **extra dimensions become the series/`color`**, not a second
  x. Templated off "Embrace Pinboard".
- **PIE** — category dim + one measure; do NOT leak filter-panel dims as a
  second column (that was the bug that broke the pies).

## The two bugs that cost us the most

1. **Filter-panel fields leaking as plotted columns.** A JAQL item whose panel
   is `filters` is a filter, not an axis column. `parse.py` tags each Field with
   `field.panel`; `dashboard_to_tml` skips `panel == "filters"`. Forgetting this
   plotted a filter dimension (Gender) and broke the chart.
2. **Multi-dimension charts putting both dims on x.** The 2nd+ dimension must go
   under `color` (series), not stacked on x.

See `map/content.py::answer_tml` for the implementation these notes describe.

## Canonical reference shapes (offline templates) — and deltas to fix

`../fixtures/ts-native-liveboard.tml` is a ThoughtSpot-native export (the shape
we emit), captured offline so you can template the common types without a live
export. Diffing it against what `content.py` emits today surfaces these
candidate fixes (all verified against the native export, none applied yet):

- **PIE: `axis_configs: {x:[dim], y:[measure]}`. ✅ APPLIED + verified live
  (2026-06-24)** — we emitted no axis_configs for PIE before; the native export
  has them and the fixed PIE validates clean on the cluster.
- **KPI: keep `axis_configs: {y:[measure]}` (y ONLY).** The native export shows
  KPI with the measure on BOTH `x` and `y`, but that ONLY works because it also
  carries `client_state_v2` axisProperties binding those axes. In our minimal
  TML (empty client_state_v2), adding a bare `x` 400s with "Invalid axis config
  columns. These column ids do not exist." ❌ Tried x+y live, reverted. This is
  the "fixture-misleads-without-client_state" trap — verify live, don't copy the
  fixture blind.
- `table_columns` entries in the native export carry `headline_aggregation` (SUM
  for measures, COUNT_DISTINCT for dims), which we omit. Untested candidate; only
  add it with a live re-validate.
- **Multi-MEASURE ≠ multi-DIMENSION.** Our "extra dims → `color`" is right for
  dimensions. For two measures the native shape is `ADVANCED_COLUMN` with two
  `Y` axisProperties (one `isOpposite: true` for a dual axis), `display_mode:
  TABLE_MODE`, and a `custom_chart_config` block — not a color series.
- `client_state_v2` is where axis labels, data labels, dual-axis `isOpposite`,
  and sorts live. Empty strings import and render for the basics; reach for it
  when a chart needs those.

Treat the fixture as the source of truth for a type's shape; treat our current
`answer_tml` output as the thing to reconcile toward it.

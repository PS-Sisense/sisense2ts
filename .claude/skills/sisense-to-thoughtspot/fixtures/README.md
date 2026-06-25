# Canonical ThoughtSpot TML — offline templates

These are **ThoughtSpot-native** TML exports (a Model + a Liveboard over a retail
star, demo/synthetic data). They are the shapes we EMIT, captured offline so the
"validate-then-template" method in `../refs/chart-types.md` does not require a
live export for the common chart types.

- `ts-native-model.tml` — a Model TML (tables, joins, columns, aggregations).
- `ts-native-liveboard.tml` — a Liveboard with KPI / COLUMN / LINE / PIE /
  multi-measure (ADVANCED_COLUMN) Answers + a `layout.tiles` grid.

## Per-viz canonical chart shapes (from `ts-native-liveboard.tml`)

| Viz | type | `axis_configs` | Notes |
|---|---|---|---|
| Total Net Revenue | `KPI` | `x:[measure], y:[measure]` | measure on BOTH axes — but this needs the fixture's `client_state_v2` axisProperties. With minimal TML (empty client_state) use **`y:[measure]` only**; a bare `x` 400s. Verified live 2026-06-24. |
| Net Revenue by Category | `COLUMN` | `x:[dim], y:[measure]` | |
| Net Revenue by Month | `LINE` | `x:[dim], y:[measure]` | |
| Net Revenue by Customer Segment | `PIE` | `x:[dim], y:[measure]` | PIE DOES carry axis_configs (we currently omit them) |
| Region Performance (2 measures) | `ADVANCED_COLUMN` | two `Y` axisProperties, one `isOpposite: true` | multi-MEASURE → dual-Y, NOT color; `display_mode: TABLE_MODE`; uses `custom_chart_config` |

Other observed shape details:
- Every `table.table_columns[]` entry has `headline_aggregation` (SUM for
  measures, COUNT_DISTINCT for dimensions). We emit `column_id` only.
- `client_state_v2` carries axis/column-property JSON. Our empty-string
  client_state imported and rendered, so it appears optional for the basics, but
  it is where axis labels, data labels, dual-axis `isOpposite`, and sorts live.
- Each visualization has a `viz_guid`; the Liveboard has a top-level `guid`.

## Layout (the Phase 4 target shape)

```yaml
layout:
  tiles:
  - { visualization_id: Viz_1, x: 0, y: 0,  height: 4, width: 3  }   # KPI card
  - { visualization_id: Viz_2, x: 3, y: 0,  height: 8, width: 6  }   # chart
  - { visualization_id: Viz_5, x: 0, y: 16, height: 8, width: 12 }   # full width
```

`x`/`width` are on a **12-column** grid; `y`/`height` stack downward. This is the
target our IR `TilePosition` (Sisense columns/cells/subcells) maps onto.

## Provenance

Adapted from the MIT-licensed **sigma-migration-skills**
(https://github.com/twells89/sigma-migration-skills, Thomas Wells), where these
ship as fixtures for the reverse-direction `thoughtspot-to-sigma` converter.
Reused here under MIT as reference templates for the ThoughtSpot TML we generate.
Demo/synthetic data only.

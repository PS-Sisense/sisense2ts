# ThoughtSpot TML + REST gotchas (paid for in trial-and-error)

## Auth — mint a fresh token from the trusted-auth secret_key

Static bearer tokens expire (~401 mid-run). The fix is a trusted-auth
`secret_key`: it mints a fresh token on demand, so expiry is a non-issue.

```
POST /api/rest/2.0/auth/token/full
body: { username, secret_key, org_id }   → { token }
```

`load/ts_client.get_token(ts_cfg)` does this, falling back to a static
`token` if no `secret_key` is present. The token is **org-bound** — mint it
with the right `org_id`. (See the org-isolation memory: the tenant boundary is
the Org + server-side org_id, not the secret.)

## Import API

```
POST /api/rest/2.0/metadata/tml/import
policy: VALIDATE_ONLY   → validate, create nothing (use for the per-viz preflight)
        ALL_OR_NONE     → all objects or none
        PARTIAL         → import what passes
```
`load/ts_client.import_tml(base_url, token, tmls, policy)`. `status_of(item)`
returns `(code, name, guid)`; `code == "ERROR"` means that TML failed.
Import order matters: **Tables → Model → Answers/Liveboard.** Read back the
Model's GUID from its import result and bind Answers to it (`fqn`).

## Databricks / warehouse naming

- **Table names fold to lowercase.** `model_to_tml` sets `db_table=.lower()`,
  else import fails with `External table workspace.sisense_demo.Country not found`.
- **Physical columns use underscores**, not spaces — Delta rejects spaces
  (`Country_ID`, not `Country ID`). `_dbcol()` does spaces→`_`.
- **Catalog** for the demo workspace is `workspace` (not `main`).
- A numeric ID column maps to **ATTRIBUTE**, not a SUM measure (`_role`).

## The Answer `table` block (the "Index: 0" fix)

A minimal Answer that has only a `chart` block fails import with `Index: 0`.
An Answer MUST also carry, alongside the chart:
- `display_mode: CHART_MODE`
- `tables: [{ id, name, fqn }]` (the Model binding)
- `search_query` (the TML search tokens, e.g. `[Country] [Revenue]`)
- `answer_columns: [{ name }, ...]`
- a `table` block: `{ table_columns, ordered_column_ids, client_state }`

`map/content.answer_tml` emits all of these. The `table` block was the actual
fix; the chart alone is not a valid Answer.

## Aggregated measure display names

A model measure with an aggregation shows up in search/columns as a prefixed
display name, e.g. `Total Revenue` (SUM), `Unique Number of Brand`
(COUNT_DISTINCT), `Average …`, `Min …`, `Max …`. `dashboard_to_tml` maps a
source field to the model column by display name and uses the prefixed form for
measures (`_AGG_PREFIX`). Search tokens use the bare column (`[Revenue]`); the
rendered column is the prefixed measure.

## Liveboard layout (Phase 4 target shape)

A Liveboard TML carries a `layout.tiles[]` on a **12-column** grid:

```yaml
layout:
  tiles:
  - { visualization_id: Viz_1, x: 0, y: 0, height: 4, width: 3 }
```

`x`/`width` are columns (0..12), `y`/`height` stack downward. Map the IR
`TilePosition` (Sisense columns/cells/subcells → row/col/width%) onto this. KPIs
read well at ~w3/h4, charts ~w6/h8, full-width tables w12. See
`../fixtures/ts-native-liveboard.tml`. Apply layout in the SAME Liveboard
import (CREATE preserves the `Viz_N` ids the tiles reference).

## Filters → `search_query` tokens

A widget/dashboard filter becomes a token in the Answer's `search_query`, e.g.
`[Category] [Net Revenue] [Region] = 'West'`. ThoughtSpot lowercases string
literals in the query (best-effort case for case-sensitive warehouses). This is
the path for porting Sisense JAQL `members`/`exclude`/range filters.

## Parity (Phase 5) — the two endpoints

- Sisense (source): `POST /api/datasources/{datasource}/jaql` with the widget's
  JAQL → aggregated rows.
- ThoughtSpot (target): `POST /api/rest/2.0/searchdata` with the Answer's
  `search_query` → rows under `contents[0].data_rows`.
Compare the aggregates; GREEN only on a match.

## Secrets

`config.yaml` holds Sisense token, ThoughtSpot secret_key + token, Databricks
PAT. It is **gitignored. Never commit it; never paste these into chat.** Rotate
anything that leaks. `config.example.yaml` is the committed template.

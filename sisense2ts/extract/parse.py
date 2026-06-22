"""WS-A: shape raw Sisense JSON into the frozen IR.

These two functions are the boundary between "Sisense knowledge" and the rest of the
pipeline. Everything downstream (map/) only ever sees the IR, never raw Sisense JSON.

Use the fixtures in tests/fixtures/ to develop these before live extraction works.

VERIFIED SHAPES (live Sisense Cloud trial, 2026-06-18 - the frozen IR held; only the
JSON paths differ from first assumptions):
- Data model (GET /api/v2/datamodel-exports/schema): tables live at
  datasets[].schema.tables[] (NOT datasets[].tables); each table has columns[] with an
  int `type` code (feed sisense_types.to_datatype). dataset/table/column each carry an
  `oid` AND an `id`/`name`.
- relations[]: relation["columns"] is a list of {dataset, table, column} OID triples
  (object oids, not names). Build an oid->name index from the datasets to resolve them.
- Dashboard widgets are NOT embedded in GET /dashboards/{oid}; fetch separately via
  SisenseClient.get_widgets(oid). Dashboard-level filters ARE on the dashboard object
  at dash["filters"][].jaql.
- Indicator (gauge) widgets carry extra jaql items for gauge bounds (formula "0", empty
  context); skip those and take the real measure from the values panel.
"""
from __future__ import annotations

from sisense2ts.extract.sisense_types import to_datatype
from sisense2ts.ir.models import (
    Field,
    FieldKind,
    Formula,
    JoinEndpoint,
    Relation,
    SourceColumn,
    SourceDashboard,
    SourceFilter,
    SourceModel,
    SourceTable,
    SourceWidget,
    TilePosition,
)


def parse_datamodel(raw: dict) -> SourceModel:
    """Sisense v2 datamodel export -> SourceModel.

    TODO(WS-A)  (paths verified on the live trial 2026-06-18):
      - walk datasets[].schema.tables[].columns[] -> SourceTable / SourceColumn
        (column `type` int -> to_datatype(); `isCustom`+`expression` -> calculated)
      - relations[]: relation["columns"] is a list of {dataset,table,column} OID triples;
        build an oid->name index from datasets to resolve into JoinEndpoint(table, column)
      - custom (SQL-defined) tables: type=="custom" + expression -> SourceTable.sql_expression
    """
    raise NotImplementedError("WS-A: parse_datamodel")


def parse_dashboard(raw: dict) -> SourceDashboard:
    """Sisense .dash JSON -> SourceDashboard.

    TODO(WS-A)  (verified on the live trial 2026-06-18):
      - widgets are a SEPARATE call: SisenseClient.get_widgets(oid), NOT embedded in the
        dashboard object. For each widget: type/subtype/title -> SourceWidget
      - per widget: metadata.panels[].items[].jaql -> Field
          dimension  = jaql with `dim`, no `agg`/`formula`
          measure    = jaql with `agg`
          calculated = jaql with `formula` (+ `context`) -> Formula
      - jaql `filter` objects -> SourceFilter (use classify_filter())
      - dashboard `filters[]` -> dashboard-level SourceFilter
      - layout.columns[].cells[].subcells[].elements[] -> TilePosition (by widgetid)
    """
    raise NotImplementedError("WS-A: parse_dashboard")


def classify_filter(jaql_filter: dict) -> SourceFilter:
    """Map a JAQL `filter` object to an IR SourceFilter. TODO(WS-A): cover
    members / equals|from|to / last|next / top+by / exclude (see ir.FilterKind)."""
    raise NotImplementedError("WS-A: classify_filter")

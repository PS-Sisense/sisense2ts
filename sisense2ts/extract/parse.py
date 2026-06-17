"""WS-A: shape raw Sisense JSON into the frozen IR.

These two functions are the boundary between "Sisense knowledge" and the rest of the
pipeline. Everything downstream (map/) only ever sees the IR, never raw Sisense JSON.

Use the fixtures in tests/fixtures/ to develop these before live extraction works.
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

    TODO(WS-A):
      - walk datasets[].tables[].columns[] -> SourceTable / SourceColumn
        (column `type` int -> to_datatype(); `isCustom`+`expression` -> calculated)
      - walk relations[] (each is a list of {dataset,table,column} triples) -> Relation
      - custom (SQL-defined) tables: type=="custom" + expression -> SourceTable.sql_expression
    """
    raise NotImplementedError("WS-A: parse_datamodel")


def parse_dashboard(raw: dict) -> SourceDashboard:
    """Sisense .dash JSON -> SourceDashboard.

    TODO(WS-A):
      - widgets[]: type/subtype/title -> SourceWidget
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

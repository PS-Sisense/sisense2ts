"""WS-A: shape raw Sisense JSON into the frozen IR.

These functions are the boundary between "Sisense knowledge" and the rest of the
pipeline. Everything downstream (map/) only ever sees the IR, never raw Sisense JSON.

Develop against the fixtures in tests/fixtures/. parse_dashboard accepts widgets either
embedded (synthetic fixtures) or passed separately (live trial, see below).

VERIFIED SHAPES (live Sisense Cloud trial, 2026-06-18 - the frozen IR held; only the
JSON paths differed from first assumptions):
- Data model (GET /api/v2/datamodel-exports/schema): tables live at
  datasets[].schema.tables[] (NOT datasets[].tables); each table has columns[] with an
  int `type` code (feed sisense_types.to_datatype). dataset/table/column each carry an
  `oid` AND an `id`/`name`.
- relations[]: relation["columns"] is a list of {dataset, table, column} OID triples
  (object oids, not names). Resolved here via an oid->name index built from the datasets.
- Dashboard widgets are NOT embedded in GET /dashboards/{oid}; fetch separately via
  SisenseClient.get_widgets(oid). Dashboard-level filters ARE on the dashboard object
  at dash["filters"][].jaql. The dashboard id is at dash["oid"] or dash["_id"].
- Indicator (gauge) widgets carry extra jaql items for gauge bounds (formula "0", empty
  context); those are skipped here. Real measures come from the values panel.
"""
from __future__ import annotations

from sisense2ts.extract.sisense_types import to_datatype
from sisense2ts.ir.models import (
    Field,
    FieldKind,
    FilterKind,
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


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
def parse_datamodel(raw: dict) -> SourceModel:
    """Sisense v2 datamodel export -> SourceModel.

    Tables are at datasets[].schema.tables[]. Relations reference columns by oid, so we
    build an oid->(table_id, column_id) index and resolve joins to ids that match the
    tables list. Falls back gracefully if a relation already uses names/ids (synthetic
    fixtures).
    """
    tables: list[SourceTable] = []
    col_by_oid: dict[str, tuple[str, str]] = {}   # column oid -> (table_id, column_id)
    table_by_oid: dict[str, str] = {}             # table oid -> table_id

    for ds in raw.get("datasets", []) or []:
        schema = ds.get("schema") or {}
        for t in schema.get("tables", []) or []:
            t_oid = t.get("oid")
            t_id = t.get("id") or t.get("name") or t_oid
            columns: list[SourceColumn] = []
            for c in t.get("columns", []) or []:
                c_id = c.get("id") or c.get("name") or c.get("oid")
                columns.append(
                    SourceColumn(
                        id=c_id,
                        name=c.get("name") or c.get("displayName") or c_id,
                        data_type=to_datatype(c.get("type")),
                        is_calculated=bool(c.get("isCustom")),
                        expression=c.get("expression"),
                        raw=c,
                    )
                )
                if c.get("oid"):
                    col_by_oid[c["oid"]] = (t_id, c_id)
            tables.append(
                SourceTable(
                    id=t_id,
                    name=t.get("displayName") or t.get("name") or t_id,
                    columns=columns,
                    sql_expression=t.get("expression") if t.get("type") == "custom" else None,
                    raw=t,
                )
            )
            if t_oid:
                table_by_oid[t_oid] = t_id

    relations: list[Relation] = []
    for rel in raw.get("relations", []) or []:
        endpoints: list[JoinEndpoint] = []
        for ep in rel.get("columns", []) or []:
            col_ref = ep.get("column")
            resolved = col_by_oid.get(col_ref)
            if resolved:
                endpoints.append(JoinEndpoint(table=resolved[0], column=resolved[1]))
            else:  # already a name/id (synthetic fixtures) or unresolved oid
                endpoints.append(
                    JoinEndpoint(table=table_by_oid.get(ep.get("table"), ep.get("table")), column=col_ref)
                )
        if endpoints:
            relations.append(Relation(endpoints=endpoints, cardinality=rel.get("type") or "UNKNOWN", raw=rel))

    return SourceModel(
        name=raw.get("title") or raw.get("name") or "model",
        datasource=raw.get("title") or "",
        tables=tables,
        relations=relations,
        raw=raw,
    )


# --------------------------------------------------------------------------- #
# Dashboard / widgets
# --------------------------------------------------------------------------- #
def _items(widget: dict):
    for panel in (widget.get("metadata") or {}).get("panels", []) or []:
        pname = panel.get("name") or ""
        for item in panel.get("items", []) or []:
            yield pname, item


def _jaql_to_field(jaql: dict) -> Field | None:
    """One JAQL item -> Field, or None for gauge-bound / empty items."""
    if not isinstance(jaql, dict):
        return None
    formula = jaql.get("formula")
    has_formula = formula not in (None, "", "0")
    dim = jaql.get("dim")
    agg = jaql.get("agg")
    if not has_formula and not dim:
        return None  # gauge bound or empty
    if has_formula:
        kind, f = FieldKind.MEASURE, Formula(expression=str(formula), context=jaql.get("context") or {})
    elif agg:
        kind, f = FieldKind.MEASURE, None
    else:
        kind, f = FieldKind.DIMENSION, None
    return Field(kind=kind, dim=dim, agg=agg, title=jaql.get("title") or "", formula=f,
                 level=jaql.get("level"), fmt=jaql.get("format") or {}, raw=jaql)


def parse_widget(widget: dict) -> SourceWidget:
    fields: list[Field] = []
    filters: list[SourceFilter] = []
    for pname, item in _items(widget):
        jaql = item.get("jaql") or {}
        field = _jaql_to_field(jaql)
        if field:
            field.panel = pname
            field.fmt = item.get("format") or field.fmt   # Sisense format is on the ITEM, not the jaql
            field.series_type = item.get("singleSeriesType")   # combo: per-series 'column'/'line' (item-level)
            fields.append(field)
        if jaql.get("filter"):
            sf = classify_filter(jaql)
            if sf:
                filters.append(sf)
    return SourceWidget(
        oid=widget.get("oid") or "",
        title=widget.get("title") or "",
        wtype=widget.get("type") or "",
        subtype=widget.get("subtype") or "",
        fields=fields,
        filters=filters,
        raw=widget,
    )


def _num(v) -> float:
    """Coerce a CSS-ish numeric ('184px', '50%', 50) to a float; 0 on failure."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).lower().replace("px", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse_layout(layout: dict) -> list[TilePosition]:
    tiles: list[TilePosition] = []
    for ci, col in enumerate(layout.get("columns", []) or []):
        col_w = _num(col.get("width"))
        for ri, cell in enumerate(col.get("cells", []) or []):
            for sub in cell.get("subcells", []) or []:
                width = _num(sub.get("width"))
                for el in sub.get("elements", []) or []:
                    if el.get("widgetid"):
                        tiles.append(TilePosition(widget_oid=el["widgetid"], height=int(_num(el.get("height"))),
                                                  width_pct=width, row=ri, col=ci, col_width_pct=col_w))
    return tiles


def parse_dashboard(raw: dict, widgets: list | None = None) -> SourceDashboard:
    """Sisense dashboard JSON (+ widgets) -> SourceDashboard.

    On the live trial, widgets are a separate get_widgets() call - pass them in. The
    synthetic fixtures embed widgets, so widgets defaults to raw["widgets"].
    """
    if widgets is None:
        widgets = raw.get("widgets") or []
    dash_filters: list[SourceFilter] = []
    for f in raw.get("filters", []) or []:
        sf = classify_filter(f.get("jaql") or f)
        if sf:
            dash_filters.append(sf)
    return SourceDashboard(
        oid=raw.get("oid") or raw.get("_id") or "",
        title=raw.get("title") or "",
        datasource=(raw.get("datasource") or {}).get("title") or "",
        widgets=[parse_widget(w) for w in widgets],
        filters=dash_filters,
        layout=_parse_layout(raw.get("layout") or {}),
        raw=raw,
    )


def classify_filter(jaql: dict) -> SourceFilter | None:
    """Map a JAQL item (dim + filter) to an IR SourceFilter.

    Live-observed filter keys: members, exclude, last/next, top/bottom, from/to/equals,
    plus flag keys explicit/multiSelection/all. Unknown shapes become FilterKind.UNKNOWN
    (still recorded, with raw, so nothing is silently dropped).
    """
    if not isinstance(jaql, dict):
        return None
    f = jaql.get("filter") or {}
    dim = jaql.get("dim")
    if not f:
        return None
    if "members" in f:
        return SourceFilter(FilterKind.MEMBER, dim, "members", list(f.get("members") or []), raw=f)
    if "exclude" in f:
        return SourceFilter(FilterKind.EXCLUDE, dim, "exclude", list((f.get("exclude") or {}).get("members") or []), raw=f)
    if "last" in f or "next" in f:
        op = "last" if "last" in f else "next"
        return SourceFilter(FilterKind.RELATIVE_DATE, dim, op, [f.get(op)], raw=f)
    if "top" in f or "bottom" in f:
        op = "top" if "top" in f else "bottom"
        return SourceFilter(FilterKind.TOP_N, dim, op, [f.get(op)], raw=f)
    if any(k in f for k in ("from", "to", "equals", "fromNotEqual", "toNotEqual")):
        return SourceFilter(FilterKind.RANGE, dim, "range",
                            [f[k] for k in ("from", "to", "equals") if k in f], raw=f)
    return SourceFilter(FilterKind.UNKNOWN, dim, ",".join(f.keys()), [], raw=f)

"""WS-B: IR semantic layer -> ThoughtSpot Table TML + one Model TML.

Target MODEL TML, not Worksheet TML (Worksheets are deprecated). Format verified against
a real export from the ps-internal cluster:
  - Table TML: name/db/schema/db_table/connection{name,fqn}, columns[{name, db_column_name,
    properties{column_type, aggregation}, db_column_properties{data_type}}], plus joins_with.
  - Model TML: model{name, model_tables[{name, joins[{with, referencing_join}]}],
    columns[{name, column_id "Table::Col", properties}]}.

Physical-name conventions (must match sql/databricks_sample_ecommerce.sql):
  db_table       = SourceTable.id without ".csv"
  db_column_name = column display name with spaces -> underscores
  column `name`  = the Sisense display name (kept, may contain spaces)
"""
from __future__ import annotations

from collections import Counter

from sisense2ts.ir.models import Coverage, CoverageReport, DataType, SourceModel

_TML_TYPE = {
    DataType.INT: "INT64", DataType.DOUBLE: "DOUBLE", DataType.BOOL: "BOOL",
    DataType.STRING: "VARCHAR", DataType.DATE: "DATE", DataType.DATETIME: "DATE_TIME",
    DataType.UNKNOWN: "VARCHAR",
}


def _clean(table_id: str) -> str:
    return table_id[:-4] if table_id.lower().endswith(".csv") else table_id


def _dbcol(name: str) -> str:
    return name.replace(" ", "_")


def _is_id(name: str) -> bool:
    return name.strip().lower().endswith("id")


def _role(col):
    """Infer column role when the IR did not set one. Numeric IDs are attributes, not
    measures; other numerics are SUM measures; everything else is an attribute."""
    if col.role is not None:
        return col.role.value, ("SUM" if col.role.value == "MEASURE" else None)
    if _is_id(col.name):
        return "ATTRIBUTE", None
    if col.data_type in (DataType.INT, DataType.DOUBLE):
        return "MEASURE", "SUM"
    return "ATTRIBUTE", None


def model_to_tml(model: SourceModel, connection_name: str, connection_fqn: str,
                 db: str, schema: str, model_name: str | None = None,
                 report: CoverageReport | None = None) -> dict:
    """Return {"tables": [<Table TML dict>...], "model": <Model TML dict>}."""
    # Join orientation: the most-connected table is the fact (source of the joins).
    part: Counter = Counter()
    for rel in model.relations:
        for ep in rel.endpoints:
            part[ep.table] += 1

    joins_with: dict[str, list] = {}   # table_id -> table-level joins_with entries
    model_joins: dict[str, list] = {}  # fact table_id -> model_tables joins
    for rel in model.relations:
        if len(rel.endpoints) < 2:
            continue
        a, b = rel.endpoints[0], rel.endpoints[1]
        src, dst = (a, b) if part[a.table] >= part[b.table] else (b, a)
        jname = f"{_clean(src.table)}_to_{_clean(dst.table)}"
        joins_with.setdefault(src.table, []).append({
            "name": jname,
            "destination": {"name": _clean(dst.table)},
            "on": f"[{_clean(src.table)}::{src.column}] = [{_clean(dst.table)}::{dst.column}]",
            "type": "INNER",
            "is_one_to_one": False,
        })
        model_joins.setdefault(src.table, []).append(
            {"with": _clean(dst.table), "referencing_join": jname})

    tables = []
    for t in model.tables:
        cols = []
        for c in t.columns:
            ctype, agg = _role(c)
            props = {"column_type": ctype}
            if agg:
                props["aggregation"] = agg
            cols.append({
                "name": c.name,
                "db_column_name": _dbcol(c.name),
                "properties": props,
                "db_column_properties": {"data_type": _TML_TYPE.get(c.data_type, "VARCHAR")},
            })
        tbl = {
            "name": _clean(t.id),
            "db": db, "schema": schema, "db_table": _clean(t.id).lower(),  # Databricks folds table names lowercase
            "connection": {"name": connection_name, "fqn": connection_fqn},
            "columns": cols,
        }
        if t.id in joins_with:
            tbl["joins_with"] = joins_with[t.id]
        tables.append({"table": tbl})

    # Model columns: curated (skip join-key IDs, dedupe by display name).
    seen: set = set()
    mcols = []
    for t in model.tables:
        for c in t.columns:
            if _is_id(c.name) or c.name in seen:
                continue
            seen.add(c.name)
            ctype, agg = _role(c)
            props = {"column_type": ctype}
            if agg:
                props["aggregation"] = agg
            mcols.append({"name": c.name, "column_id": f"{_clean(t.id)}::{c.name}", "properties": props})
            if report:
                report.add("column", c.name, Coverage.AUTO, ctype.lower())

    model_tables = []
    for t in model.tables:
        entry = {"name": _clean(t.id)}
        if t.id in model_joins:
            entry["joins"] = model_joins[t.id]
        model_tables.append(entry)

    return {
        "tables": tables,
        "model": {"model": {
            "name": model_name or model.name or "Converted Model",
            "model_tables": model_tables,
            "columns": mcols,
        }},
    }

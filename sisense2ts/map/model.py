"""WS-B: IR semantic layer -> ThoughtSpot Table TML + one Model TML.

Generation is built on the `thoughtspot_tml` library (do not hand-write YAML).
Target MODEL TML, not Worksheet TML (Worksheets are deprecated and their import is
blocked on current ThoughtSpot versions).

Key references (see README): a Table TML binds columns to a Connection + db/schema/
db_table; a Model TML lists model_tables, joins (with cardinality), columns
(column_id = "<table_path>::<column name>"), and formulas.
"""
from __future__ import annotations

from sisense2ts.ir.models import CoverageReport, SourceModel


def model_to_tml(
    model: SourceModel,
    connection_name: str,
    db: str,
    schema: str,
    report: CoverageReport | None = None,
) -> dict:
    """Return {"tables": [<Table TML>...], "model": <Model TML>} as thoughtspot_tml
    objects (or dicts ready to dump).

    TODO(WS-B):
      - one Table TML per SourceTable, bound to `connection_name` / db / schema.
        Map SourceColumn.data_type -> TML db_column_properties.data_type.
        Set column_type ATTRIBUTE vs MEASURE and a default aggregation for measures.
      - one Model TML: model_tables (+ fqn handling), joins from SourceModel.relations
        (cardinality defaults to MANY_TO_ONE if UNKNOWN -- log a PARTIAL coverage item),
        columns referencing table paths, and calculated columns -> formulas[].
      - calculated columns (SourceColumn.expression): translate via map.formula, attach
        as Model formulas or Table formulas; record coverage.
    """
    raise NotImplementedError("WS-B: model_to_tml")

"""Frozen intermediate representation (IR) for the Sisense -> ThoughtSpot converter.

THIS IS THE TEAM CONTRACT.  Status: FROZEN 2026-06-18 (task S1, signed off by lead).
Change it only via the amendment process in CONTRIBUTING.md ("Evolving the IR"): reach for
the `raw` escape hatch first, add new fields additively (with defaults), and make any
breaking change in one coordinated commit that updates every consumer with tests green.
Every workstream codes against these types in parallel, so a silent change breaks others.

Two halves:
  * Semantic layer  -> SourceModel / SourceTable / SourceColumn / Relation
  * Presentation    -> SourceDashboard / SourceWidget / Field / SourceFilter

The IR is intentionally source-neutral. Today Sisense populates it (extract/), but
the same shapes should accept Power BI / Tableau later so the map/ layer is reused.
Every node keeps a `raw` dict holding the original source JSON, so a workstream can
reach back for something the IR does not model yet without re-extracting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class DataType(str, Enum):
    """Normalized data types. map/model.py renders these to TML data_type values.
    WS-B: confirm the exact TML enum strings against thoughtspot_tml before M1."""
    INT = "INT64"
    DOUBLE = "DOUBLE"
    BOOL = "BOOL"
    STRING = "VARCHAR"
    DATE = "DATE"
    DATETIME = "DATE_TIME"
    UNKNOWN = "UNKNOWN"


class ColumnRole(str, Enum):
    ATTRIBUTE = "ATTRIBUTE"
    MEASURE = "MEASURE"


class FieldKind(str, Enum):
    DIMENSION = "dimension"
    MEASURE = "measure"


class FilterKind(str, Enum):
    MEMBER = "member"            # {"members": [...]}
    RANGE = "range"             # {"from":..,"to":..} / equals on numeric|datetime
    RELATIVE_DATE = "relative_date"  # {"last": {...}} / {"next": {...}}
    TOP_N = "top_n"            # {"top": N, "by": {...}}
    EXCLUDE = "exclude"        # {"exclude": {...}}
    UNKNOWN = "unknown"


class Coverage(str, Enum):
    """How completely an object was auto-converted. Drives the coverage report."""
    AUTO = "auto"        # fully translated, no human action needed
    PARTIAL = "partial"  # translated but with a caveat worth review
    MANUAL = "manual"    # could not translate; needs a human


# --------------------------------------------------------------------------- #
# Semantic layer
# --------------------------------------------------------------------------- #
@dataclass
class SourceColumn:
    id: str
    name: str
    data_type: DataType = DataType.UNKNOWN
    role: Optional[ColumnRole] = None  # MEASURE/ATTRIBUTE; None -> WS-B infers (numeric->MEASURE/SUM, else ATTRIBUTE)
    is_calculated: bool = False
    expression: Optional[str] = None   # raw Sisense SQL expr for calculated columns
    raw: dict = field(default_factory=dict)


@dataclass
class SourceTable:
    id: str
    name: str
    columns: list[SourceColumn] = field(default_factory=list)
    sql_expression: Optional[str] = None  # set for custom (SQL-defined) tables
    raw: dict = field(default_factory=dict)


@dataclass
class JoinEndpoint:
    table: str   # SourceTable.id
    column: str  # SourceColumn.id


@dataclass
class Relation:
    """One join. Usually two endpoints; more for multi-column joins.
    NOTE: Sisense v2 `relations` does NOT export cardinality, so it defaults to
    UNKNOWN and WS-B must infer or default it (TML needs a cardinality)."""
    endpoints: list[JoinEndpoint] = field(default_factory=list)
    cardinality: str = "UNKNOWN"   # MANY_TO_ONE | ONE_TO_ONE | ONE_TO_MANY | UNKNOWN
    raw: dict = field(default_factory=dict)


@dataclass
class SourceModel:
    name: str
    datasource: str = ""            # Sisense datasource title / ElastiCube name
    tables: list[SourceTable] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Presentation layer
# --------------------------------------------------------------------------- #
@dataclass
class Formula:
    """A Sisense JAQL calculation: a formula string plus its context map.
    e.g. expression="count([users]) / 10", context={"users": {"dim": "[Users.ID]"}}"""
    expression: str
    context: dict = field(default_factory=dict)  # placeholder-key -> jaql fragment


@dataclass
class Field:
    """A dimension or measure used by a widget (one item from a JAQL panel)."""
    kind: FieldKind
    dim: Optional[str] = None        # e.g. "[Commerce.Revenue]"
    agg: Optional[str] = None        # sum, avg, count, ... (simple measures)
    title: str = ""
    panel: str = ""                  # source JAQL panel: categories | values | break by | filters
    formula: Optional[Formula] = None  # set when this is a calculated measure
    level: Optional[str] = None      # date-dimension granularity (days/weeks/months/quarters/years); WS-D -> TS date bucket
    fmt: dict = field(default_factory=dict)  # Sisense format block, if any
    raw: dict = field(default_factory=dict)


@dataclass
class SourceFilter:
    kind: FilterKind
    dim: Optional[str] = None
    operator: str = ""               # equals, members, from, to, last, top, exclude, ...
    values: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class TilePosition:
    """Where a widget sits on the dashboard grid (Sisense layout column/cell/subcell)."""
    widget_oid: str
    height: int = 0
    width_pct: float = 0.0
    row: int = 0
    col: int = 0


@dataclass
class SourceWidget:
    oid: str
    title: str
    wtype: str                       # Sisense "type", e.g. "chart/column"
    subtype: str = ""                # e.g. "column/classic" (varies by version, verify empirically)
    fields: list[Field] = field(default_factory=list)
    filters: list[SourceFilter] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class SourceDashboard:
    oid: str
    title: str
    datasource: str = ""
    widgets: list[SourceWidget] = field(default_factory=list)
    filters: list[SourceFilter] = field(default_factory=list)   # dashboard-level
    layout: list[TilePosition] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Translation + coverage (produced by map/, consumed by report/)
# --------------------------------------------------------------------------- #
@dataclass
class TranslationResult:
    """Output of translating one Sisense calc/filter to TML."""
    expr: Optional[str]              # TML formula expr, or None when coverage == MANUAL
    coverage: Coverage
    note: str = ""                   # what could not be translated / the caveat
    source: str = ""                 # original Sisense formula, kept for the report


@dataclass
class CoverageItem:
    object_type: str                 # "formula" | "widget" | "filter" | "table" | ...
    name: str
    coverage: Coverage
    note: str = ""


@dataclass
class CoverageReport:
    items: list[CoverageItem] = field(default_factory=list)

    def add(self, object_type: str, name: str, coverage: Coverage, note: str = "") -> None:
        self.items.append(CoverageItem(object_type, name, coverage, note))

    def counts(self) -> dict:
        out = {c: 0 for c in Coverage}
        for it in self.items:
            out[it.coverage] += 1
        return {k.value: v for k, v in out.items()}

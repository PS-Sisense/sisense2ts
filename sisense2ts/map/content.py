"""WS-D: IR presentation layer -> ThoughtSpot Answer TML + Liveboard TML.

Each Sisense widget becomes an Answer (chart type + columns + filters). The dashboard
becomes a Liveboard whose `visualizations` are those Answers and whose `layout.tiles`
approximates the Sisense grid. Coarse, not pixel-perfect, by design.

CHART_TYPE_MAP is a seed. Sisense `subtype` strings drift across versions/plugins, so
derive missing ones empirically from the real trial exports (P1 will drop them into
fixtures). Unknown types fall back to TABLE.
"""
from __future__ import annotations

from sisense2ts.ir.models import CoverageReport, SourceDashboard

# Sisense widget type -> TML chart type. WS-D: confirm exact TML chart_type enum values
# against thoughtspot_tml / Answer TML before wiring.
CHART_TYPE_MAP: dict[str, str] = {
    "chart/column": "COLUMN",
    "chart/bar": "BAR",
    "chart/line": "LINE",
    "chart/area": "AREA",
    "chart/pie": "PIE",
    "chart/polar": "COLUMN",      # approx
    "chart/scatter": "SCATTER",
    "chart/bubble": "SCATTER",    # approx
    "chart/boxplot": "TABLE",     # no clean equiv -> fall back, flag PARTIAL
    "indicator": "KPI",
    "pivot": "PIVOT_TABLE",
    "pivot2": "PIVOT_TABLE",
    "tablewidget": "TABLE",
    "treemap": "TREEMAP",
    "sunburst": "TABLE",          # approx
    "richtexteditor": None,       # text widget -> no Answer; skip or note MANUAL
}
DEFAULT_CHART_TYPE = "TABLE"


def widget_chart_type(wtype: str) -> str | None:
    return CHART_TYPE_MAP.get(wtype, DEFAULT_CHART_TYPE)


def answer_tml(name, model_name, model_fqn, search_query, columns, chart_type="COLUMN"):
    """Build an Answer TML dict on a Model. `columns` are display names in order;
    a model measure with aggregation appears as 'Total <col>' (e.g. 'Total Revenue').
    Mirrors the cluster's exported answer shape: both a table and a chart block."""
    measures = [c for c in columns if c.startswith("Total ")]  # aggregated model measures
    dims = [c for c in columns if c not in measures]
    chart = {"type": chart_type, "chart_columns": [{"column_id": c} for c in columns],
             "client_state": "", "client_state_v2": ""}
    if chart_type in ("COLUMN", "BAR", "LINE", "AREA", "STACKED_COLUMN") and len(columns) >= 2:
        chart["axis_configs"] = [{"x": dims, "y": measures or [columns[-1]]}]
    elif chart_type == "KPI":  # KPI needs the measure under y, even with no dimension
        chart["axis_configs"] = [{"y": measures or columns}]
    return {
        "name": name,
        "display_mode": "CHART_MODE",
        "tables": [{"id": model_name, "name": model_name, "fqn": model_fqn}],
        "search_query": search_query,
        "answer_columns": [{"name": c} for c in columns],
        "table": {
            "table_columns": [{"column_id": c} for c in columns],
            "ordered_column_ids": list(columns),
            "client_state": "", "client_state_v2": "",
        },
        "chart": chart,
    }


def liveboard_tml(name, answers):
    """Wrap a list of Answer dicts into a Liveboard TML dict."""
    viz = [{"id": f"Viz_{i+1}", "answer": a} for i, a in enumerate(answers)]
    return {"liveboard": {"name": name, "visualizations": viz}}


def dashboard_to_tml(
    dash: SourceDashboard,
    model_name: str,
    report: CoverageReport | None = None,
) -> dict:
    """Return {"answers": [<Answer TML>...], "liveboard": <Liveboard TML>}.

    TODO(WS-D):
      - per widget -> Answer TML: chart type via widget_chart_type(); columns from
        widget.fields (dimensions -> attributes, measures -> measures via map.formula);
        attach widget + dashboard filters. Answer.tables references `model_name`.
        Flag fallback/approx chart types as PARTIAL; richtext/BloX as MANUAL/skip.
      - Liveboard TML: visualizations = those Answers (id "Viz 1", "Viz 2", ...);
        layout.tiles ordered from dash.layout with a size per tile.
    """
    raise NotImplementedError("WS-D: dashboard_to_tml")

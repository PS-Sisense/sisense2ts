"""WS-D: IR presentation layer -> ThoughtSpot Answer TML + Liveboard TML.

Each Sisense widget becomes an Answer (chart type + columns + filters). The dashboard
becomes a Liveboard whose `visualizations` are those Answers and whose `layout.tiles`
approximates the Sisense grid. Coarse, not pixel-perfect, by design.

CHART_TYPE_MAP is a seed. Sisense `subtype` strings drift across versions/plugins, so
derive missing ones empirically from the real trial exports (P1 will drop them into
fixtures). Unknown types fall back to TABLE.
"""
from __future__ import annotations

from sisense2ts.ir.models import Coverage, CoverageReport, SourceDashboard

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
    if chart_type == "SCATTER" and measures:        # x/y are measures; first dim -> color
        ax = {"x": measures[:1], "y": measures[1:2] or measures[:1]}
        if dims:
            ax["color"] = dims[:1]
        chart["axis_configs"] = [ax]
    elif chart_type in ("COLUMN", "BAR", "LINE", "AREA", "STACKED_COLUMN", "STACKED_BAR") and len(columns) >= 2:
        ax = {"x": dims[:1] or [columns[0]], "y": measures or [columns[-1]]}
        if len(dims) > 1:                            # extra dimensions become series/color
            ax["color"] = dims[1:]
        chart["axis_configs"] = [ax]
    elif chart_type in ("PIE", "DONUT") and len(columns) >= 2:  # category x, measure y (TS-native pie shape)
        chart["axis_configs"] = [{"x": dims[:1] or [columns[0]], "y": measures or [columns[-1]]}]
    elif chart_type == "KPI":  # measure under y ONLY. The TS-native export's x+y needs the
        # client_state_v2 axisProperties we don't emit; adding a bare x here 400s ("invalid axis").
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


_AGG_PREFIX = {"SUM": "Total ", "COUNT": "Total ", "COUNT_DISTINCT": "Unique Count ",
               "AVERAGE": "Average ", "MIN": "Min ", "MAX": "Max "}


def _model_col(dim: str) -> str:
    """'[Table.Column Name]' -> 'Column Name' (the model column display name)."""
    inner = (dim or "").strip().strip("[]")
    return inner.split(".")[-1].strip() if inner else ""


def _flag(report, name, reason):
    if report:
        report.add("widget", name, Coverage.MANUAL, reason)


def dashboard_to_tml(dash: SourceDashboard, model_name: str, model_fqn: str,
                     model_columns: list, report: CoverageReport | None = None) -> dict:
    """IR dashboard -> {"answers": [<Answer TML>...], "liveboard": <Liveboard TML>}.

    `model_columns` is the Model TML's `columns` list (each {name, properties:{column_type,
    aggregation}}), so we know attributes vs measures and the aggregated display name
    ('Total Revenue'). Each widget's fields are mapped to model columns by display name
    (Sisense dim '[Table.Col]' -> 'Col'). Widgets that can't map cleanly (calculated
    measures pending B1, fields not exposed on the model, text/no-chart widgets) are
    skipped and logged as MANUAL coverage rather than breaking the import. Pure: the caller
    validates each Answer and imports.
    """
    attrs = {c["name"] for c in model_columns
             if (c.get("properties") or {}).get("column_type") == "ATTRIBUTE"}
    measures = {c["name"]: _AGG_PREFIX.get((c.get("properties") or {}).get("aggregation", "SUM"), "Total ") + c["name"]
                for c in model_columns if (c.get("properties") or {}).get("column_type") == "MEASURE"}

    answers = []
    for w in dash.widgets:
        ct = widget_chart_type(w.wtype)
        if ct is None:
            _flag(report, w.title, f"widget type {w.wtype} has no chart equivalent")
            continue
        if any(f.formula for f in w.fields):
            _flag(report, w.title, "calculated measure (needs translate_formula / B1)")
            continue
        if not w.fields:
            _flag(report, w.title, "no fields")
            continue
        tokens, cols, seen, ok = [], [], set(), True
        for f in w.fields:
            if f.panel == "filters":   # a filter, not a column to plot
                continue
            name = _model_col(f.dim)
            if name in measures or f.agg:
                disp = measures.get(name)
            elif name in attrs:
                disp = name
            else:
                disp = None
            if not disp:
                ok = False
                break
            if disp in seen:   # same dim used as category + break-by/filter -> keep once
                continue
            seen.add(disp)
            tokens.append(f"[{name}]")
            cols.append(disp)
        if not ok or not cols:
            _flag(report, w.title, "a field maps to no model column (dropped ID / custom / unexposed)")
            continue
        answers.append(answer_tml(w.title, model_name, model_fqn, " ".join(tokens), cols, ct))
        if report:
            report.add("widget", w.title, Coverage.AUTO, ct)

    return {"answers": answers, "liveboard": liveboard_tml(dash.title or model_name, answers)}

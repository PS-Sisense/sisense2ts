"""WS-D: IR presentation layer -> ThoughtSpot Answer TML + Liveboard TML.

Each Sisense widget becomes an Answer (chart type + columns + filters). The dashboard
becomes a Liveboard whose `visualizations` are those Answers and whose `layout.tiles`
approximates the Sisense grid. Coarse, not pixel-perfect, by design.

CHART_TYPE_MAP is a seed. Sisense `subtype` strings drift across versions/plugins, so
derive missing ones empirically from the real trial exports (P1 will drop them into
fixtures). Unknown types fall back to TABLE.
"""
from __future__ import annotations

import re

from sisense2ts.ir.models import Coverage, CoverageReport, FilterKind, SourceDashboard
from sisense2ts.map.formula import translate_formula

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


def widget_chart_type(wtype: str, subtype: str = "") -> str | None:
    base = CHART_TYPE_MAP.get(wtype, DEFAULT_CHART_TYPE)
    st = (subtype or "").lower()
    if base in ("BAR", "COLUMN") and "stacked" in st:
        return "ADVANCED_STACKED_" + base   # bar/stacked -> ADVANCED_STACKED_BAR (explicit axis config)
    if base == "SCATTER" and ("bubble" in st or wtype == "chart/bubble"):
        return "ADVANCED_BUBBLE"       # TS bubble = ADVANCED_BUBBLE (x/y/slice/color/size dims)
    return base


# Sisense JAQL panel name -> axis role. Drives faithful axis assignment so a widget's
# columns land where the source put them (x/y/color/size) instead of being guessed.
# None => not a plotted column (gauge bounds, filters). "grain" => a column but no axis
# (e.g. a scatter/bubble's point dimension). Unknown panels default by field kind.
_PANEL_ROLE: dict[str, str | None] = {
    "categories": "x", "x-axis": "x", "rows": "x",
    "values": "y", "y-axis": "y", "value": "y",
    "break by": "color", "break by / color": "color", "color": "color", "break-by": "color",
    "size": "size",
    "point": "grain",
    "min": None, "max": None, "filters": None,
    "secondary": None,   # a KPI's comparison/growth badge -> not a plotted column (see loop)
}


def _panel_role(panel: str):
    p = (panel or "").strip().lower()
    return _PANEL_ROLE[p] if p in _PANEL_ROLE else ""   # "" => default by field kind later


# Sisense date-dimension `level` -> ThoughtSpot date BUCKET, attached to the column token
# as `[Col].MONTHLY` (NOT a separate token) (H2). Live-validated: `[Date].MONTHLY` groups by
# month; a standalone `[monthly]` token is read as a missing column and 400s. Cyclic date
# PARTS (day-of-week, etc.) have a different, unverified syntax -> flagged PARTIAL for now.
DATE_BUCKET_MAP: dict[str, str] = {
    "hours": "HOURLY", "days": "DAILY", "weeks": "WEEKLY",
    "months": "MONTHLY", "quarters": "QUARTERLY", "years": "YEARLY",
}
DATE_PART_LEVELS: frozenset[str] = frozenset({
    "dayofweek", "daysofweek", "weekday", "dayofmonth", "dayinmonth", "dayofquarter",
    "dayofyear", "monthofyear", "monthsofyear", "weekofyear", "weeksofyear", "hourofday",
})


def date_bucket_suffix(level: str | None) -> str | None:
    """Sisense date `level` -> a TS bucket suffix ('MONTHLY') for `[Col].MONTHLY`; None for
    cyclic parts / unmapped levels (caller flags PARTIAL)."""
    return DATE_BUCKET_MAP.get((level or "").lower())


def _custom_chart_config(slots):
    """Build an ADVANCED_* chart's `custom_chart_config` from `slots` (a list of
    (slot_key, [columns])). A slot with columns -> FLAT axes; an empty slot -> a bare,
    column-less slot (the shape ThoughtSpot exports). Mirrors a cluster-exported answer."""
    dims = []
    for key, cols in slots:
        if cols:
            dims.append({"key": key, "axes": [{"type": "FLAT", "column": c} for c in cols],
                         "mode": "AXIS_DRIVEN"})
        else:
            dims.append({"key": key, "mode": "AXIS_DRIVEN"})
    return [{"key": "basic", "dimensions": dims}]


def answer_tml(name, model_name, model_fqn, search_query, columns, chart_type="COLUMN",
               formulas=None, roles=None, formats=None):
    """Build an Answer TML dict on a Model. `columns` are display names in order;
    a model measure with aggregation appears as 'Total <col>' (e.g. 'Total Revenue').
    `roles` maps each display name to its source-panel axis role
    ('x'|'y'|'color'|'size'|'grain'); when absent, fall back to the Total-prefix
    heuristic (dims->x, measures->y). `formulas` are calculated measures
    [{id,name,expr}] emitted in a TML formulas block and referenced by name. Mirrors
    the cluster's exported answer shape: both a table and a chart block."""
    formulas = formulas or []
    fnames = {f["name"] for f in formulas}
    if roles:                                         # panel-driven (faithful) axis roles
        xs = [c for c in columns if roles.get(c) == "x"]
        ys = [c for c in columns if roles.get(c) == "y"]
        colors = [c for c in columns if roles.get(c) == "color"]
        sizes = [c for c in columns if roles.get(c) == "size"]
        grains = [c for c in columns if roles.get(c) == "grain"]
    else:                                             # legacy heuristic: dims->x, measures->y
        ys = [c for c in columns if c.startswith("Total ") or c in fnames]
        xs = [c for c in columns if c not in ys]
        colors, sizes, grains = [], [], []
    chart = {"type": chart_type, "chart_columns": [{"column_id": c} for c in columns],
             "client_state": "", "client_state_v2": ""}
    ax = {}
    if chart_type == "KPI":  # measure under y ONLY (bare x 400s without client_state_v2 axes)
        ax = {"y": ys or columns}
    elif chart_type in ("PIE", "DONUT") and len(columns) >= 2:
        ax = {"x": xs[:1] or [columns[0]], "y": ys[:1] or [columns[-1]]}
    elif chart_type == "ADVANCED_BUBBLE":   # x/y measures, slice=point dim, slice-with-color, size
        chart["custom_chart_config"] = _custom_chart_config(
            [("x-axis", xs[:1]), ("y-axis", ys[:1]), ("slice", grains[:1]),
             ("slice-with-color", colors[:1]), ("size", sizes[:1]), ("trellis-by", [])])
    elif chart_type in ("ADVANCED_STACKED_BAR", "ADVANCED_STACKED_COLUMN") and len(columns) >= 2:
        bar_dim = xs[:1] or [columns[0]]                  # the category axis (Sisense 'categories' panel)
        meas = ys or [columns[-1]]                        # the stacked measure(s)
        if chart_type == "ADVANCED_STACKED_BAR":          # horizontal: measure on x, category on y
            slots = [("x-axis", meas), ("y-axis", bar_dim)]
        else:                                             # vertical: category on x, measure on y
            slots = [("x-axis", bar_dim), ("y-axis", meas)]
        slots += [("slice-with-color", colors[:1]), ("trellis-by", [])]   # break-by -> the stack split
        chart["custom_chart_config"] = _custom_chart_config(slots)
    elif chart_type == "SCATTER":           # x/y are measures; first dim -> color
        if roles:
            if xs: ax["x"] = xs[:1]
            if ys: ax["y"] = ys[:1]
        else:
            ax = {"x": ys[:1], "y": ys[1:2] or ys[:1]}
            if xs:
                ax["color"] = xs[:1]
        if colors:
            ax["color"] = colors[:1]
    elif chart_type in ("COLUMN", "BAR", "LINE", "AREA", "STACKED_COLUMN", "STACKED_BAR") and len(columns) >= 2:
        ax = {"x": xs[:1] or [columns[0]], "y": ys or [columns[-1]]}
        series = colors or (xs[1:] if not roles else [])   # break-by / extra dims -> series
        if series:
            ax["color"] = series
    if ax:
        chart["axis_configs"] = [ax]
    answer = {
        "name": name,
        "display_mode": "CHART_MODE",
        "tables": [{"id": model_name, "name": model_name, "fqn": model_fqn}],
        "search_query": search_query,
        "answer_columns": [{"name": c} for c in columns],
        "table": {
            "table_columns": [
                {"column_id": c, **({"format_pattern": (formats or {})[c]} if (formats or {}).get(c) else {})}
                for c in columns
            ],
            "ordered_column_ids": list(columns),
            "client_state": "", "client_state_v2": "",
        },
        "chart": chart,
    }
    if formulas:
        answer["formulas"] = [{"id": f["id"], "name": f["name"], "expr": f["expr"]} for f in formulas]
    return answer


def liveboard_tml(name, answers, layout=None):
    """Wrap a list of Answer dicts into a Liveboard TML dict; `layout` (a list of tile
    dicts) is emitted as the Liveboard's `layout.tiles` when present."""
    viz = [{"id": f"Viz_{i+1}", "answer": a} for i, a in enumerate(answers)]
    lb = {"name": name, "visualizations": viz}
    if layout:
        lb["layout"] = {"tiles": layout}
    return {"liveboard": lb}


def _alloc(weights, total):
    """Split `total` integer units across `weights` proportionally (largest-remainder),
    summing to exactly `total`."""
    s = sum(weights) or 1
    raw = [w / s * total for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(weights)), key=lambda i: raw[i] - out[i], reverse=True)[:total - sum(out)]:
        out[i] += 1
    return [max(1, x) for x in out]


def liveboard_layout(tiles, viz_by_widget, grid_cols=12, px_per_row=46):
    """Sisense TilePositions -> Liveboard layout.tiles on a `grid_cols`-wide grid. Faithful:
    columns keep their proportional widths (largest-remainder to `grid_cols`), cells stack
    top-to-bottom, subcells sit side by side; px heights -> grid rows via `px_per_row`."""
    if not tiles:
        return []
    col_w = {}
    for t in tiles:
        col_w.setdefault(t.col, t.col_width_pct or 1.0)
    cols = sorted(col_w)
    spans = _alloc([col_w[c] for c in cols], grid_cols)
    col_x, x = {}, 0
    for c, sp in zip(cols, spans):
        col_x[c] = (x, sp); x += sp
    out = []
    for c in cols:
        x0, span = col_x[c]
        y = 0
        for r in sorted({t.row for t in tiles if t.col == c}):
            cell = [t for t in tiles if t.col == c and t.row == r]
            h = max(max(1, round(t.height / px_per_row)) for t in cell)
            cx = x0
            for t, sw in zip(cell, _alloc([t.width_pct or 1.0 for t in cell], span)):
                if viz_by_widget.get(t.widget_oid):
                    out.append({"visualization_id": viz_by_widget[t.widget_oid],
                                "x": cx, "y": y, "width": sw, "height": h})
                cx += sw
            y += h
    return out


# Chart types -> narrative tier, for the story layout. Everything not a KPI / trend / detail
# table is treated as composition/comparison (pie, bar, column, stacked, bubble, scatter, ...).
_TIER_KPI = frozenset({"KPI"})
_TIER_TREND = frozenset({"LINE", "AREA", "LINE_COLUMN", "LINE_STACKED_COLUMN"})
_TIER_DETAIL = frozenset({"GRID_TABLE", "PIVOT_TABLE"})


def _rows(vids, per_row, height, y, grid_cols):
    """Lay `vids` in rows of up to `per_row`, each row's width split evenly across `grid_cols`
    (largest-remainder), stacking downward from `y`. Returns (tiles, next_y)."""
    tiles = []
    for r in range(0, len(vids), per_row):
        chunk = vids[r:r + per_row]
        x = 0
        for vid, w in zip(chunk, _alloc([1] * len(chunk), grid_cols)):
            tiles.append({"visualization_id": vid, "x": x, "y": y, "width": w, "height": height})
            x += w
        y += height
    return tiles, y


def story_layout(viz_specs, grid_cols=12):
    """Reflow vizzes into a progressive-disclosure narrative, ignoring the source grid:
    KPIs (summary) -> trend (over time) -> composition (top/bottom, share) -> detail tables.
    `viz_specs` is [(viz_id, chart_type)] in display order. Implements the Position +
    Progressive Disclosure principles from ThoughtSpot's visualization guide: the summary tier
    reads first (top, packed in a row), detail sinks to the bottom; related composition charts
    sit two-up (proximity / view-diversely). Within a tier, source order is kept (we can't
    infer 'most important', so the first KPI lands top-left)."""
    kpi, trend, comp, detail = [], [], [], []
    for vid, ct in viz_specs:
        (kpi if ct in _TIER_KPI else trend if ct in _TIER_TREND
         else detail if ct in _TIER_DETAIL else comp).append(vid)
    tiles, y = [], 0
    if kpi:                                            # summary: one row (wraps past 6), short
        t, y = _rows(kpi, min(len(kpi), 6), 4, y, grid_cols); tiles += t
    if trend:                                          # trend: full width, or two-up if several
        t, y = _rows(trend, min(len(trend), 2), 8, y, grid_cols); tiles += t
    if comp:                                           # composition: two-up for side-by-side reading
        t, y = _rows(comp, 2, 9, y, grid_cols); tiles += t
    if detail:                                         # detail tables: full width, at the bottom
        t, y = _rows(detail, 1, 11, y, grid_cols); tiles += t
    return tiles


_AGG_PREFIX = {"SUM": "Total ", "COUNT": "Total ", "COUNT_DISTINCT": "Unique Count ",
               "AVERAGE": "Average ", "MIN": "Min ", "MAX": "Max "}

# Sisense JAQL agg -> ThoughtSpot formula function, used when an agg is applied to a column
# the model exposes as an ATTRIBUTE (e.g. count of an ID) -> emit it as a calc measure.
_AGG_FUNC = {"sum": "sum", "avg": "average", "average": "average", "count": "count",
             "countduplicates": "count", "countdistinct": "unique count",
             "min": "min", "max": "max"}


def _model_col(dim: str) -> str:
    """'[Table.Column Name]' -> 'Column Name' (the model column display name)."""
    inner = (dim or "").strip().strip("[]")
    return inner.split(".")[-1].strip() if inner else ""


def _safe_name(title: str) -> str:
    """A formula's name is also a `[name]` search token, so brackets/parens/# in the raw
    Sisense title (e.g. 'count([Patient ID])', '# PATIENTS') break the search. Strip those
    to a token-safe, still-readable name ('count Patient ID', 'PATIENTS')."""
    return re.sub(r"\s+", " ", re.sub(r"[\[\](){}#]", " ", title or "")).strip()


def _flag(report, name, reason):
    if report:
        report.add("widget", name, Coverage.MANUAL, reason)


def _filter_token(sf, attrs, measures):
    """A SourceFilter -> a ThoughtSpot search token ('[Gender] != 'Unspecified''), plus a
    PARTIAL note when a filter is recognized but not applied. Returns (token, note); both
    may be empty. Filters on columns the model doesn't expose, and 'all'/empty controls,
    are silently skipped (no restriction)."""
    col = _model_col(sf.dim)
    if col not in attrs and col not in measures:
        col = col.split(" (")[0].strip()
    if col not in attrs and col not in measures:
        return "", ""
    q = lambda v: f"'{v}'" if isinstance(v, str) else str(v)
    if sf.kind is FilterKind.MEMBER and sf.values:
        return f"[{col}] = " + " ".join(q(v) for v in sf.values), ""
    if sf.kind is FilterKind.EXCLUDE and sf.values:
        return f"[{col}] != " + " ".join(q(v) for v in sf.values), ""
    if sf.kind is FilterKind.TOP_N:
        return "", f"top-N on [{col}] not applied (display cap)"
    return "", ""


def _format_pattern(fmt: dict) -> str | None:
    """Sisense format block -> a ThoughtSpot column format_pattern, or None for the default.
    Carries currency / percent (the high-value cases) and grouped numbers; per-level date
    masks aren't mapped yet."""
    mask = (fmt or {}).get("mask") or {}
    if not mask or mask.get("years") or mask.get("days"):   # empty or a date mask -> skip
        return None
    cur, pct, dec = mask.get("currency"), mask.get("percent"), mask.get("decimals")
    frac = "." + "0" * int(dec) if str(dec).isdigit() and int(dec) > 0 else ""
    if cur:
        sym = cur.get("symbol", "$") if isinstance(cur, dict) else "$"
        return f"{sym}#,##0{frac or '.00'}"
    if pct:
        return f"0{frac or '.00'}%"
    if mask.get("type") == "number" or mask.get("separated"):
        return ("#,##0" if mask.get("separated", True) else "0") + frac
    return None


def dashboard_to_tml(dash: SourceDashboard, model_name: str, model_fqn: str,
                     model_columns: list, report: CoverageReport | None = None,
                     faithful_layout: bool = False) -> dict:
    """IR dashboard -> {"answers": [<Answer TML>...], "liveboard": <Liveboard TML>}.

    `model_columns` is the Model TML's `columns` list (each {name, properties:{column_type,
    aggregation}}), so we know attributes vs measures and the aggregated display name
    ('Total Revenue'). Each widget's fields are mapped to model columns by display name
    (Sisense dim '[Table.Col]' -> 'Col'). Widgets that can't map cleanly (calculated
    measures pending B1, fields not exposed on the model, text/no-chart widgets) are
    skipped and logged as MANUAL coverage rather than breaking the import. Pure: the caller
    validates each Answer and imports.

    A Sisense per-attribute top-N rank filter (e.g. "top 3 Categories by Revenue",
    `filter: {top: 3, by: sum(Revenue)}`) maps to a ThoughtSpot rank that re-ranks live:
      - single plotted dim -> a leading `top N` (the row cap IS exactly the top-N members);
      - the ranked dim plotted alongside others -> a subquery filter
        `[Category] in ( [Category] top 3 [Category] sort by [Revenue] )`, which keeps the
        ranked column so the other dimensions keep their full breakdown. Plain search `top N`
        can't do this (it caps total rows); the subquery is the global, dynamic, faithful form.

    Layout: by default the vizzes are reflowed into a progressive-disclosure narrative
    (`story_layout`: KPIs -> trend -> composition -> detail), since an intuitive flow beats
    mirroring the source grid for migration value. `faithful_layout=True` instead replicates
    the Sisense grid placement (`liveboard_layout`) for customers who want it preserved.
    """
    attrs = {c["name"] for c in model_columns
             if (c.get("properties") or {}).get("column_type") == "ATTRIBUTE"}
    measures = {c["name"]: _AGG_PREFIX.get((c.get("properties") or {}).get("aggregation", "SUM"), "Total ") + c["name"]
                for c in model_columns if (c.get("properties") or {}).get("column_type") == "MEASURE"}
    measure_agg = {c["name"]: ((c.get("properties") or {}).get("aggregation", "SUM") or "SUM").lower()
                   for c in model_columns if (c.get("properties") or {}).get("column_type") == "MEASURE"}

    answers, answer_widgets, answer_cts = [], [], []
    for w in dash.widgets:
        ct = widget_chart_type(w.wtype, w.subtype)
        if ct is None:
            _flag(report, w.title, f"widget type {w.wtype} has no chart equivalent")
            continue
        if not w.fields:
            _flag(report, w.title, "no fields")
            continue
        tokens, cols, seen, formulas, roles, formats, ok, reason, level_note = [], [], set(), [], {}, {}, True, "", ""
        cov, n_dims = Coverage.AUTO, 0   # n_dims = plotted dimension columns (drives top-N applicability)
        for f in w.fields:
            role = _panel_role(f.panel)
            if role is None:   # gauge min/max bounds, filters, KPI secondary badge -> not a plotted column
                # A KPI's secondary comparison/growth badge isn't a plotted column. If it needs a
                # function we don't translate (e.g. GrowthPastYear, time-intelligence), the primary
                # value still converts; flag PARTIAL so the dropped badge is visible, not silent.
                if (f.panel or "").lower() == "secondary" and f.formula and cov is Coverage.AUTO \
                        and translate_formula(f.formula).coverage is not Coverage.AUTO:
                    cov, level_note = Coverage.PARTIAL, "YoY comparison badge dropped (no clean ThoughtSpot formula)"
                continue
            if f.formula:      # calculated measure -> translate JAQL to a TML formula
                tr = translate_formula(f.formula)
                if tr.coverage is Coverage.MANUAL:
                    ok, reason = False, tr.note or "unsupported calculated measure"
                    break
                if "[" not in (tr.expr or ""):   # a bare constant (e.g. a gauge bound) -> not a column
                    continue
                fname = _safe_name(f.title) or f"Calc {len(formulas) + 1}"
                if fname in seen:
                    continue
                seen.add(fname)
                formulas.append({"id": f"formula_{len(formulas) + 1}", "name": fname, "expr": tr.expr})
                tokens.append(f"[{fname}]")
                cols.append(fname)
                roles[fname] = role or "y"
                if (fp := _format_pattern(f.fmt)):
                    formats[fname] = fp
                if tr.coverage is Coverage.PARTIAL:
                    cov = Coverage.PARTIAL
                continue
            name = _model_col(f.dim)
            if name not in measures and name not in attrs:   # Sisense date-hierarchy suffix:
                base = name.split(" (")[0].strip()           # 'Date (Calendar)' -> 'Date'
                if base in measures or base in attrs:
                    name = base
            is_dim = False
            override_fn = None
            if name in measures and f.agg:       # widget may override the measure's default agg
                fn = _AGG_FUNC.get((f.agg or "").lower())
                if fn and fn != _AGG_FUNC.get(measure_agg.get(name, "sum"), "sum"):
                    override_fn = fn            # e.g. AVG of a SUM measure -> emit a formula, not the default
            if name in measures and not override_fn:   # a model measure (its default agg applies)
                disp = measures[name]
            elif override_fn:                    # measure aggregated differently than its model default
                fname = _safe_name(f.title) or f"{f.agg.title()} {name}"
                if fname not in seen:
                    seen.add(fname)
                    formulas.append({"id": f"formula_{len(formulas) + 1}", "name": fname,
                                     "expr": f"{override_fn}([{name}])"})
                    tokens.append(f"[{fname}]")
                    cols.append(fname)
                    roles[fname] = role or "y"
                    if (fp := _format_pattern(f.fmt)):
                        formats[fname] = fp
                continue
            elif f.agg and name in attrs:        # agg on an attribute (e.g. count of an ID) -> calc measure
                aggl = (f.agg or "").lower()
                # Sisense count on a dimension is a DISTINCT count ("how many X") -> unique count.
                fn = "unique count" if aggl.startswith("count") else _AGG_FUNC.get(aggl)
                if not fn:
                    ok, reason = False, f"unsupported aggregation '{f.agg}'"
                    break
                fname = _safe_name(f.title) or f"{f.agg.title()} {name}"
                if fname in seen:
                    continue
                seen.add(fname)
                formulas.append({"id": f"formula_{len(formulas) + 1}", "name": fname,
                                 "expr": f"{fn}([{name}])"})
                tokens.append(f"[{fname}]")
                cols.append(fname)
                roles[fname] = role or "y"
                if (fp := _format_pattern(f.fmt)):
                    formats[fname] = fp
                continue
            elif name in attrs:                  # a plain dimension
                disp, is_dim = name, True
            else:
                ok, reason = False, "a field maps to no model column (dropped ID / custom / unexposed)"
                break
            if disp in seen:   # same dim used as category + break-by/filter -> keep once
                continue
            seen.add(disp)
            col_tok = f"[{name}]"
            if f.level:   # date granularity (H2) -> bucket attached to the column: [Col].MONTHLY
                suf = date_bucket_suffix(f.level)
                if suf:
                    col_tok = f"[{name}].{suf}"
                elif cov is Coverage.AUTO:
                    cov, level_note = Coverage.PARTIAL, f"date level '{f.level}' not applied (cyclic part / unmapped)"
            tokens.append(col_tok)
            cols.append(disp)
            roles[disp] = role or "x"
            if is_dim:
                n_dims += 1
            if (fp := _format_pattern(f.fmt)):
                formats[disp] = fp
        if not ok or not cols:
            _flag(report, w.title, reason or "no mappable fields")
            continue
        top_filters = []
        for sf in list(w.filters) + list(dash.filters):   # H5: widget + dashboard filters -> search tokens
            if sf.kind is FilterKind.TOP_N:                # a per-attribute rank filter (top 3 Cats by Revenue)
                top_filters.append(sf)
                continue
            ftok, fnote = _filter_token(sf, attrs, measures)
            if ftok and ftok not in tokens:
                tokens.append(ftok)
            elif fnote and cov is Coverage.AUTO:
                cov, level_note = Coverage.PARTIAL, fnote
        search_tokens = list(tokens)
        ranked_done = set()                              # a column may carry the same top-N on both the
        for sf in top_filters:                           # widget AND the dashboard -> apply it only once
            ranked = _model_col(sf.dim)                 # the attribute being ranked, e.g. 'Category'
            if ranked in ranked_done:
                continue
            ranked_done.add(ranked)
            by = (sf.raw or {}).get("by") or {}
            by_base = _model_col(by.get("dim"))         # the measure it ranks by, e.g. 'Revenue'
            try:
                n = int(sf.values[0])
            except (TypeError, ValueError, IndexError):
                continue
            if ranked not in cols:                       # ranked attribute isn't a plotted column -> can't apply
                if cov is Coverage.AUTO:
                    cov, level_note = Coverage.PARTIAL, f"top-{n} on [{ranked}] not applied (column not mapped)"
                continue
            if n_dims <= 1:                              # single plotted dim: leading "top N" IS the global top-N
                search_tokens = [f"top {n}"] + search_tokens
            elif by_base:                                # one of several plotted dims: a subquery filter keeps the
                # ranked column (so the other dimensions keep their full breakdown) and re-ranks live (no snapshot)
                search_tokens.append(f"[{ranked}] in ( [{ranked}] top {n} [{ranked}] sort by [{by_base}] )")
            elif cov is Coverage.AUTO:                   # multi-dim but the rank measure didn't map -> honest PARTIAL
                cov, level_note = Coverage.PARTIAL, f"top-{n} on [{ranked}] not applied (rank measure unmapped)"
                continue
            level_note = f"top {n} [{ranked}] by {by.get('title') or by_base or 'plotted measure'}"
        answers.append(answer_tml(w.title, model_name, model_fqn, " ".join(search_tokens), cols, ct,
                                  formulas=formulas, roles=roles, formats=formats))
        answer_widgets.append(w.oid)
        answer_cts.append(ct)
        if report:
            note = ct + (" + formula" if formulas else "") + (f"; {level_note}" if level_note else "")
            report.add("widget", w.title, cov, note)

    if faithful_layout:                                # replicate the Sisense grid placement
        viz_by_widget = {oid: f"Viz_{i + 1}" for i, oid in enumerate(answer_widgets)}
        layout = liveboard_layout(dash.layout, viz_by_widget)
    else:                                              # reflow into a progressive-disclosure story
        layout = story_layout([(f"Viz_{i + 1}", ct) for i, ct in enumerate(answer_cts)])
    return {"answers": answers,
            "liveboard": liveboard_tml(dash.title or model_name, answers, layout)}

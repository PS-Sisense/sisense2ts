"""C1/C2: dashboard_to_tml maps IR widgets to Answers + a Liveboard, flagging what it
can't map rather than dropping silently. Runs on committed fixtures (no live cluster)."""
from sisense2ts.extract import parse
from sisense2ts.ir.models import (
    Coverage,
    CoverageReport,
    Field,
    FieldKind,
    FilterKind,
    SourceDashboard,
    SourceFilter,
    SourceWidget,
    TilePosition,
)
from sisense2ts.map.content import (
    _format_pattern,
    answer_tml,
    dashboard_to_tml,
    date_bucket_suffix,
    liveboard_layout,
)
from sisense2ts.map.model import model_to_tml


def _date_widget(level: str):
    """A 'date by <level>' column widget over Order Date + Revenue."""
    return SourceWidget(
        oid="1", title="By Date", wtype="chart/column",
        fields=[
            Field(kind=FieldKind.DIMENSION, dim="[Orders.Order Date]", level=level, panel="categories"),
            Field(kind=FieldKind.MEASURE, dim="[Orders.Revenue]", agg="sum", panel="values"),
        ],
    )


_DATE_MCOLS = [
    {"name": "Order Date", "properties": {"column_type": "ATTRIBUTE"}},
    {"name": "Revenue", "properties": {"column_type": "MEASURE", "aggregation": "SUM"}},
]


def test_dashboard_to_tml(raw_datamodel, raw_dashboard_rich):
    sm = parse.parse_datamodel(raw_datamodel)
    mcols = model_to_tml(sm, "conn", "fqn", "db", "sch")["model"]["model"]["columns"]
    dash = parse.parse_dashboard(raw_dashboard_rich)
    rep = CoverageReport()
    out = dashboard_to_tml(dash, "M", "model-fqn", mcols, rep)

    # at least one widget auto-maps to an Answer on a Liveboard
    assert out["answers"]
    assert out["liveboard"]["liveboard"]["visualizations"]

    # formula-based widgets are flagged MANUAL, not silently dropped
    assert any(it.coverage is Coverage.MANUAL for it in rep.items)

    # no Answer carries duplicate columns (regression guard for the dedupe fix)
    for a in out["answers"]:
        names = [c["name"] for c in a["answer_columns"]]
        assert len(names) == len(set(names)), f"duplicate columns in {a['name']}"


def test_date_level_emits_bucket_token(raw_datamodel, raw_dashboard_rich):
    # H2: the monthly "Revenue Trend" widget must carry a [monthly] bucket in its search
    # query, right after the date column, so it groups by month instead of raw date.
    sm = parse.parse_datamodel(raw_datamodel)
    mcols = model_to_tml(sm, "conn", "fqn", "db", "sch")["model"]["model"]["columns"]
    dash = parse.parse_dashboard(raw_dashboard_rich)
    out = dashboard_to_tml(dash, "M", "model-fqn", mcols)

    trend = next(a for a in out["answers"] if a["name"] == "Revenue Trend")
    # H2: the date bucket attaches to the column ([Order Date].MONTHLY) - live-validated;
    # a standalone [monthly] token 400s. H5 may append dashboard filter tokens after.
    assert trend["search_query"].startswith("[Order Date].MONTHLY [Revenue]")
    # the bucket is a search modifier only, not an extra answer column
    assert [c["name"] for c in trend["answer_columns"]] == ["Order Date", "Total Revenue"]


def test_date_bucket_suffix():
    # continuous granularity -> a TS column bucket suffix ([Order Date].MONTHLY)
    assert date_bucket_suffix("months") == "MONTHLY"
    assert date_bucket_suffix("years") == "YEARLY"
    # cyclic parts + unmapped -> no bucket (caller flags PARTIAL)
    assert date_bucket_suffix("dayofweek") is None
    assert date_bucket_suffix("fortnight") is None
    assert date_bucket_suffix(None) is None


def test_top_n_filter_prepends_keyword():
    # a TOP_N filter -> a leading "top N" search keyword (base measure name), AUTO not PARTIAL.
    w = SourceWidget(oid="1", title="Top Cats", wtype="chart/bar",
                     fields=[Field(kind=FieldKind.DIMENSION, dim="[Category.Category]", panel="categories"),
                             Field(kind=FieldKind.MEASURE, dim="[Commerce.Revenue]", agg="sum", panel="values")],
                     filters=[SourceFilter(FilterKind.TOP_N, "[Category.Category]", "top", [3])])
    mcols = [{"name": "Category", "properties": {"column_type": "ATTRIBUTE"}},
             {"name": "Revenue", "properties": {"column_type": "MEASURE", "aggregation": "SUM"}}]
    rep = CoverageReport()
    out = dashboard_to_tml(SourceDashboard(oid="d", title="D", widgets=[w]), "M", "fqn", mcols, rep)
    assert out["answers"][0]["search_query"].startswith("top 3 ")
    assert all(it.coverage is not Coverage.PARTIAL for it in rep.items)


# A two-dimension top-N widget mirroring "TOP 3 CATEGORIES BY REVENUE AND AGE": Age Range on
# the bar axis, Revenue as the value, Category as the break-by, with a top-3 rank FILTER on
# Category by Revenue. This is the case search `top N` gets wrong (it caps total rows, not the
# ranked dimension), so it must resolve members and keep the ranked column.
def _topn_multidim_widget():
    return SourceWidget(
        oid="1", title="TOP 3 CATEGORIES BY REVENUE AND AGE", wtype="chart/bar", subtype="bar/stacked",
        fields=[Field(kind=FieldKind.DIMENSION, dim="[Commerce.Age Range]", panel="categories"),
                Field(kind=FieldKind.MEASURE, dim="[Commerce.Revenue]", agg="sum", panel="values"),
                Field(kind=FieldKind.DIMENSION, dim="[Category.Category]", panel="break by")],
        filters=[SourceFilter(FilterKind.TOP_N, "[Category.Category]", "top", [3],
                              raw={"top": 3, "by": {"dim": "[Commerce.Revenue]", "agg": "sum",
                                                    "title": "Total Revenue"}})])


_TOPN_MCOLS = [{"name": "Age Range", "properties": {"column_type": "ATTRIBUTE"}},
               {"name": "Category", "properties": {"column_type": "ATTRIBUTE"}},
               {"name": "Revenue", "properties": {"column_type": "MEASURE", "aggregation": "SUM"}}]


def test_top_n_multidim_emits_subquery_keeping_ranked_column():
    # the ranked dim (Category) plotted alongside Age Range -> a subquery filter that ranks
    # Category globally by Revenue while KEEPING [Category] in the chart (so Age Range keeps its
    # full breakdown). Dynamic (re-ranks live), AUTO, and not a row cap. Live-validated grammar.
    rep = CoverageReport()
    out = dashboard_to_tml(SourceDashboard(oid="d", title="D", widgets=[_topn_multidim_widget()]),
                           "M", "fqn", _TOPN_MCOLS, rep)
    q = out["answers"][0]["search_query"]
    assert not q.startswith("top 3")                               # not a row cap
    assert "[Category] in ( [Category] top 3 [Category] sort by [Revenue] )" in q
    assert all(it.coverage is Coverage.AUTO for it in rep.items)   # no snapshot, no PARTIAL


def test_liveboard_layout_faithful_grid():
    # two equal columns: left has one full-width tile; right stacks a cell of two side-by-side.
    tiles = [
        TilePosition(widget_oid="a", col=0, row=0, col_width_pct=50, width_pct=100, height=184),
        TilePosition(widget_oid="b", col=1, row=0, col_width_pct=50, width_pct=50, height=384),
        TilePosition(widget_oid="c", col=1, row=0, col_width_pct=50, width_pct=50, height=384),
    ]
    out = liveboard_layout(tiles, {"a": "Viz_1", "b": "Viz_2", "c": "Viz_3"})
    by = {t["visualization_id"]: t for t in out}
    assert by["Viz_1"]["x"] == 0 and by["Viz_1"]["width"] == 6      # left column, full width
    assert by["Viz_2"]["x"] == 6 and by["Viz_3"]["x"] == 9          # right column, split side by side
    assert by["Viz_2"]["width"] == 3 and by["Viz_3"]["width"] == 3
    assert by["Viz_1"]["height"] == 4 and by["Viz_2"]["height"] == 8  # px -> rows


def test_format_pattern_maps_currency_percent_number():
    # Sisense format mask -> TML format_pattern; high-value cases carry, default -> None.
    assert _format_pattern({"mask": {"currency": {"symbol": "$"}, "decimals": 2}}) == "$#,##0.00"
    assert _format_pattern({"mask": {"percent": True, "decimals": 1}}) == "0.0%"
    assert _format_pattern({"mask": {"type": "number", "separated": True, "decimals": "auto"}}) == "#,##0"
    assert _format_pattern({"mask": {"isdefault": True}}) is None    # plain default
    assert _format_pattern({"mask": {"years": "yyyy"}}) is None       # date mask (not mapped yet)
    assert _format_pattern({}) is None


def test_answer_tml_emits_format_pattern():
    a = answer_tml("k", "M", "fqn", "[Revenue]", ["Total Revenue"], "KPI",
                   formats={"Total Revenue": "$#,##0.00"})
    assert a["table"]["table_columns"][0]["format_pattern"] == "$#,##0.00"


def test_date_part_is_partial():
    # A cyclic date PART (day of week) uses a different, unverified TS syntax, so we don't
    # emit a possibly-broken token; the widget still maps (ungrouped) and is flagged PARTIAL.
    dash = SourceDashboard(oid="d", title="D", widgets=[_date_widget("dayofweek")])
    rep = CoverageReport()
    out = dashboard_to_tml(dash, "M", "fqn", _DATE_MCOLS, rep)
    assert out["answers"][0]["search_query"] == "[Order Date] [Revenue]"
    assert any(it.coverage is Coverage.PARTIAL for it in rep.items)


def test_unmapped_date_level_is_partial():
    # an unknown level still emits the widget (ungrouped) but is flagged PARTIAL.
    dash = SourceDashboard(oid="d", title="D", widgets=[_date_widget("fortnight")])
    rep = CoverageReport()
    out = dashboard_to_tml(dash, "M", "fqn", _DATE_MCOLS, rep)
    assert out["answers"][0]["search_query"] == "[Order Date] [Revenue]"
    assert any(it.coverage is Coverage.PARTIAL for it in rep.items)

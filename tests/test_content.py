"""C1/C2: dashboard_to_tml maps IR widgets to Answers + a Liveboard, flagging what it
can't map rather than dropping silently. Runs on committed fixtures (no live cluster)."""
from sisense2ts.extract import parse
from sisense2ts.ir.models import (
    Coverage,
    CoverageReport,
    Field,
    FieldKind,
    SourceDashboard,
    SourceWidget,
)
from sisense2ts.map.content import dashboard_to_tml, date_level_token
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
    assert trend["search_query"] == "[Order Date] [monthly] [Revenue]"
    # the bucket is a search modifier only, not an extra answer column
    assert [c["name"] for c in trend["answer_columns"]] == ["Order Date", "Total Revenue"]


def test_date_level_token_buckets_and_parts():
    # continuous granularity buckets
    assert date_level_token("months") == "[monthly]"
    assert date_level_token("years") == "[yearly]"
    # cyclic date-part extraction (incl. common Sisense spelling aliases)
    assert date_level_token("dayofweek") == "[day of week]"
    assert date_level_token("monthofyear") == "[month of year]"
    assert date_level_token("weekday") == "[day of week]"
    # unmapped -> no token
    assert date_level_token("fortnight") is None
    assert date_level_token(None) is None


def test_date_part_emits_keyword_token():
    # H2: a date-PART level (day of week) maps to its TS keyword, AUTO (not PARTIAL).
    dash = SourceDashboard(oid="d", title="D", widgets=[_date_widget("dayofweek")])
    rep = CoverageReport()
    out = dashboard_to_tml(dash, "M", "fqn", _DATE_MCOLS, rep)
    assert out["answers"][0]["search_query"] == "[Order Date] [day of week] [Revenue]"
    assert all(it.coverage is Coverage.AUTO for it in rep.items)


def test_unmapped_date_level_is_partial():
    # an unknown level still emits the widget (ungrouped) but is flagged PARTIAL.
    dash = SourceDashboard(oid="d", title="D", widgets=[_date_widget("fortnight")])
    rep = CoverageReport()
    out = dashboard_to_tml(dash, "M", "fqn", _DATE_MCOLS, rep)
    assert out["answers"][0]["search_query"] == "[Order Date] [Revenue]"
    assert any(it.coverage is Coverage.PARTIAL for it in rep.items)

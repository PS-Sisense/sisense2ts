"""A3/A4: raw Sisense JSON -> IR. Runs on the committed synthetic fixtures (real-shaped),
so CI covers parsing without the gitignored real exports."""
from sisense2ts.extract import parse
from sisense2ts.ir.models import FilterKind


def test_parse_datamodel(raw_datamodel):
    m = parse.parse_datamodel(raw_datamodel)
    assert {t.name for t in m.tables} >= {"Customers", "Orders"}

    orders = next(t for t in m.tables if t.name == "Orders")
    assert any(c.name == "Revenue" for c in orders.columns)

    cust = next(t for t in m.tables if t.name == "Customers")
    assert any(c.is_calculated for c in cust.columns)  # "Full Name" custom column

    # the oid-based relation resolved to table/column ids, not raw oids
    eps = m.relations[0].endpoints
    assert {e.table for e in eps} == {"Orders", "Customers"}
    assert all(e.column == "Customer ID" for e in eps)


def test_parse_dashboard(raw_dashboard):
    d = parse.parse_dashboard(raw_dashboard)  # synthetic fixture embeds widgets
    assert d.title
    assert len(d.widgets) == len(raw_dashboard["widgets"])

    # the indicator widget carries a calculated measure (formula + context)
    assert any(f.formula for w in d.widgets for f in w.fields)

    # dashboard-level relative-date filter parsed
    assert any(flt.kind is FilterKind.RELATIVE_DATE for flt in d.filters)

    # layout produced tiles
    assert d.layout


def test_parse_captures_date_level(raw_dashboard_rich):
    # the "Revenue Trend" line widget buckets Order Date by month (JAQL `level`)
    d = parse.parse_dashboard(raw_dashboard_rich)
    levels = {f.level for w in d.widgets for f in w.fields if f.level}
    assert "months" in levels


def test_offline_bundle_contract(raw_datamodel):
    # --dump-source writes {dashboard, widgets, datamodel}; --from-json reads the same shape
    # and feeds the SAME parse functions as the live path. Verify that contract parses.
    bundle = {"dashboard": {"title": "D", "datasource": {"title": "X"}},
              "widgets": {"widgets": []}, "datamodel": raw_datamodel}
    ir_model = parse.parse_datamodel(bundle["datamodel"])
    ir_dash = parse.parse_dashboard(bundle["dashboard"], bundle["widgets"]["widgets"])
    assert ir_model.tables            # model leg (binding-critical) parses
    assert ir_dash.title == "D"       # dashboard leg parses

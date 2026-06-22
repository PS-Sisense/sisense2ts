"""Sanity-check the sample fixtures so workstreams B/C/D can rely on their shape.
P1 replaces these with REAL trial exports once live extraction works (same filenames)."""


def test_datamodel_shape(raw_datamodel):
    tables = raw_datamodel["datasets"][0]["schema"]["tables"]
    names = {t["name"] for t in tables}
    assert {"Customers", "Orders"} <= names
    assert raw_datamodel["relations"], "expected at least one relation/join"


def test_dashboard_shape(raw_dashboard):
    assert raw_dashboard["widgets"], "expected at least one widget"
    wtypes = {w["type"] for w in raw_dashboard["widgets"]}
    assert "chart/column" in wtypes
    # the indicator widget carries a calculated measure (formula + context)
    ind = next(w for w in raw_dashboard["widgets"] if w["type"] == "indicator")
    jaql = ind["metadata"]["panels"][0]["items"][0]["jaql"]
    assert "formula" in jaql and "context" in jaql


def test_rich_dashboard_breadth(raw_dashboard_rich):
    """The rich sample must exercise breadth so the converter (and the demo) is tested
    against many chart types, all filter kinds, and a known-MANUAL calc."""
    wtypes = {w["type"] for w in raw_dashboard_rich["widgets"]}
    assert {"chart/column", "chart/line", "chart/pie", "indicator", "tablewidget"} <= wtypes
    # an UNSUPPORTED function (growth) must be present so coverage shows a MANUAL item
    blob = str(raw_dashboard_rich)
    assert "growth(" in blob
    # all major filter kinds appear somewhere in the dashboard
    assert "members" in blob and "last" in blob and "top" in blob and "from" in blob

"""C1/C2: dashboard_to_tml maps IR widgets to Answers + a Liveboard, flagging what it
can't map rather than dropping silently. Runs on committed fixtures (no live cluster)."""
from sisense2ts.extract import parse
from sisense2ts.ir.models import Coverage, CoverageReport
from sisense2ts.map.content import dashboard_to_tml
from sisense2ts.map.model import model_to_tml


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

"""WS-E coverage report rendering."""
from sisense2ts.ir.models import Coverage, CoverageReport
from sisense2ts.report.coverage import render_markdown


def _report():
    r = CoverageReport()
    r.add("widget", "Revenue Trend", Coverage.AUTO, "LINE_COLUMN")
    r.add("widget", "Top Diagnosis", Coverage.PARTIAL, "YoY badge dropped")
    return r


def test_meta_header_and_counts():
    md = render_markdown(_report(), "Coverage: Demo",
                         meta={"Source": "Sisense dashboard \"Demo\"",
                               "Target": "https://ts/#/pinboard/abc",
                               "Generated": "2026-06-30 12:00 UTC"})
    assert md.startswith("# Coverage: Demo")
    assert "- **Source:** Sisense dashboard \"Demo\"" in md
    assert "- **Target:** https://ts/#/pinboard/abc" in md
    assert "- **Generated:** 2026-06-30 12:00 UTC" in md
    assert "- Auto-converted: **1**" in md and "- Needs review: **1**" in md
    # problems sort first (REVIEW before OK)
    assert md.index("REVIEW") < md.index("| OK |")


def test_meta_omitted_is_backward_compatible():
    md = render_markdown(_report(), "Coverage: Demo")   # no meta -> no header block
    assert "**Source:**" not in md
    assert "- Auto-converted: **1**" in md

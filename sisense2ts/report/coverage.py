"""WS-E: render the coverage report.

The coverage report is a first-class deliverable, not an afterthought: in a PS
engagement it sets expectations about what converted automatically vs. what a
consultant must finish by hand. Every map/ workstream feeds CoverageItems into a
shared CoverageReport; this module renders it.
"""
from __future__ import annotations

from sisense2ts.ir.models import Coverage, CoverageReport

_ICON = {Coverage.AUTO: "OK", Coverage.PARTIAL: "REVIEW", Coverage.MANUAL: "MANUAL"}


def render_markdown(report: CoverageReport, title: str = "Conversion coverage") -> str:
    counts = report.counts()
    lines = [
        f"# {title}",
        "",
        f"- Auto-converted: **{counts['auto']}**",
        f"- Needs review: **{counts['partial']}**",
        f"- Manual: **{counts['manual']}**",
        "",
        "| Status | Type | Object | Note |",
        "|---|---|---|---|",
    ]
    order = {Coverage.MANUAL: 0, Coverage.PARTIAL: 1, Coverage.AUTO: 2}
    for it in sorted(report.items, key=lambda i: order[i.coverage]):
        note = (it.note or "").replace("|", "\\|")
        lines.append(f"| {_ICON[it.coverage]} | {it.object_type} | {it.name} | {note} |")
    return "\n".join(lines) + "\n"

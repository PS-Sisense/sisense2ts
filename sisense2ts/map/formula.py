"""WS-C: translate Sisense JAQL calculations and filters to ThoughtSpot TML.

STRATEGY: deterministically translate the common subset; emit everything else as a
MANUAL coverage item with the original Sisense formula preserved verbatim. Do NOT
chase the long tail (time-intelligence, RANK/ORDERING, measured-value scoping, R).
That long tail is intentionally out of scope for the June 26 demo.

This module is pure (IR in, TranslationResult out) and has no I/O, so it is the most
unit-testable piece. Write tests first against tests/fixtures and tests/test_formula.py.

Function-by-function mapping table, caveats, and worked examples:
.claude/skills/sisense-to-thoughtspot/refs/sisense-formula-translation.md
"""
from __future__ import annotations

import re

from sisense2ts.ir.models import Coverage, Formula, TranslationResult

# Sisense JAQL `agg` -> TML aggregation property (for SIMPLE measures, no formula).
AGG_MAP: dict[str, str] = {
    "sum": "SUM",
    "avg": "AVERAGE",
    "count": "COUNT",
    "countduplicates": "COUNT",   # approx (DupCount); flag PARTIAL
    "min": "MIN",
    "max": "MAX",
    "stdev": "STD_DEVIATION",
    "var": "VARIANCE",
    # median / stdevp / varp / mode have no clean TML aggregation -> MANUAL
}

# Sisense formula function -> TML formula function (deterministic subset only).
# Confident 1:1 mappings only. Full rationale + caveats:
# .claude/skills/sisense-to-thoughtspot/refs/sisense-formula-translation.md
FUNCTION_MAP: dict[str, str] = {
    # aggregation
    "sum": "sum",
    "avg": "average",
    "average": "average",
    "count": "count",
    "min": "min",
    "max": "max",
    # mathematical
    "abs": "abs",
    "round": "round",
    "ceiling": "ceil",
    "floor": "floor",
    "power": "pow",
    "sqrt": "sqrt",
    "exp": "exp",
    "mod": "mod",
    "log": "ln",       # Sisense `Log` is the NATURAL log (Sisense has no separate `Ln`)
    "ln": "ln",        # defensive alias if a JAQL variant uses `ln`
    "log10": "log10",
    "sign": "sign",
    # statistical (sample variants) -- confirmed in TS 26.6.0 formula reference
    "stdev": "stddev",
    "var": "variance",
    "median": "median",
    # logical / conditional -- confirmed in TS 26.6.0 formula reference
    "if": "if",
    "isnull": "isnull",    # TS spells it `isnull` (NOT `is_null`)
    "ifnull": "ifnull",
    # "case" -> handled specially (maps to nested if) -> PARTIAL; see _PARTIAL_FUNCS
}

# Functions we will NOT auto-translate for v1. Presence => MANUAL coverage.
# Unknown functions are MANUAL anyway; this set exists for clearer coverage-report notes
# and to guard names that look translatable but are not (e.g. population stats, R, window).
UNSUPPORTED: frozenset[str] = frozenset({
    # window / ranking
    "rank", "ordering", "rsum", "rpsum", "rpavg", "prev", "next", "all", "now",
    # time intelligence: period-to-date
    "ytdsum", "ytdavg", "mtdsum", "mtdavg", "qtdsum", "qtdavg", "wtdsum",
    # time intelligence: prior period
    "pastday", "pastweek", "pastmonth", "pastquarter", "pastyear",
    # time intelligence: growth / diff
    "growth", "growthrate", "diffpastyear", "diffpastmonth",
    "ydiff", "qdiff", "mdiff", "ddiff", "hdiff", "mndiff", "sdiff",
    # population / advanced statistics (no confident TML 1:1; percentile/quartile exist in
    # TS but arg semantics differ from Sisense -> keep MANUAL until verified)
    "stdevp", "varp", "mode", "largest", "smallest",
    "percentile", "quartile", "correl", "covar", "slope",
    # R integration
    "rdouble", "rint",
})


# Functions that translate but with a caveat worth a human review -> PARTIAL.
# "case" maps to a nested if; not a clean 1:1, so we flag it.
_PARTIAL_FUNCS: frozenset[str] = frozenset({"case"})

# identifier immediately followed by "(" -> a function call in the expression.
_FUNC_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")


def _column_from_dim(dim: str | None) -> str | None:
    """Sisense dim '[Orders.Revenue]' -> TML column ref '[Revenue]'.

    Strips the surrounding brackets and the 'Table.' qualifier, keeping the column's
    display name (spaces and all) wrapped in brackets the way TML formulas reference it.
    """
    if not dim:
        return None
    s = dim.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return "[" + s.split(".")[-1] + "]"


def _agg_to_func(agg: str) -> tuple[str | None, Coverage, str]:
    """A JAQL agg used as a formula wrapper -> (tml_func, coverage, note)."""
    key = (agg or "").lower()
    if key == "countduplicates":
        return "count", Coverage.PARTIAL, "countduplicates approximated as count"
    if key in FUNCTION_MAP:           # sum, avg->average, count, min, max
        return FUNCTION_MAP[key], Coverage.AUTO, ""
    return None, Coverage.MANUAL, f"no TML function for agg '{agg}'"


def _normalize_key(raw_key: str) -> str:
    """Context keys may be bracketed ('[rev]') or bare ('rev'); normalize to bare."""
    k = raw_key.strip()
    if k.startswith("[") and k.endswith("]"):
        k = k[1:-1]
    return k


def _manual(note: str, source: str) -> TranslationResult:
    return TranslationResult(expr=None, coverage=Coverage.MANUAL, note=note, source=source)


def translate_formula(formula: Formula) -> TranslationResult:
    """Translate a Sisense JAQL formula+context into a TML formula expression.

    Strategy (per pm/B1_brief.md):
      1. Resolve each `[key]` placeholder against the context. A `{dim, agg}` fragment
         becomes a column ref `[Column]` when the expression already wraps it in an
         aggregation, or `agg([Column])` when it appears bare. Nested `formula` fragments
         recurse.
      2. Map function names in the expression via FUNCTION_MAP.
      3. Any function in UNSUPPORTED (or unknown), or an unresolvable placeholder, makes
         the whole formula MANUAL (expr=None) with the offender noted.
      4. `case` / `countduplicates` -> PARTIAL with a caveat; otherwise AUTO.
    """
    source = formula.expression or ""
    expr = source
    coverage = Coverage.AUTO
    notes: list[str] = []

    def downgrade(level: Coverage, note: str = "") -> None:
        nonlocal coverage
        if note:
            notes.append(note)
        # MANUAL is the floor; PARTIAL only downgrades from AUTO.
        if level is Coverage.MANUAL or coverage is Coverage.AUTO:
            coverage = level

    # 1. Resolve context placeholders.
    for raw_key, frag in (formula.context or {}).items():
        key = _normalize_key(raw_key)
        token = "[" + key + "]"
        frag = frag if isinstance(frag, dict) else {}

        if frag.get("formula"):  # nested calc -> recurse
            sub = translate_formula(Formula(expression=str(frag["formula"]),
                                            context=frag.get("context") or {}))
            if sub.coverage is Coverage.MANUAL or sub.expr is None:
                return _manual(sub.note or f"unsupported nested formula for '{key}'", source)
            if sub.coverage is Coverage.PARTIAL:
                downgrade(Coverage.PARTIAL, sub.note)
            expr = expr.replace(token, "(" + sub.expr + ")")
            continue

        col = _column_from_dim(frag.get("dim"))
        if col is None:
            return _manual(f"cannot resolve placeholder '{key}' (no dim/formula)", source)

        # If the expression already aggregates the placeholder (e.g. "sum([rev])"),
        # substitute the bare column and let step 2 map that wrapping function. If it
        # appears bare, apply the context agg here.
        wrapped = re.search(r"[A-Za-z_]\w*\s*\(\s*" + re.escape(token) + r"\s*\)", source)
        agg = frag.get("agg")
        if wrapped or not agg:
            replacement = col
        else:
            fn, cov, note = _agg_to_func(agg)
            if fn is None:
                return _manual(note, source)
            downgrade(cov, note)
            replacement = f"{fn}({col})"
        expr = expr.replace(token, replacement)

    # 2/3. Inspect every function call in the (original) expression.
    for name in _FUNC_CALL.findall(source):
        low = name.lower()
        if low in UNSUPPORTED:
            return _manual(f"unsupported function '{name}'", source)
        if low in FUNCTION_MAP:
            continue
        if low in _PARTIAL_FUNCS:
            downgrade(Coverage.PARTIAL, f"'{name}' mapped with a caveat (review)")
            continue
        return _manual(f"unknown function '{name}'", source)

    # 3b. round() arg semantics diverge: TS's 2nd arg is a rounding INCREMENT
    # (round(x, .01) for 2 decimals), not Sisense's decimal-place COUNT (Round(x, 2)).
    # A 2-arg round would translate to the wrong number, so flag it for review.
    if re.search(r"\bround\s*\([^()]*,", source, re.IGNORECASE):
        downgrade(Coverage.PARTIAL,
                  "TS round() 2nd arg is a rounding increment, not a decimal-place count")

    # 4. Rename mapped functions in the resolved expression (e.g. ceiling->ceil, case->if).
    def _rename(m: re.Match) -> str:
        low = m.group(1).lower()
        if low == "case":
            return "if("
        return FUNCTION_MAP.get(low, m.group(1)) + "("

    expr = _FUNC_CALL.sub(_rename, expr)
    expr = re.sub(r"\s+", " ", expr).strip()

    return TranslationResult(expr=expr, coverage=coverage, note="; ".join(notes), source=source)


def translate_simple_agg(agg: str) -> TranslationResult:
    """Translate a plain JAQL `agg` (no formula) to a TML aggregation keyword."""
    key = (agg or "").lower()
    if key in AGG_MAP:
        cov = Coverage.PARTIAL if key == "countduplicates" else Coverage.AUTO
        return TranslationResult(expr=AGG_MAP[key], coverage=cov, source=agg)
    return TranslationResult(
        expr=None, coverage=Coverage.MANUAL,
        note=f"no TML aggregation for Sisense agg '{agg}'", source=agg,
    )

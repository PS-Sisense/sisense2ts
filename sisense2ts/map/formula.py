"""WS-C: translate Sisense JAQL calculations and filters to ThoughtSpot TML.

STRATEGY: deterministically translate the common subset; emit everything else as a
MANUAL coverage item with the original Sisense formula preserved verbatim. Do NOT
chase the long tail (time-intelligence, RANK/ORDERING, measured-value scoping, R).
That long tail is intentionally out of scope for the June 26 demo.

This module is pure (IR in, TranslationResult out) and has no I/O, so it is the most
unit-testable piece. Write tests first against tests/fixtures and tests/test_formula.py.
"""
from __future__ import annotations

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
# Seed list; WS-C extends as fixtures reveal more. Keep ONLY confident 1:1 mappings.
FUNCTION_MAP: dict[str, str] = {
    "sum": "sum",
    "avg": "average",
    "count": "count",
    "min": "min",
    "max": "max",
    "abs": "abs",
    "round": "round",
    "ceiling": "ceil",
    "floor": "floor",
    "power": "pow",
    "sqrt": "sqrt",
    "exp": "exp",
    "mod": "mod",
    "if": "if",
    "isnull": "is_null",
    # "case" -> handled specially (maps to nested if); see TODO below
}

# Functions we will NOT auto-translate for v1. Presence => MANUAL coverage.
UNSUPPORTED: frozenset[str] = frozenset({
    "rank", "ordering", "rsum", "prev", "next", "all", "now",
    "pastday", "pastweek", "pastmonth", "pastquarter", "pastyear",
    "growth", "growthrate", "diffpastyear", "diffpastmonth",
    "ytdsum", "ytdavg", "mtdsum", "qtdsum", "wtdsum", "rpsum", "rpavg",
    "rank", "percentile", "quartile", "correl", "covar", "slope",
    "rdouble", "rint",
})


def translate_formula(formula: Formula) -> TranslationResult:
    """Translate a Sisense JAQL formula+context into a TML formula expression.

    TODO(WS-C):
      1. Resolve context placeholders (e.g. "[users]") to their dim/agg, producing a
         flat expression over real column references.
      2. Tokenize the formula string; map function names via FUNCTION_MAP.
      3. If ANY token is in UNSUPPORTED (or unknown) -> Coverage.MANUAL, expr=None,
         note the offending function, source=formula.expression.
      4. Simple arithmetic + supported funcs only -> Coverage.AUTO.
      5. "case"/conditional or countduplicates -> Coverage.PARTIAL with a note.
    """
    raise NotImplementedError("WS-C: translate_formula")


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

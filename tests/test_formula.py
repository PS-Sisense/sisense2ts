"""WS-C starter tests. translate_simple_agg is already implemented (worked example).
translate_formula is the stub to build out; its xfail flips to pass when WS-C lands."""
import pytest

from sisense2ts.ir.models import Coverage, Formula
from sisense2ts.map.formula import translate_formula, translate_simple_agg


def test_simple_agg_supported():
    r = translate_simple_agg("sum")
    assert r.expr == "SUM" and r.coverage is Coverage.AUTO


def test_simple_agg_dupcount_is_partial():
    r = translate_simple_agg("countduplicates")
    assert r.coverage is Coverage.PARTIAL


def test_simple_agg_unsupported_is_manual():
    r = translate_simple_agg("median")
    assert r.coverage is Coverage.MANUAL and r.expr is None


@pytest.mark.xfail(reason="WS-C: translate_formula not implemented yet", strict=True)
def test_translate_simple_formula():
    # "Avg Order Value" = sum(Revenue) / count(Order ID)
    f = Formula(
        expression="sum([rev]) / count([ord])",
        context={"[rev]": {"dim": "[Orders.Revenue]", "agg": "sum"},
                 "[ord]": {"dim": "[Orders.Order ID]", "agg": "count"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.AUTO
    assert result.expr is not None

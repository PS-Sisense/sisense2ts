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


def test_translate_simple_formula():
    # "Avg Order Value" = sum(Revenue) / count(Order ID)
    f = Formula(
        expression="sum([rev]) / count([ord])",
        context={"[rev]": {"dim": "[Orders.Revenue]", "agg": "sum"},
                 "[ord]": {"dim": "[Orders.Order ID]", "agg": "count"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.AUTO
    assert result.expr == "sum([Revenue]) / count([Order ID])"


def test_ddiff_maps_to_diff_days_stripping_date_hierarchy():
    # Sisense Avg(DDiff(discharge, admission)) -> length of stay. DDiff -> diff_days, and the
    # date-hierarchy tag "(Calendar)" is stripped so the ref matches the base model column.
    f = Formula(
        expression="Avg(DDiff([disc],[adm]))",
        context={"[disc]": {"dim": "[Admissions.Discharge_Time (Calendar)]"},
                 "[adm]": {"dim": "[Admissions.Admission_Time(Calendar)]"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.AUTO
    assert result.expr == "average(diff_days([Discharge_Time],[Admission_Time]))"


def test_growthpastyear_is_manual():
    # time-intelligence (YoY growth) stays MANUAL with a clear note (not silently wrong)
    f = Formula(expression="GrowthPastYear([m])", context={"[m]": {"dim": "[Admissions.Cost_of_admission]"}})
    result = translate_formula(f)
    assert result.coverage is Coverage.MANUAL
    assert "growthpastyear" in (result.note or "").lower()


def test_translate_bare_placeholder_applies_context_agg():
    # Placeholders appear unaggregated in the expression; the context agg supplies it.
    f = Formula(
        expression="[rev] / [ord]",
        context={"rev": {"dim": "[Orders.Revenue]", "agg": "sum"},
                 "ord": {"dim": "[Orders.Order ID]", "agg": "count"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.AUTO
    assert result.expr == "sum([Revenue]) / count([Order ID])"


def test_translate_unbracketed_keys():
    # Real JAQL uses bare context keys referenced as [key]; must work the same.
    f = Formula(
        expression="sum([rev])",
        context={"rev": {"dim": "[Orders.Revenue]", "agg": "sum"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.AUTO
    assert result.expr == "sum([Revenue])"


def test_translate_unsupported_function_is_manual():
    # growth(...) is time-intelligence -> not auto-translated.
    f = Formula(
        expression="growth(sum([rev2]))",
        context={"[rev2]": {"dim": "[Orders.Revenue]", "agg": "sum"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.MANUAL
    assert result.expr is None
    assert "growth" in result.note
    assert result.source == "growth(sum([rev2]))"


def test_sisense_log_is_natural_log():
    # Sisense Log() is the natural logarithm -> TS ln() (NOT log10).
    f = Formula(expression="log([x])", context={"x": {"dim": "[T.Distance]"}})
    r = translate_formula(f)
    assert r.coverage is Coverage.AUTO
    assert r.expr == "ln([Distance])"


def test_round_single_arg_is_auto():
    f = Formula(expression="round([x])", context={"x": {"dim": "[T.Price]"}})
    assert translate_formula(f).coverage is Coverage.AUTO


def test_round_two_arg_is_partial():
    # TS round()'s 2nd arg is a rounding increment, not Sisense's decimal-place count.
    f = Formula(expression="round([x], 2)", context={"x": {"dim": "[T.Price]"}})
    r = translate_formula(f)
    assert r.coverage is Coverage.PARTIAL
    assert "increment" in r.note


def test_translate_countduplicates_is_partial():
    f = Formula(
        expression="[c] * 2",
        context={"c": {"dim": "[Orders.Order ID]", "agg": "countduplicates"}},
    )
    result = translate_formula(f)
    assert result.coverage is Coverage.PARTIAL
    assert result.expr == "count([Order ID]) * 2"

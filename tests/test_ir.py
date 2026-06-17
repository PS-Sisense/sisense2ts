"""Baseline tests for the frozen IR contract. These must always stay green:
if a change here breaks them, the contract changed and needs lead sign-off."""
from sisense2ts.ir import (
    Coverage,
    CoverageReport,
    DataType,
    Field,
    FieldKind,
    SourceColumn,
    SourceModel,
    SourceTable,
)


def test_build_model():
    m = SourceModel(
        name="Sample ECommerce",
        tables=[
            SourceTable(id="t_orders", name="Orders", columns=[
                SourceColumn(id="o_revenue", name="Revenue", data_type=DataType.DOUBLE),
            ]),
        ],
    )
    assert m.tables[0].columns[0].data_type is DataType.DOUBLE


def test_field_measure():
    f = Field(kind=FieldKind.MEASURE, dim="[Orders.Revenue]", agg="sum", title="Total Revenue")
    assert f.kind is FieldKind.MEASURE


def test_coverage_counts():
    r = CoverageReport()
    r.add("formula", "Avg Order Value", Coverage.AUTO)
    r.add("formula", "YoY Growth", Coverage.MANUAL, note="time-intelligence not supported")
    assert r.counts() == {"auto": 1, "partial": 0, "manual": 1}

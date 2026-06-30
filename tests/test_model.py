"""WS-B model_to_tml: physical Table TML + one Model TML, and duplicate-name disambiguation."""
from sisense2ts.ir.models import (
    DataType,
    JoinEndpoint,
    Relation,
    SourceColumn,
    SourceModel,
    SourceTable,
)
from sisense2ts.map.model import model_to_tml


def _col(name, dt=DataType.INT):
    return SourceColumn(id=name, name=name, data_type=dt)


def test_duplicate_column_name_binds_to_the_fact_table():
    # Patient_ID exists in both ER and Admissions; ER sorts first. The single exposed
    # "Patient_ID" model column must bind to Admissions (the most-connected/fact table) so
    # count([Patient_ID]) counts admissions, not the incidental ER rows. (regression: the old
    # first-seen dedup bound it to ER and silently undercounted.)
    er = SourceTable(id="ER", name="ER", columns=[_col("ID"), _col("Patient_ID")])
    adm = SourceTable(id="Admissions", name="Admissions",
                      columns=[_col("ID"), _col("Patient_ID"), _col("Cost", DataType.DOUBLE)])
    pat = SourceTable(id="Patients", name="Patients", columns=[_col("ID")])
    model = SourceModel(
        name="HC", tables=[er, adm, pat],   # ER first on purpose
        relations=[
            Relation(endpoints=[JoinEndpoint("Admissions", "Patient_ID"), JoinEndpoint("ER", "Patient_ID")]),
            Relation(endpoints=[JoinEndpoint("Admissions", "Patient_ID"), JoinEndpoint("Patients", "ID")]),
        ],
    )
    mcols = model_to_tml(model, "conn", "fqn", "db", "sch")["model"]["model"]["columns"]
    by_name = {c["name"]: c["column_id"] for c in mcols}
    assert by_name["Patient_ID"] == "Admissions::Patient_ID"   # fact, not ER
    assert by_name["ID"] == "Admissions::ID"                   # fact wins for the shared key too
    # still exactly one column per display name (the model requires unique names)
    names = [c["name"] for c in mcols]
    assert len(names) == len(set(names))

#!/usr/bin/env python3
"""Generate a meaningful Databricks data layer for the Sisense Sample Healthcare model.

Pulls the exact physical schema (db_table + db_column names, data types) from the converter
itself (map.model.model_to_tml), so the seeded tables are guaranteed to bind to the Model TML
the converter emits. Then fills the tables with realistic, FK-consistent healthcare data:
admissions across 2023-2024 (so the year-over-year KPIs move), costs and lengths-of-stay that
vary by diagnosis (so avg cost / avg days / the top-10 diagnosis pivot are meaningful), and
rooms spread across divisions (so "admissions by division" rolls up correctly).

    python scripts/gen_healthcare_sql.py            # writes sql/databricks_sample_healthcare.sql
    python sql/run_sql.py sql/databricks_sample_healthcare.sql

Deterministic (seeded) so re-runs reproduce the same numbers.
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from sisense2ts.extract import parse
from sisense2ts.extract.sisense_client import SisenseClient
from sisense2ts.map import model as M

random.seed(42)

_DBX_TYPE = {"INT64": "BIGINT", "DOUBLE": "DOUBLE", "VARCHAR": "STRING", "DATE_TIME": "TIMESTAMP",
             "DATE": "DATE", "BOOL": "BOOLEAN"}

# ---- the meaningful data ---------------------------------------------------------------
DIVISIONS = [(1, "Cardiology"), (2, "Oncology"), (3, "Orthopedics"),
             (4, "Pediatrics"), (5, "Neurology"), (6, "Emergency")]

DOCTORS = []  # 2 per division
_FN = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
       "David", "Elizabeth", "William", "Susan"]
_LN = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
       "Rodriguez", "Martinez", "Hernandez", "Lopez"]
_SPEC = {1: "Cardiologist", 2: "Oncologist", 3: "Orthopedic Surgeon",
         4: "Pediatrician", 5: "Neurologist", 6: "Emergency Physician"}
for i, (div_id, _) in enumerate(DIVISIONS):
    for k in range(2):
        did = i * 2 + k + 1
        DOCTORS.append((did, _FN[did - 1], _LN[did - 1], _SPEC[div_id], div_id))

ROOMS = []  # 3 per division
rid = 0
for div_id, _ in DIVISIONS:
    for r in range(3):
        rid += 1
        ROOMS.append((rid, div_id * 100 + r + 1, div_id, random.choice([1, 1, 2, 2, 4])))

# diagnosis: (id, description, typical_division, base_cost, stay_min, stay_max, weight, surgical)
DIAGNOSES = [
    (1,  "Hypertension",                 1,  8000, 1, 3,  9, False),
    (2,  "Type 2 Diabetes",              6, 14000, 2, 5,  7, False),
    (3,  "Pneumonia",                    6, 18000, 3, 7,  8, False),
    (4,  "Acute Myocardial Infarction",  1, 45000, 5, 10, 4, True),
    (5,  "Ischemic Stroke",              5, 40000, 6, 14, 4, False),
    (6,  "Femur Fracture",               3, 35000, 4, 9,  5, True),
    (7,  "Appendicitis",                 6, 22000, 2, 5,  5, True),
    (8,  "COPD Exacerbation",            6, 16000, 3, 6,  6, False),
    (9,  "Sepsis",                       6, 50000, 7, 16, 3, False),
    (10, "Asthma",                       4,  7000, 1, 3,  6, False),
    (11, "Kidney Stones",                6, 12000, 1, 3,  5, True),
    (12, "Migraine",                     5,  4000, 1, 2,  7, False),
    (13, "Influenza",                    4,  5000, 1, 2,  9, False),
    (14, "Cellulitis",                   6, 10000, 2, 5,  5, False),
    (15, "Urinary Tract Infection",      6,  6000, 1, 3,  7, False),
]
DX_BY_DIV = {}
for d in DIAGNOSES:
    DX_BY_DIV.setdefault(d[2], []).append(d)
ROOMS_BY_DIV = {}
for r in ROOMS:
    ROOMS_BY_DIV.setdefault(r[2], []).append(r[0])
DOCS_BY_DIV = {}
for dr in DOCTORS:
    DOCS_BY_DIV.setdefault(dr[4], []).append(dr[0])

PATIENTS = []  # 60
_GEN = ["Male", "Female"]
for pid in range(1, 61):
    PATIENTS.append((random.choice(_FN), random.choice(_LN),
                     f"19{random.randint(40,99)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                     pid, random.choice(_GEN)))

# admissions: 240, spread over 2023-2024, 2024 weighted heavier so YoY change is positive
DX_WEIGHTED = []
for d in DIAGNOSES:
    DX_WEIGHTED += [d] * d[6]
ADMISSIONS = []
for aid in range(1, 241):
    dx = random.choice(DX_WEIGHTED)
    div = dx[2]
    room = random.choice(ROOMS_BY_DIV[div])
    doctor = random.choice(DOCS_BY_DIV[div])
    patient = random.randint(1, 60)
    year = 2023 if random.random() < 0.45 else 2024          # ~55% in 2024 -> positive YoY
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    adm = datetime(year, month, day, random.randint(7, 20), random.choice([0, 15, 30, 45]))
    stay = random.randint(dx[4], dx[5])
    dis = adm + timedelta(days=stay, hours=random.randint(0, 12))
    cost = round(dx[3] * random.uniform(0.8, 1.3) + stay * random.uniform(200, 600), 2)
    surgical = "Yes" if dx[7] else ("Yes" if random.random() < 0.12 else "No")
    ADMISSIONS.append({
        "ID": aid, "Patient_ID": patient, "Diagnosis_ID": dx[0], "Room_ID": room,
        "Doctor_ID": doctor, "Admission_Time": adm, "Discharge_Time": dis,
        "HAI": "Yes" if random.random() < 0.09 else "No",
        "Surgical_Procedure": surgical,
        "SSI": "Yes" if random.random() < 0.05 else "No",
        "Cost_of_admission": cost,
        "Death": "Yes" if random.random() < 0.02 else "No",
    })

# ER: 12 minimal rows (not used by a widget, but the model references the table)
ER = []
for eid in range(1, 13):
    ci = datetime(2024, random.randint(1, 12), random.randint(1, 28), random.randint(0, 23))
    ER.append({"Patient_ID": random.randint(1, 60), "Diagnosis_ID": random.randint(1, 15),
               "ID": eid, "Check_in_time": ci, "Attendance_time": ci + timedelta(minutes=random.randint(10, 120)),
               "Date": ci})

# SQL-defined "Conditions time of stay" table: one row per diagnosis id
COND = []
for d in DIAGNOSES:
    COND.append({"ID": d[0], "Average_time_of_stay": (d[4] + d[5]) // 2,
                 "Positive": random.randint(5, 40), "Negative": random.randint(1, 20)})


def _lit(v, dtype):
    if v is None:
        return "NULL"
    if dtype == "TIMESTAMP":
        return "TIMESTAMP'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if dtype in ("STRING", "DATE"):
        return "'" + str(v).replace("'", "''") + "'"
    return str(v)


# logical-table name -> (rows as dicts keyed by db_column_name, OR tuple-rows aligned to col order)
def _rows_for(logical_name, columns):
    cols = [c["db_column_name"] for c in columns]
    if logical_name == "Divisions":
        return [dict(zip(cols, r)) for r in DIVISIONS]
    if logical_name == "Doctors":
        return [dict(zip(cols, r)) for r in DOCTORS]
    if logical_name == "Rooms":
        return [dict(zip(cols, r)) for r in ROOMS]
    if logical_name == "Patients":
        return [dict(zip(cols, r)) for r in PATIENTS]
    if logical_name == "Diagnosis":
        return [{"ID": d[0], "Description": d[1]} for d in DIAGNOSES]
    if logical_name == "Admissions":
        return ADMISSIONS
    if logical_name == "ER":
        return ER
    if {"Average_time_of_stay", "Positive", "Negative"} <= set(cols):   # the SQL table (hash name)
        return COND
    return []


def main():
    cfg = yaml.safe_load(open("config.yaml"))
    S, D = cfg["sisense"], cfg["databricks"]
    sis = SisenseClient(S["base_url"], S["token"])
    models = sis.list_datamodels()
    models = models if isinstance(models, list) else models.get("datamodels", [])
    mt = next(m for m in models if (m.get("title", "") or "") == "Sample Healthcare")
    sm = parse.parse_datamodel(sis.export_datamodel(mt["oid"]))
    mb = M.model_to_tml(sm, D["connection_name"], D["connection_fqn"], D["catalog"], D["schema"],
                        model_name="Sample Healthcare (Sisense)")

    out = ["-- Sample Healthcare data layer (Databricks) for the Sisense -> ThoughtSpot demo.",
           "-- GENERATED by scripts/gen_healthcare_sql.py (deterministic). Physical names mirror",
           "-- the converter's Model TML (db_table = table id lowercased; db_column = name_with_underscores).",
           "-- Run via: python sql/run_sql.py sql/databricks_sample_healthcare.sql",
           "", "CREATE SCHEMA IF NOT EXISTS sisense_demo;", "USE sisense_demo;", ""]

    for t in mb["tables"]:
        tt = t["table"]
        db_table, name, columns = tt["db_table"], tt["name"], tt["columns"]
        coldefs = ", ".join(f"`{c['db_column_name']}` {_DBX_TYPE.get(c['db_column_properties']['data_type'], 'STRING')}"
                            for c in columns)
        out.append(f"CREATE OR REPLACE TABLE {db_table} ({coldefs});")
        rows = _rows_for(name, columns)
        if not rows:
            out.append("")
            continue
        collist = ", ".join(f"`{c['db_column_name']}`" for c in columns)
        dtypes = [_DBX_TYPE.get(c["db_column_properties"]["data_type"], "STRING") for c in columns]
        names = [c["db_column_name"] for c in columns]
        vals = []
        for r in rows:
            vals.append("(" + ", ".join(_lit(r.get(n), dt) for n, dt in zip(names, dtypes)) + ")")
        # chunk inserts at 100 rows
        for i in range(0, len(vals), 100):
            chunk = ",\n  ".join(vals[i:i + 100])
            out.append(f"INSERT INTO {db_table} ({collist}) VALUES\n  {chunk};")
        out.append("")

    path = Path("sql/databricks_sample_healthcare.sql")
    path.write_text("\n".join(out))
    n_adm = len(ADMISSIONS)
    print(f"wrote {path}  ({len(mb['tables'])} tables, {n_adm} admissions)")


if __name__ == "__main__":
    main()

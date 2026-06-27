"""Phase 5 — parity gate: prove the migrated ThoughtSpot answer returns the SAME
numbers the source did.

A migration can validate and even render and still be wrong. This gate compares,
per metric, three reference points:

    A  Sisense  (source)   -> POST /api/datasources/{ds}/jaql        (optional leg)
    B  ThoughtSpot (target)-> POST /api/rest/2.0/searchdata
    C  warehouse (oracle)  -> Databricks SQL Statement Execution API

Both Sisense (Live) and ThoughtSpot read the SAME warehouse, so C is the common
ground truth: if B == C the migrated answer is correct. The gate anchors on
B vs C (no Sisense access needed) and treats the Sisense leg (A) as an optional
third comparison that runs only when a live source token is supplied. GREEN
requires every available leg to agree within tolerance.

The pure comparison core (`normalize`, `compare`) has no I/O and is unit-tested
in tests/test_parity.py; the `*_rows` helpers do the network calls.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

_CTX = ssl._create_unverified_context()  # internal cluster / warehouse certs


# --------------------------------------------------------------------------- #
# Spec + result
# --------------------------------------------------------------------------- #
@dataclass
class ParityCheck:
    """One metric to verify across tools.

    `dims` = number of leading group-by columns (0 = a scalar KPI total, 1 = a
    one-dimension breakdown like Revenue by Category). `ts_query` is the
    ThoughtSpot search string; `sql` is warehouse SQL returning the same
    `[dim,] measure` rows; `jaql` is an optional Sisense JAQL body for the third
    leg (skipped when no live source token).
    """
    label: str
    ts_query: str
    sql: str
    dims: int = 0
    jaql: Optional[dict] = None
    tolerance: float = 0.01


@dataclass
class ParityResult:
    label: str
    verdict: str                       # GREEN | RED | ERROR
    legs: dict = field(default_factory=dict)   # leg name -> "ok" | "skipped" | "<error>"
    mismatches: list = field(default_factory=list)  # human-readable diffs
    note: str = ""


# --------------------------------------------------------------------------- #
# Pure comparison core (unit-tested, no I/O)
# --------------------------------------------------------------------------- #
def normalize(rows: list, dims: int) -> dict:
    """Rows -> {key: float}. dims=0 collapses to a single {'(total)': value};
    dims=1 keys by the first (dimension) column. Values coerce via float(str())."""
    out: dict = {}
    if dims == 0:
        if rows and rows[0]:
            out["(total)"] = _num(rows[0][-1] if len(rows[0]) > 1 else rows[0][0])
        return out
    for r in rows or []:
        if r is None or len(r) < 2:
            continue
        out[str(r[0])] = _num(r[-1])
    return out


def compare(expected: dict, actual: dict, tolerance: float = 0.01) -> tuple[bool, list]:
    """Compare two {key: value} maps. Match when keys line up and every value is
    within `tolerance` (absolute, plus a tiny relative cushion). Returns
    (ok, mismatches[str])."""
    diffs: list = []
    for k in sorted(set(expected) | set(actual)):
        if k not in expected:
            diffs.append(f"{k}: missing on left, right={actual[k]}")
        elif k not in actual:
            diffs.append(f"{k}: left={expected[k]}, missing on right")
        else:
            a, b = expected[k], actual[k]
            if abs(a - b) > tolerance + abs(b) * 1e-4:
                diffs.append(f"{k}: {a} vs {b} (Δ{round(a - b, 4)})")
    return (not diffs), diffs


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


# --------------------------------------------------------------------------- #
# Network legs
# --------------------------------------------------------------------------- #
def _post(url: str, body: dict, headers: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json", **headers})
    return json.loads(urllib.request.urlopen(req, timeout=timeout, context=_CTX).read().decode())


def thoughtspot_rows(base_url: str, token: str, model_id: str, query: str) -> list:
    """B — run a search query on the model via /searchdata; return data_rows."""
    resp = _post(base_url.rstrip("/") + "/api/rest/2.0/searchdata",
                 {"query_string": query, "logical_table_identifier": model_id,
                  "data_format": "COMPACT", "record_size": 5000},
                 {"Authorization": "Bearer " + token})
    contents = resp.get("contents") or [{}]
    return contents[0].get("data_rows") or resp.get("data_rows") or []


def databricks_rows(dbx: dict, sql: str) -> list:
    """C — run SQL via the Databricks SQL Statement Execution API; return rows.
    Polls a cold warehouse the same way sql/run_sql.py does."""
    host = dbx["host"].rstrip("/").replace("http://", "https://")
    hdr = {"Authorization": "Bearer " + dbx["token"]}
    body = {"warehouse_id": dbx["warehouse_id"], "statement": sql, "catalog": dbx["catalog"],
            "schema": dbx["schema"], "wait_timeout": "50s", "disposition": "INLINE",
            "format": "JSON_ARRAY"}
    r = _post(host + "/api/2.0/sql/statements", body, hdr, timeout=70)
    state = (r.get("status") or {}).get("state")
    sid, tries = r.get("statement_id"), 0
    while state in ("PENDING", "RUNNING") and sid and tries < 40:
        time.sleep(3); tries += 1
        gr = urllib.request.Request(host + "/api/2.0/sql/statements/" + sid, headers=hdr)
        r = json.loads(urllib.request.urlopen(gr, timeout=60, context=_CTX).read().decode())
        state = (r.get("status") or {}).get("state")
    if state != "SUCCEEDED":
        raise RuntimeError(f"warehouse {state}: {(r.get('status') or {}).get('error')}")
    return (r.get("result") or {}).get("data_array") or []


def sisense_rows(base_url: str, token: str, datasource, jaql) -> list:
    """A — run JAQL against Sisense; return aggregated rows ([dim,] value).

    `datasource` is the Sisense datasource object ({title, ...}); `jaql` is the metadata
    list (one `{jaql: {...}}` per dimension/measure). The response `values` is a list of
    {data, text} cells for a scalar metric, or a list of rows (each a list of such cells);
    we extract `.data` from each cell into plain [[dim,] value] rows."""
    title = datasource.get("title") if isinstance(datasource, dict) else str(datasource)
    url = base_url.rstrip("/") + "/api/datasources/" + urllib.parse.quote(title) + "/jaql"
    metadata = jaql if isinstance(jaql, list) else (jaql or {}).get("metadata", [])
    resp = _post(url, {"datasource": datasource, "metadata": metadata}, {"Authorization": "Bearer " + token})
    out = []
    for v in resp.get("values") or []:
        if isinstance(v, list):
            out.append([c.get("data") if isinstance(c, dict) else c for c in v])
        elif isinstance(v, dict):
            out.append([v.get("data")])
        else:
            out.append([v])
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_check(check: ParityCheck, *, ts: dict, dbx: dict, sisense: Optional[dict] = None) -> ParityResult:
    """Run one check. `ts` = {base_url, token, model_id}; `dbx` = the databricks
    config block; `sisense` = {base_url, token, datasource} or None to skip leg A."""
    res = ParityResult(label=check.label, verdict="ERROR")
    try:
        wh = normalize(databricks_rows(dbx, check.sql), check.dims)
    except Exception as e:  # no oracle -> can't judge
        res.note = f"warehouse query failed: {e}"
        res.legs["warehouse"] = str(e)
        return res
    res.legs["warehouse"] = "ok"

    try:
        tsm = normalize(thoughtspot_rows(ts["base_url"], ts["token"], ts["model_id"], check.ts_query),
                        check.dims)
    except Exception as e:
        res.legs["thoughtspot"] = str(e)
        res.note = f"thoughtspot query failed: {e}"
        return res
    res.legs["thoughtspot"] = "ok"

    ok, diffs = compare(wh, tsm, check.tolerance)   # B vs C — the anchor
    res.mismatches = ["TS vs warehouse — " + d for d in diffs]

    if sisense and check.jaql:                      # optional A leg
        try:
            sis = normalize(sisense_rows(sisense["base_url"], sisense["token"],
                                         sisense["datasource"], check.jaql), check.dims)
            sok, sdiffs = compare(wh, sis, check.tolerance)
            res.legs["sisense"] = "ok"
            ok = ok and sok
            res.mismatches += ["Sisense vs warehouse — " + d for d in sdiffs]
        except Exception as e:
            res.legs["sisense"] = str(e)            # dead token, etc. -> skip, don't fail
    else:
        res.legs["sisense"] = "skipped"

    res.verdict = "GREEN" if ok else "RED"
    return res


def render(results: list) -> str:
    """A compact GREEN/RED report."""
    g = sum(1 for r in results if r.verdict == "GREEN")
    lines = [f"PARITY  {g}/{len(results)} GREEN", "=" * 52]
    for r in results:
        legs = " ".join(f"{k}={v if v in ('ok', 'skipped') else 'ERR'}" for k, v in r.legs.items())
        lines.append(f"[{r.verdict:5}] {r.label:28} {legs}")
        for m in r.mismatches:
            lines.append(f"          {m}")
        if r.note:
            lines.append(f"          note: {r.note}")
    return "\n".join(lines)


def all_green(results: list) -> bool:
    return bool(results) and all(r.verdict == "GREEN" for r in results)

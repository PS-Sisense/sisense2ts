"""Phase 5: the parity comparison core is pure (no I/O) and must be exact.
These run creds-free; the network legs are exercised live by scripts/verify_parity.py."""
from sisense2ts.verify import parity


def test_normalize_scalar_kpi():
    # dims=0 collapses a single aggregate row to one (total) key
    assert parity.normalize([[5315.0]], 0) == {"(total)": 5315.0}
    # tolerate a [label, value] shape too -> take the last column
    assert parity.normalize([["x", "5315.00"]], 0) == {"(total)": 5315.0}


def test_normalize_grouped():
    rows = [["Female", "2005.00"], ["Male", "3310.00"]]
    assert parity.normalize(rows, 1) == {"Female": 2005.0, "Male": 3310.0}


def test_compare_match_within_tolerance():
    ok, diffs = parity.compare({"Male": 3310.0}, {"Male": 3310.004}, tolerance=0.01)
    assert ok and diffs == []


def test_compare_flags_value_mismatch():
    ok, diffs = parity.compare({"Male": 3310.0}, {"Male": 3000.0})
    assert not ok and "Male" in diffs[0]


def test_compare_flags_missing_key():
    ok, diffs = parity.compare({"Male": 1.0, "Female": 2.0}, {"Male": 1.0})
    assert not ok and any("Female" in d for d in diffs)


def test_all_green():
    g = parity.ParityResult("a", "GREEN")
    r = parity.ParityResult("b", "RED")
    assert parity.all_green([g]) and not parity.all_green([g, r]) and not parity.all_green([])

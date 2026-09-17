"""Integration tests for reconcile(): the four-bucket comparison end to end."""

import pytest

from main import ReconciliationError, reconcile


def _write_csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture
def base_config():
    return {
        "key_column": "id",
        "numeric_tolerance": 0.01,
        "column_mapping": {},
    }


def test_clean_match_is_case_insensitive(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,name\n1,John")
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,john")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["clean"]) == 1
    assert len(results["mismatches"]) == 0


def test_field_mismatch_is_reported_per_field(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,amount\n1,100")
    b = _write_csv(tmp_path / "b.csv", "id,amount\n1,150")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["clean"]) == 0
    assert len(results["mismatches"]) == 1
    row = results["mismatches"].iloc[0]
    assert row["field"] == "amount"
    assert row["value_a"] == "100"
    assert row["value_b"] == "150"


def test_multiple_mismatched_fields_produce_multiple_rows(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,amount,notes\n1,100,foo")
    b = _write_csv(tmp_path / "b.csv", "id,amount,notes\n1,150,bar")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["mismatches"]) == 2
    assert set(results["mismatches"]["field"]) == {"amount", "notes"}


def test_only_in_a_and_only_in_b(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,name\n1,John\n2,Extra")
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,John\n3,New")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert list(results["only_in_a"]["id"]) == ["2"]
    assert list(results["only_in_b"]["id"]) == ["3"]


def test_duplicate_keys_are_excluded_from_pairing(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,name\n1,John\n1,Jane")
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,John")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["duplicates_a"]) == 2
    assert len(results["clean"]) == 0
    assert len(results["mismatches"]) == 0
    # A's key 1 is ambiguous and pulled out entirely, so B's (unambiguous)
    # key 1 has no clean counterpart left to pair against.
    assert list(results["only_in_b"]["id"]) == ["1"]


def test_column_mapping_renames_before_comparison(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,name\n1,John")
    b = _write_csv(tmp_path / "b.csv", "id,full_name\n1,John")
    config = {**base_config, "file_a": a, "file_b": b, "column_mapping": {"full_name": "name"}}
    results, _ = reconcile(config)
    assert len(results["clean"]) == 1


def test_numeric_tolerance_is_applied(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,amount\n1,99.995")
    b = _write_csv(tmp_path / "b.csv", "id,amount\n1,100.00")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b, "numeric_tolerance": 0.01})
    assert len(results["clean"]) == 1


def test_blank_fields_on_both_sides_count_as_clean(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,notes\n1,")
    b = _write_csv(tmp_path / "b.csv", "id,notes\n1,")
    results, _ = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["clean"]) == 1


def test_schema_only_columns_are_reported_not_compared(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "id,name,extra_a\n1,John,x")
    b = _write_csv(tmp_path / "b.csv", "id,name,extra_b\n1,John,y")
    results, schema_notes = reconcile({**base_config, "file_a": a, "file_b": b})
    assert len(results["clean"]) == 1
    assert schema_notes["only_in_a_columns"] == ["extra_a"]
    assert schema_notes["only_in_b_columns"] == ["extra_b"]


def test_missing_file_raises_reconciliation_error(tmp_path, base_config):
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,John")
    config = {**base_config, "file_a": str(tmp_path / "missing.csv"), "file_b": b}
    with pytest.raises(ReconciliationError, match="not found"):
        reconcile(config)


def test_missing_key_column_raises_reconciliation_error(tmp_path, base_config):
    a = _write_csv(tmp_path / "a.csv", "other,name\n1,John")
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,John")
    config = {**base_config, "file_a": a, "file_b": b}
    with pytest.raises(ReconciliationError, match="Key column"):
        reconcile(config)


def test_empty_file_raises_reconciliation_error(tmp_path, base_config):
    a = tmp_path / "a.csv"
    a.write_text("", encoding="utf-8")
    b = _write_csv(tmp_path / "b.csv", "id,name\n1,John")
    config = {**base_config, "file_a": str(a), "file_b": b}
    with pytest.raises(ReconciliationError, match="empty"):
        reconcile(config)

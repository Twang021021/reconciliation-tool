"""Spreadsheet reconciliation tool.

Compares two versions of the same tabular data (CSV or XLSX), pairs rows by
a key column, and sorts every row into one of four buckets: clean matches,
field-level mismatches, "only in A", and "only in B". Duplicate keys are
flagged separately since they break the 1:1 pairing this tool relies on.
"""

import os
import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG = {
    "file_a": "sample_data/file_a.csv",
    "file_b": "sample_data/file_b.csv",
    "key_column": "id",
    "numeric_tolerance": 0.01,
    # Maps a column name in file B to the equivalent column name in file A,
    # for cases where the same field is labeled differently in each file.
    "column_mapping": {
        "full_name": "name",
    },
    "output_dir": "output",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_file(path):
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    raise ValueError(f"Unsupported file type: {path}")


# ---------------------------------------------------------------------------
# Value normalization / comparison
# ---------------------------------------------------------------------------
_CURRENCY_PREFIX = re.compile(r"^[$€£]")


def is_blank(value):
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def try_parse_number(value):
    """Best-effort numeric parse, tolerant of currency/thousands formatting."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = _CURRENCY_PREFIX.sub("", value.strip()).replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def normalize_key(value):
    """Stable string form of a key value, so '1', ' 1 ', and 1.0 all match."""
    if is_blank(value):
        return None
    num = try_parse_number(value)
    if num is not None:
        return str(int(num)) if num == int(num) else str(num)
    return str(value).strip().lower()


def values_equal(a, b, tolerance):
    a_blank, b_blank = is_blank(a), is_blank(b)
    if a_blank and b_blank:
        return True
    if a_blank != b_blank:
        return False

    num_a, num_b = try_parse_number(a), try_parse_number(b)
    if num_a is not None and num_b is not None:
        return abs(num_a - num_b) <= tolerance

    return str(a).strip().lower() == str(b).strip().lower()


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
def _extract_side(df, suffix, original_columns, key):
    """Pull the suffixed columns from a one-sided merge result back into
    plain original column names, dropping merge bookkeeping columns."""
    cols = [c for c in original_columns if c != "__key__"]
    out = pd.DataFrame({col: df.get(f"{col}{suffix}", df.get(col)) for col in cols})
    return out.reset_index(drop=True)


def reconcile(config):
    df_a = load_file(config["file_a"])
    df_b = load_file(config["file_b"]).rename(columns=config["column_mapping"])

    key = config["key_column"]
    tolerance = config["numeric_tolerance"]

    df_a["__key__"] = df_a[key].map(normalize_key)
    df_b["__key__"] = df_b[key].map(normalize_key)

    dup_a_mask = df_a["__key__"].duplicated(keep=False) & df_a["__key__"].notna()
    dup_b_mask = df_b["__key__"].duplicated(keep=False) & df_b["__key__"].notna()

    duplicates_a = df_a[dup_a_mask].drop(columns="__key__")
    duplicates_b = df_b[dup_b_mask].drop(columns="__key__")

    clean_a = df_a[~dup_a_mask]
    clean_b = df_b[~dup_b_mask]

    common_cols = [c for c in df_a.columns if c in df_b.columns and c not in (key, "__key__")]
    only_in_a_cols = [c for c in df_a.columns if c not in df_b.columns and c != "__key__"]
    only_in_b_cols = [c for c in df_b.columns if c not in df_a.columns and c != "__key__"]

    merged = pd.merge(
        clean_a, clean_b, on="__key__", how="outer",
        suffixes=("_a", "_b"), indicator=True,
    )

    only_in_a = _extract_side(merged[merged["_merge"] == "left_only"], "_a", df_a.columns, key)
    only_in_b = _extract_side(merged[merged["_merge"] == "right_only"], "_b", df_b.columns, key)
    both = merged[merged["_merge"] == "both"]

    clean_rows = []
    mismatch_rows = []

    for _, row in both.iterrows():
        key_val = row.get(f"{key}_a", row.get(key))
        mismatched_fields = []
        for col in common_cols:
            col_a, col_b = f"{col}_a", f"{col}_b"
            val_a = row[col_a] if col_a in row else row[col]
            val_b = row[col_b] if col_b in row else row[col]
            if not values_equal(val_a, val_b, tolerance):
                mismatched_fields.append((col, val_a, val_b))

        if mismatched_fields:
            for col, val_a, val_b in mismatched_fields:
                mismatch_rows.append({
                    "key": key_val,
                    "field": col,
                    "value_a": val_a,
                    "value_b": val_b,
                })
        else:
            record = {"key": key_val}
            for col in common_cols:
                col_a = f"{col}_a"
                record[col] = row[col_a] if col_a in row else row[col]
            clean_rows.append(record)

    results = {
        "clean": pd.DataFrame(clean_rows),
        "mismatches": pd.DataFrame(mismatch_rows),
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "duplicates_a": duplicates_a,
        "duplicates_b": duplicates_b,
    }

    schema_notes = {
        "only_in_a_columns": only_in_a_cols,
        "only_in_b_columns": only_in_b_cols,
    }

    return results, schema_notes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_summary(results, schema_notes):
    print("=" * 60)
    print("RECONCILIATION SUMMARY")
    print("=" * 60)
    print(f"Clean matches:        {len(results['clean'])}")
    print(f"Field mismatches:     {len(results['mismatches'])} field-level diffs")
    print(f"Only in A:            {len(results['only_in_a'])}")
    print(f"Only in B:            {len(results['only_in_b'])}")
    print(f"Duplicate keys in A:  {len(results['duplicates_a'])} rows")
    print(f"Duplicate keys in B:  {len(results['duplicates_b'])} rows")

    if schema_notes["only_in_a_columns"]:
        print(f"\nColumns only in file A (not compared): {schema_notes['only_in_a_columns']}")
    if schema_notes["only_in_b_columns"]:
        print(f"Columns only in file B (not compared): {schema_notes['only_in_b_columns']}")

    if len(results["mismatches"]):
        print("\n--- Mismatches ---")
        print(results["mismatches"].to_string(index=False))

    if len(results["duplicates_a"]) or len(results["duplicates_b"]):
        print("\n--- Duplicate keys (excluded from pairing) ---")
        if len(results["duplicates_a"]):
            print("File A:")
            print(results["duplicates_a"].to_string(index=False))
        if len(results["duplicates_b"]):
            print("File B:")
            print(results["duplicates_b"].to_string(index=False))
    print("=" * 60)


def write_outputs(results, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for name, df in results.items():
        df.to_csv(os.path.join(output_dir, f"{name}.csv"), index=False)
    print(f"\nCSV reports written to: {output_dir}/")


def main():
    results, schema_notes = reconcile(CONFIG)
    print_summary(results, schema_notes)
    write_outputs(results, CONFIG["output_dir"])


if __name__ == "__main__":
    main()

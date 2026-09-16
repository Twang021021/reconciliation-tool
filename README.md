# Reconciliation Tool

A Python tool for reconciling two spreadsheets (CSV or XLSX) that are supposed
to represent the same data. It pairs rows by a key column and sorts every row
into one of four buckets:

- **Clean** — matched on key, all fields agree
- **Mismatches** — matched on key, one or more fields disagree
- **Only in A** — key exists in file A but not file B
- **Only in B** — key exists in file B but not file A

Duplicate keys within a single file are detected and excluded from pairing
(since a repeated key makes 1:1 matching ambiguous), and reported separately.

## Matching rules

Field comparison is not naive string equality:

- Numeric values are compared with a configurable tolerance, and are parsed
  leniently (`"100,000.00"` and `100000` are treated as equal).
- Text is trimmed of whitespace and compared case-insensitively.
- Blank/null values on both sides are treated as equal.

## Status

Core comparison logic and a formatted, multi-tab Excel report are both
implemented.

## Usage

```bash
python -m venv venv
venv\Scripts\activate      # or `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
python main.py
```

Edit the `CONFIG` dict at the top of `main.py` to point at your own files,
set the key column, numeric tolerance, and any column name mappings between
the two files.

## Output

Plain CSV files are written to `output/`: `clean.csv`, `mismatches.csv`,
`only_in_a.csv`, `only_in_b.csv`, `duplicates_a.csv`, `duplicates_b.csv`.

A formatted Excel workbook is also written to
`output/reconciliation_report.xlsx`, with one tab per bucket plus a Summary
tab with bucket counts:

- **Mismatches** — the differing `value_a`/`value_b` cells are highlighted.
- **Only in A / Only in B** — orphaned rows are shaded to flag them for review.
- **Duplicates A / Duplicates B** — duplicate-key rows are shaded to flag them
  for manual reconciliation, since duplicates are excluded from the
  automated pairing.
- **Clean** — unstyled, since there's nothing to flag.

All sheets have a bold header row and frozen top row for readability.

## Project structure

```
reconciliation-tool/
├── main.py           # core reconciliation logic
├── sample_data/       # example file_a.csv / file_b.csv for testing
├── requirements.txt
└── README.md
```

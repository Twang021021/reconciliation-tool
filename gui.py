"""Desktop GUI for the reconciliation tool.

A thin tkinter layer over reconcile(), write_outputs(), and
write_excel_report() from main.py - none of the core logic changes to
support this; it's just file pickers and save dialogs wired to the same
functions the CLI uses.
"""

import argparse
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from main import (
    CONFIG,
    ReconciliationError,
    parse_column_mapping,
    reconcile,
    write_excel_report,
    write_outputs,
)


class ReconciliationApp:
    def __init__(self, root):
        self.root = root
        root.title("Reconciliation Tool")
        root.geometry("600x560")
        root.minsize(560, 480)

        self.file_a = tk.StringVar(value="")
        self.file_b = tk.StringVar(value="")
        self.key_column = tk.StringVar(value=CONFIG["key_column"])
        self.tolerance = tk.StringVar(value=str(CONFIG["numeric_tolerance"]))
        self.column_mapping = tk.StringVar(
            value=",".join(f"{b}={a}" for b, a in CONFIG["column_mapping"].items())
        )
        self.status = tk.StringVar(value="Select two files to compare.")

        self._results = None
        self._schema_notes = None
        self._work_queue = queue.Queue()

        self._build_layout()

    def _build_layout(self):
        pad = {"padx": 10, "pady": 4}

        file_frame = ttk.LabelFrame(self.root, text="Files")
        file_frame.pack(fill="x", **pad)
        file_frame.columnconfigure(1, weight=1)
        self._file_row(file_frame, "File A (before):", self.file_a, 0)
        self._file_row(file_frame, "File B (after):", self.file_b, 1)

        settings_frame = ttk.LabelFrame(self.root, text="Settings")
        settings_frame.pack(fill="x", **pad)
        ttk.Label(settings_frame, text="Key column:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(settings_frame, textvariable=self.key_column, width=20).grid(
            row=0, column=1, sticky="w", pady=4
        )
        ttk.Label(settings_frame, text="Numeric tolerance:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(settings_frame, textvariable=self.tolerance, width=20).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(settings_frame, text="Column mapping (file_b=file_a):").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(settings_frame, textvariable=self.column_mapping, width=32).grid(
            row=2, column=1, sticky="w", pady=4
        )

        self.run_button = ttk.Button(self.root, text="Run Reconciliation", command=self._on_run)
        self.run_button.pack(pady=10)

        results_frame = ttk.LabelFrame(self.root, text="Results")
        results_frame.pack(fill="both", expand=True, **pad)
        self.results_text = tk.Text(results_frame, height=14, state="disabled", wrap="word")
        self.results_text.pack(fill="both", expand=True, padx=8, pady=8)

        save_frame = ttk.Frame(self.root)
        save_frame.pack(fill="x", **pad)
        self.save_csv_button = ttk.Button(
            save_frame, text="Save CSV Reports...", command=self._on_save_csv, state="disabled"
        )
        self.save_csv_button.pack(side="left", padx=4)
        self.save_excel_button = ttk.Button(
            save_frame, text="Save Excel Report...", command=self._on_save_excel, state="disabled"
        )
        self.save_excel_button.pack(side="left", padx=4)

        ttk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x", padx=10, pady=(0, 8))

    def _file_row(self, parent, label, var, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Browse...", command=lambda: self._browse(var)).grid(
            row=row, column=2, padx=8, pady=6
        )

    def _browse(self, var):
        path = filedialog.askopenfilename(
            title="Select a spreadsheet",
            filetypes=[("Spreadsheets", "*.csv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _on_run(self):
        if not self.file_a.get() or not self.file_b.get():
            messagebox.showerror("Missing files", "Select both File A and File B first.")
            return

        try:
            tolerance = float(self.tolerance.get())
        except ValueError:
            messagebox.showerror("Invalid tolerance", "Numeric tolerance must be a number.")
            return

        try:
            column_mapping = parse_column_mapping(self.column_mapping.get())
        except argparse.ArgumentTypeError as e:
            messagebox.showerror("Invalid column mapping", str(e))
            return

        config = dict(CONFIG)
        config["file_a"] = self.file_a.get()
        config["file_b"] = self.file_b.get()
        config["key_column"] = self.key_column.get().strip()
        config["numeric_tolerance"] = tolerance
        config["column_mapping"] = column_mapping

        self._set_running(True)
        self.status.set("Running...")
        threading.Thread(target=self._run_reconcile, args=(config,), daemon=True).start()
        self.root.after(100, self._poll_queue)

    def _run_reconcile(self, config):
        # Runs on a background thread so the window stays responsive on
        # large files; results are handed back via a queue rather than
        # touching widgets directly, since tkinter isn't thread-safe.
        try:
            results, schema_notes = reconcile(config)
            self._work_queue.put(("ok", results, schema_notes))
        except ReconciliationError as e:
            self._work_queue.put(("error", str(e)))
        except Exception as e:
            self._work_queue.put(("error", f"Unexpected error: {e}"))

    def _poll_queue(self):
        try:
            item = self._work_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_queue)
            return

        self._set_running(False)
        if item[0] == "ok":
            _, results, schema_notes = item
            self._results, self._schema_notes = results, schema_notes
            self._show_results(results, schema_notes)
            self.save_csv_button.state(["!disabled"])
            self.save_excel_button.state(["!disabled"])
            self.status.set("Done.")
        else:
            messagebox.showerror("Reconciliation failed", item[1])
            self.status.set("Failed.")

    def _set_running(self, running):
        self.run_button.state(["disabled"] if running else ["!disabled"])

    def _show_results(self, results, schema_notes):
        lines = [
            f"Clean matches:        {len(results['clean'])}",
            f"Field mismatches:     {len(results['mismatches'])} field-level diffs",
            f"Only in A:            {len(results['only_in_a'])}",
            f"Only in B:            {len(results['only_in_b'])}",
            f"Duplicate keys in A:  {len(results['duplicates_a'])} rows",
            f"Duplicate keys in B:  {len(results['duplicates_b'])} rows",
        ]
        if schema_notes["only_in_a_columns"]:
            lines.append(f"\nColumns only in file A (not compared): {schema_notes['only_in_a_columns']}")
        if schema_notes["only_in_b_columns"]:
            lines.append(f"Columns only in file B (not compared): {schema_notes['only_in_b_columns']}")
        if len(results["mismatches"]):
            lines.append("\nMismatches:")
            lines.append(results["mismatches"].to_string(index=False))

        self.results_text["state"] = "normal"
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", "\n".join(lines))
        self.results_text["state"] = "disabled"

    def _on_save_csv(self):
        directory = filedialog.askdirectory(title="Choose a folder for the CSV reports")
        if not directory:
            return
        write_outputs(self._results, directory)
        messagebox.showinfo("Saved", f"CSV reports written to:\n{directory}")

    def _on_save_excel(self):
        path = filedialog.asksaveasfilename(
            title="Save Excel report",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile="reconciliation_report.xlsx",
        )
        if not path:
            return
        write_excel_report(self._results, self._schema_notes, path)
        messagebox.showinfo("Saved", f"Excel report written to:\n{path}")


def main():
    root = tk.Tk()
    ReconciliationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

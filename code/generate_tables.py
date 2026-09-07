"""
generate_boundary_tables.py

Reads the Trial-1 representative histogram boundary CSVs produced by
histogram.py:

    results/id_boundaries_{N}.csv
    results/title_boundaries_{N}.csv

for N in {1000, 3000, 5000}, and prints a ready-to-paste LaTeX
`tabular` block for each one, matching the table format used in
report.tex (Section "Q2.3 Frequency Bucket Boundaries").

Usage:
    python generate_boundary_tables.py > boundary_tables.tex

Then copy the relevant table(s) from boundary_tables.tex into
report.tex, replacing the placeholder tables.
"""

import os
import pandas as pd

RESULTS_DIR = "results"
SAMPLE_SIZES = [1000, 3000, 5000]
COLUMNS = ["id", "title"]


def escape_latex(value):
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def make_table(column, sample_size):
    path = os.path.join(
        RESULTS_DIR,
        f"{column}_boundaries_{sample_size}.csv"
    )

    if not os.path.exists(path):
        return (
            f"% Could not find {path} -- run histogram.py first.\n"
        )

    df = pd.read_csv(path).sort_values("bucket")

    lines = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"\centering")
    lines.append(r"\small")

    if column == "id":
        lines.append(r"\begin{tabular}{rllr}")
    else:
        lines.append(r"\begin{tabular}{r p{4.5cm} p{4.5cm} r}")

    lines.append(r"\toprule")
    lines.append(
        r"\textbf{Bucket} & \textbf{Lower Boundary} & "
        r"\textbf{Upper Boundary} & \textbf{Distinct Values} \\"
    )
    lines.append(r"\midrule")

    for _, row in df.iterrows():
        lower = escape_latex(row["lower_boundary"])
        upper = escape_latex(row["upper_boundary"])
        n = int(row["number_of_values"])
        bucket = int(row["bucket"])
        lines.append(f"{bucket} & {lower} & {upper} & {n} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(
        f"\\caption{{Optimal {column} histogram boundaries for "
        f"{sample_size} samples (Trial 1, representative run)}}"
    )
    lines.append(r"\end{table}")
    lines.append("")

    return "\n".join(lines)


def main():
    for column in COLUMNS:
        for sample_size in SAMPLE_SIZES:
            print(f"% ---- {column} / {sample_size} ----")
            print(make_table(column, sample_size))


if __name__ == "__main__":
    main()
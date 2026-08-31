"""
q2_vertical_plots.py

Generates horizontal/exchanged-axes versions of the optimal serial histogram graphs
from the CSV files produced by histogram.py.

It reads:
    results/id_boundaries_1000.csv
    results/id_boundaries_3000.csv
    results/id_boundaries_5000.csv
    results/title_boundaries_1000.csv
    results/title_boundaries_3000.csv
    results/title_boundaries_5000.csv

It does NOT recompute the histogram. It only changes the visualization.

Exchanged format:
    X-axis = Frequency
    Y-axis = Value Set / Bucket Boundaries

For each bucket, the bar length is the bucket's average frequency,
which is the same quantity used by histogram.py for selectivity
estimation.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RESULTS_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "results")
)

OUTPUT_DIR = os.path.join(RESULTS_DIR, "vertical_histograms")

os.makedirs(OUTPUT_DIR, exist_ok=True)

SAMPLE_SIZES = [1000, 3000, 5000]
COLUMNS = ["id", "title"]


# ============================================================
# LABEL FORMATTING
# ============================================================

def format_value(value):
    """Make labels readable without unnecessary .0."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def make_bucket_label(row):
    lower = format_value(row["lower_boundary"])
    upper = format_value(row["upper_boundary"])

    if lower == upper:
        return lower

    return f"{lower} | {upper}"


# ============================================================
# READ HISTOGRAM
# ============================================================

def read_histogram(column, sample_size):
    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_boundaries_{sample_size}.csv"
    )

    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"\nCould not find:\n{filename}\n\n"
            "Run histogram.py first so that the boundary CSV files "
            "are generated."
        )

    df = pd.read_csv(filename)

    required_columns = {
        "bucket",
        "lower_boundary",
        "upper_boundary",
        "number_of_values",
        "frequency",
        "average_frequency",
        "variance",
        "bucket_cost",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"{filename} is missing columns: {sorted(missing)}"
        )

    return df.sort_values("bucket").reset_index(drop=True)


# ============================================================
# HISTOGRAM WITH EXCHANGED AXES
# ============================================================

def plot_vertical_histogram(column, sample_size):
    df = read_histogram(column, sample_size)

    labels = [
        make_bucket_label(row)
        for _, row in df.iterrows()
    ]

    frequencies = df["average_frequency"].astype(float)
    value_set_sizes = df["number_of_values"].astype(int)

    fig, ax = plt.subplots(figsize=(12, 10))

    positions = range(len(df))

    # --------------------------------------------------------
    # Horizontal bars (Exchanged Axes)
    #
    # X = average frequency
    # Y = value-set / bucket boundary
    # --------------------------------------------------------

    ax.barh(
        positions,
        frequencies,
        height=0.8
    )

    ax.set_xlabel("Frequency")
    ax.set_ylabel("Value Set / Bucket Boundaries")

    ax.set_title(
        f"Optimal Serial Histogram - {column} "
        f"({sample_size} samples, {len(df)} buckets)"
    )

    ax.set_yticks(list(positions))

    # Include n_i in the Y-axis label so the value-set size remains visible.
    tick_labels = [
        f"{label} (n={n})"
        for label, n in zip(labels, value_set_sizes)
    ]

    ax.set_yticklabels(
        tick_labels,
        fontsize=8
    )

    # Invert Y-axis so the first bucket stays at the top
    ax.invert_yaxis()

    ax.grid(
        axis="x",
        alpha=0.25
    )

    plt.subplots_adjust(
        left=0.25,
        right=0.95,
        top=0.92,
        bottom=0.08
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{column}_histogram_{sample_size}_vertical.png"
    )

    plt.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close()

    print(f"Generated: {output_file}")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("Assignment 1 - Optimal Serial Histograms (Exchanged Axes)")
    print("=" * 70)

    print()
    print(f"Reading histogram CSV files from:")
    print(RESULTS_DIR)

    print()
    print("Generating graphs...")

    for column in COLUMNS:
        for sample_size in SAMPLE_SIZES:
            plot_vertical_histogram(
                column,
                sample_size
            )

    print()
    print("=" * 70)
    print("ALL HISTOGRAMS GENERATED SUCCESSFULLY")
    print("=" * 70)

    print()
    print("Graphs are stored in:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
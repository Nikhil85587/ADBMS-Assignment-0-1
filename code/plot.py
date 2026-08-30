"""
q2_vertical_plots.py

Generates vertical versions of the optimal serial histogram graphs
from the CSV files produced by histogram.py.

It reads:
    results/id_boundaries_1000.csv
    results/id_boundaries_3000.csv
    results/id_boundaries_5000.csv
    results/title_boundaries_1000.csv
    results/title_boundaries_3000.csv
    results/title_boundaries_5000.csv

It does NOT recompute the histogram. It only changes the visualization.

Vertical format:
    X-axis = Value Set / Bucket Boundaries
    Y-axis = Frequency

For each bucket, the bar height is the bucket's average frequency,
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
# VERTICAL HISTOGRAM
# ============================================================

def plot_vertical_histogram(column, sample_size):
    df = read_histogram(column, sample_size)

    labels = [
        make_bucket_label(row)
        for _, row in df.iterrows()
    ]

    frequencies = df["average_frequency"].astype(float)
    value_set_sizes = df["number_of_values"].astype(int)

    # Wider figure for the 20 bucket labels.
    fig, ax = plt.subplots(figsize=(15, 8))

    positions = range(len(df))

    # --------------------------------------------------------
    # Vertical bars
    #
    # X = value-set / bucket boundary
    # Y = average frequency
    # --------------------------------------------------------

    ax.bar(
        positions,
        frequencies,
        width=0.8
    )

    ax.set_xlabel("Value Set / Bucket Boundaries")
    ax.set_ylabel("Frequency")

    ax.set_title(
        f"Optimal Serial Histogram - {column} "
        f"({sample_size} samples, {len(df)} buckets)"
    )

    ax.set_xticks(list(positions))

    # Include n_i in the label so the value-set size is visible.
    tick_labels = [
        f"{label}\n(n={n})"
        for label, n in zip(labels, value_set_sizes)
    ]

    ax.set_xticklabels(
        tick_labels,
        rotation=60,
        ha="right",
        fontsize=8
    )

    ax.grid(
        axis="y",
        alpha=0.25
    )

    plt.subplots_adjust(
        left=0.08,
        right=0.98,
        top=0.90,
        bottom=0.34
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
    print("Assignment 1 - Vertical Optimal Serial Histograms")
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
    print("ALL VERTICAL HISTOGRAMS GENERATED SUCCESSFULLY")
    print("=" * 70)

    print()
    print("Graphs are stored in:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()

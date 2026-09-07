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

    # NOTE: "number_of_values" is the count of DISTINCT domain values
    # (e.g. distinct titles) in this bucket, NOT the number of rows.
    # Labelling it "n_distinct" avoids it being misread as a row count,
    # since for skewed columns like "title" this can legitimately
    # exceed the nominal sample size (see the plot subtitle).
    if lower == upper:
        return f"{lower} (n_distinct={int(row['number_of_values'])})"

    return (
        f"{lower} \u2026 {upper} "
        f"(n_distinct={int(row['number_of_values'])})"
    )


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
# HISTOGRAM WITH VERTICAL BARS (TARGET STYLE)
# ============================================================

# Two alternating bar heights so that labels on adjacent (narrow)
# bars don't collide with each other.
BAR_HEIGHT_TALL = 1.00
BAR_HEIGHT_SHORT = 0.84

# Default matplotlib color cycle, reused/repeated across buckets so
# consecutive bars are visually distinct.
COLOR_CYCLE = plt.rcParams["axes.prop_cycle"].by_key()["color"]


def plot_vertical_histogram(column, sample_size):
    df = read_histogram(column, sample_size)

    labels = [
        make_bucket_label(row)
        for _, row in df.iterrows()
    ]

    value_set_sizes = df["number_of_values"].astype(float).tolist()

    n_buckets = len(df)

    # --------------------------------------------------------
    # Each bucket becomes one bar whose WIDTH is its number of
    # distinct values (value-set size). Bars are placed side by
    # side, left to right, in bucket order, so the X-axis is the
    # cumulative count of distinct values covered so far - this
    # reproduces the "Frequencies" axis look from the target image.
    # --------------------------------------------------------

    lefts = []
    cumulative = 0.0

    for n in value_set_sizes:
        lefts.append(cumulative)
        cumulative += n

    total_width = cumulative

    # Alternate bar heights so adjacent vertical labels stay legible
    heights = [
        BAR_HEIGHT_TALL if i % 2 == 0 else BAR_HEIGHT_SHORT
        for i in range(n_buckets)
    ]

    colors = [
        COLOR_CYCLE[i % len(COLOR_CYCLE)]
        for i in range(n_buckets)
    ]

    fig, ax = plt.subplots(figsize=(24, 10))

    ax.bar(
        lefts,
        heights,
        width=value_set_sizes,
        align="edge",
        color=colors,
        edgecolor="none"
    )

    # --------------------------------------------------------
    # Vertical bucket-boundary labels centered inside each bar
    # --------------------------------------------------------

    for left, width, height, label in zip(
        lefts, value_set_sizes, heights, labels
    ):
        ax.text(
            left + width / 2,
            height / 2,
            label,
            rotation=90,
            ha="center",
            va="center",
            fontsize=9
        )

    ax.set_xlim(0, total_width)
    ax.set_ylim(0, BAR_HEIGHT_TALL * 1.15)

    ax.set_xlabel("Frequencies", fontsize=12)
    ax.set_ylabel("Value Set", fontsize=12)

    # No meaningful scale on the Y-axis - bar height only alternates
    # for label readability, so hide the tick labels/marks.
    ax.set_yticks([])

    # --------------------------------------------------------
    # Build an accurate subtitle.
    #
    # For "id" these numbers always equal sample_size exactly
    # (id is the primary key: no duplicates).
    #
    # For "title", histogram.py grows the raw row count until at
    # least `sample_size` DISTINCT titles are found, so the actual
    # distinct-value / raw-row totals can be larger than the
    # nominal sample_size. Showing both avoids the plot title being
    # misread as "N rows were sampled".
    # --------------------------------------------------------

    actual_distinct_total = int(df["number_of_values"].sum())
    actual_row_total = int(df["frequency"].sum())

    if actual_distinct_total == sample_size and actual_row_total == sample_size:
        subtitle = f"{sample_size} samples, {n_buckets} buckets"
    else:
        subtitle = (
            f"target \u2265{sample_size} distinct values, "
            f"{actual_distinct_total} distinct values used, "
            f"{actual_row_total} raw rows sampled, "
            f"{n_buckets} buckets"
        )

    ax.set_title(
        f"Optimal Serial Histogram - {column} ({subtitle})",
        fontsize=14
    )

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    plt.tight_layout()

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
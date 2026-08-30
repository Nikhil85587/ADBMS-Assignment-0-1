"""
Assignment 1 - Q1
PostgreSQL Histogram Investigation

Generates:
    1. PostgreSQL histogram for title.id
    2. PostgreSQL histogram for title.title

The histogram boundaries are read directly from pg_stats.
"""

import os
import ast
import psycopg2
import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "job",
    "user": "postgres",
    "password": "nikhil@123456"
}

TABLE_NAME = "title"

# Output directory: ../results
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

os.makedirs(RESULTS_DIR, exist_ok=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def connect_database():
    print("Connecting to PostgreSQL...")

    conn = psycopg2.connect(**DB_CONFIG)

    print("Connected to PostgreSQL successfully!")

    return conn


# ============================================================
# GET POSTGRESQL STATISTICS
# ============================================================

def parse_pg_array(value):
    """
    Convert a PostgreSQL array returned as text into
    a Python list.

    Handles numeric arrays and text arrays.
    """

    if value is None:
        return []

    # psycopg2 may already return a Python list/tuple
    if isinstance(value, (list, tuple)):
        return list(value)

    value = value.strip()

    if not value.startswith("{") or not value.endswith("}"):
        raise ValueError(
            f"Unexpected PostgreSQL array format: {value[:100]}"
        )

    value = value[1:-1]

    if value == "":
        return []

    # --------------------------------------------------------
    # PostgreSQL arrays can contain quoted strings containing
    # commas, braces, etc.
    #
    # This parser handles the histogram format returned by
    # pg_stats.
    # --------------------------------------------------------

    result = []
    current = []
    quoted = False
    escaped = False

    for char in value:

        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if char == '"':
            quoted = not quoted
            continue

        if char == "," and not quoted:
            result.append("".join(current))
            current = []
        else:
            current.append(char)

    result.append("".join(current))

    return result


def get_pg_stats(conn, column_name):

    query = """
        SELECT
            attname,
            null_frac,
            n_distinct,
            most_common_vals,
            most_common_freqs,
            histogram_bounds,
            correlation
        FROM pg_stats
        WHERE tablename = %s
          AND attname = %s;
    """

    with conn.cursor() as cur:

        cur.execute(
            query,
            (TABLE_NAME, column_name)
        )

        row = cur.fetchone()

    if row is None:

        raise RuntimeError(
            f"No PostgreSQL statistics found for "
            f"{TABLE_NAME}.{column_name}"
        )

    # --------------------------------------------------------
    # Parse histogram bounds.
    # --------------------------------------------------------

    raw_bounds = row[5]

    histogram_bounds = parse_pg_array(
        raw_bounds
    )

    # --------------------------------------------------------
    # Convert ID boundaries to integers.
    # --------------------------------------------------------

    if column_name == "id":

        histogram_bounds = [
            int(value)
            for value in histogram_bounds
        ]

    # --------------------------------------------------------
    # Title boundaries remain strings.
    # --------------------------------------------------------

    else:

        histogram_bounds = [
            str(value)
            for value in histogram_bounds
        ]

    return {
        "attname": row[0],
        "null_frac": row[1],
        "n_distinct": row[2],
        "most_common_vals": row[3],
        "most_common_freqs": row[4],
        "histogram_bounds": histogram_bounds,
        "correlation": row[6],
    }
# ============================================================
# GET ACTUAL TABLE CARDINALITY
# ============================================================

def get_table_cardinality(conn):
    query = f"""
        SELECT COUNT(*)
        FROM {TABLE_NAME};
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


# ============================================================
# GET ACTUAL SELECTIVITY
# ============================================================

def get_actual_selectivity(conn):
    queries = {
        "title": """
            SELECT
                COUNT(*)::double precision
                / (SELECT COUNT(*) FROM title)
            FROM title
            WHERE title < 'Race';
        """,

        "id": """
            SELECT
                COUNT(*)::double precision
                / (SELECT COUNT(*) FROM title)
            FROM title
            WHERE id < 350000;
        """
    }

    results = {}

    with conn.cursor() as cur:
        for column, query in queries.items():
            cur.execute(query)
            results[column] = cur.fetchone()[0]

    return results


# ============================================================
# HISTOGRAM FREQUENCIES
# ============================================================

def compute_bucket_frequencies(
    conn,
    column_name,
    boundaries,
    total_rows
):
    """
    Estimate the frequency represented by each PostgreSQL
    histogram bucket.

    PostgreSQL's histogram is approximately equi-depth,
    so each bucket represents approximately the same number
    of rows.

    The histogram contains len(boundaries)-1 buckets.
    """

    number_of_buckets = (
        len(boundaries) - 1
    )

    if number_of_buckets <= 0:
        raise ValueError(
            "Histogram must contain at least two boundaries."
        )

    frequency = (
        1.0 / number_of_buckets
    )

    return [
        frequency
        for _ in range(number_of_buckets)
    ]
# ============================================================
# PLOT ID HISTOGRAM
# ============================================================

def plot_id_histogram(
    boundaries,
    frequencies
):

    boundaries = np.asarray(
        boundaries,
        dtype=float
    )

    midpoints = (
        boundaries[:-1]
        + boundaries[1:]
    ) / 2.0

    widths = (
        boundaries[1:]
        - boundaries[:-1]
    )

    plt.figure(
        figsize=(14, 7)
    )

    plt.bar(
        midpoints,
        frequencies,
        width=widths,
        align="center",
        edgecolor="black"
    )

    plt.xlabel(
        "ID Value"
    )

    plt.ylabel(
        "Approximate Frequency"
    )

    plt.title(
        "PostgreSQL Histogram for title.id"
    )

    plt.grid(
        axis="y",
        alpha=0.3
    )

    plt.tight_layout()

    output_path = os.path.join(
        RESULTS_DIR,
        "q1_id_histogram.png"
    )

    plt.savefig(
        output_path,
        dpi=300
    )

    plt.close()

    print(
        f"Saved: {output_path}"
    )
# ============================================================
# PLOT TITLE HISTOGRAM
# ============================================================

def plot_title_histogram(
    boundaries,
    frequencies
):

    x = np.arange(
        len(frequencies)
    )

    plt.figure(
        figsize=(14, 7)
    )

    plt.bar(
        x,
        frequencies,
        edgecolor="black"
    )

    plt.xlabel(
        "Histogram Bucket"
    )

    plt.ylabel(
        "Approximate Frequency"
    )

    plt.title(
        "PostgreSQL Histogram for title.title"
    )

    # --------------------------------------------------------
    # Show a small number of representative boundaries.
    # --------------------------------------------------------

    number_of_labels = 10

    positions = np.linspace(
        0,
        len(boundaries) - 1,
        number_of_labels,
        dtype=int
    )

    labels = []

    for position in positions:

        label = str(
            boundaries[position]
        )

        if len(label) > 25:
            label = label[:22] + "..."

        labels.append(label)

    # The last boundary belongs to the right edge,
    # so map it to the last x position.
    tick_positions = []

    for position in positions:

        if position >= len(frequencies):
            tick_positions.append(
                len(frequencies) - 1
            )
        else:
            tick_positions.append(position)

    plt.xticks(
        tick_positions,
        labels,
        rotation=45,
        ha="right"
    )

    plt.grid(
        axis="y",
        alpha=0.3
    )

    plt.tight_layout()

    output_path = os.path.join(
        RESULTS_DIR,
        "q1_title_histogram.png"
    )

    plt.savefig(
        output_path,
        dpi=300
    )

    plt.close()

    print(
        f"Saved: {output_path}"
    )
# ============================================================
# PRINT STATISTICS
# ============================================================

def print_statistics(column_name, stats):

    boundaries = stats["histogram_bounds"]

    print()
    print("-" * 70)
    print(f"PostgreSQL Statistics: {TABLE_NAME}.{column_name}")
    print("-" * 70)

    print(f"Null fraction: {stats['null_frac']}")
    print(f"n_distinct: {stats['n_distinct']}")
    print(f"Correlation: {stats['correlation']}")

    if boundaries is not None:

        print(f"Number of histogram boundaries: {len(boundaries)}")
        print(
            "Number of histogram buckets: "
            f"{len(boundaries) - 1}"
        )

        print(f"First boundary: {boundaries[0]}")
        print(f"Last boundary: {boundaries[-1]}")

    else:
        print("No histogram bounds available.")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("Assignment 1 - Q1 PostgreSQL Histogram Experiment")
    print("=" * 70)

    conn = connect_database()

    try:

        total_rows = get_table_cardinality(conn)

        print()
        print(f"Table cardinality: {total_rows:,}")

        # ----------------------------------------------------
        # Get PostgreSQL statistics
        # ----------------------------------------------------

        id_stats = get_pg_stats(conn, "id")
        title_stats = get_pg_stats(conn, "title")

        print_statistics("id", id_stats)
        print_statistics("title", title_stats)

        # ----------------------------------------------------
        # Histogram boundaries
        # ----------------------------------------------------

        id_boundaries = id_stats["histogram_bounds"]
        title_boundaries = title_stats["histogram_bounds"]

        if id_boundaries is None:
            raise RuntimeError(
                "PostgreSQL has no histogram for title.id."
            )

        if title_boundaries is None:
            raise RuntimeError(
                "PostgreSQL has no histogram for title.title."
            )

        # ----------------------------------------------------
        # Calculate frequencies
        # ----------------------------------------------------

        print()
        print("Computing ID histogram frequencies...")

        id_frequencies = compute_bucket_frequencies(
            conn,
            "id",
            id_boundaries,
            total_rows
        )

        print("Computing title histogram frequencies...")

        title_frequencies = compute_bucket_frequencies(
            conn,
            "title",
            title_boundaries,
            total_rows
        )

        # ----------------------------------------------------
        # Generate graphs
        # ----------------------------------------------------

        print()
        print("Generating Q1 graphs...")

        plot_id_histogram(
            id_boundaries,
            id_frequencies
        )

        plot_title_histogram(
            title_boundaries,
            title_frequencies
        )

        # ----------------------------------------------------
        # Actual selectivity
        # ----------------------------------------------------

        selectivity = get_actual_selectivity(conn)

        print()
        print("=" * 70)
        print("ACTUAL SELECTIVITY")
        print("=" * 70)

        print(
            f"title < 'Race': "
            f"{selectivity['title']:.12f}"
        )

        print(
            f"id < 350000: "
            f"{selectivity['id']:.12f}"
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("Q1 SUMMARY")
        print("=" * 70)

        print(
            f"ID histogram boundaries: "
            f"{len(id_boundaries)}"
        )

        print(
            f"ID histogram buckets: "
            f"{len(id_boundaries) - 1}"
        )

        print(
            f"Title histogram boundaries: "
            f"{len(title_boundaries)}"
        )

        print(
            f"Title histogram buckets: "
            f"{len(title_boundaries) - 1}"
        )

        print()
        print("Q1 graphs generated successfully!")

        print()
        print("Output files:")
        print(
            os.path.join(
                RESULTS_DIR,
                "q1_id_histogram.png"
            )
        )
        print(
            os.path.join(
                RESULTS_DIR,
                "q1_title_histogram.png"
            )
        )

    finally:
        conn.close()

        print()
        print("Database connection closed.")


if __name__ == "__main__":
    main()
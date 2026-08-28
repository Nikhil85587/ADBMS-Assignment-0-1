import os
import time
import numpy as np
import pandas as pd
import psycopg2
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}

TABLE_NAME = "title"

BUCKETS = 20
SAMPLE_SIZES = [1000, 3000, 5000]

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
# CARDINALITY
# ============================================================

def get_cardinality(conn):
    query = """
        SELECT COUNT(*)
        FROM title;
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


# ============================================================
# SAMPLING
# ============================================================

def get_sample(conn, column, sample_size):
    """
    Obtain a random sample of exactly sample_size rows.

    TABLESAMPLE SYSTEM is used to select a random collection of
    table pages. ORDER BY random() then randomly selects rows from
    that sampled population, and LIMIT gives the exact requested
    sample size.
    """

    sample_percentage = 1.0

    query = f"""
        SELECT {column}
        FROM title TABLESAMPLE SYSTEM ({sample_percentage})
        WHERE {column} IS NOT NULL
        ORDER BY random()
        LIMIT %s;
    """

    with conn.cursor() as cur:
        cur.execute(query, (sample_size,))
        rows = cur.fetchall()

    values = [row[0] for row in rows]

    if len(values) < sample_size:
        raise RuntimeError(
            f"TABLESAMPLE returned only {len(values)} rows, "
            f"but {sample_size} were required."
        )

    return values


# ============================================================
# HISTOGRAM CONSTRUCTION
# ============================================================

def build_equi_depth_histogram(values, num_buckets):
    """
    Build an equi-depth histogram.

    Every bucket attempts to contain approximately the same
    number of observations.
    """

    if len(values) == 0:
        raise ValueError("Cannot build histogram from empty data.")

    sorted_values = sorted(values)

    n = len(sorted_values)

    boundaries = []

    for i in range(num_buckets + 1):
        index = int(i * n / num_buckets)

        if index >= n:
            index = n - 1

        boundaries.append(sorted_values[index])

    # Make sure boundaries are monotonically non-decreasing.
    cleaned_boundaries = [boundaries[0]]

    for value in boundaries[1:]:
        if value >= cleaned_boundaries[-1]:
            cleaned_boundaries.append(value)
        else:
            cleaned_boundaries.append(cleaned_boundaries[-1])

    frequencies = []

    for i in range(num_buckets):
        lower_index = int(i * n / num_buckets)
        upper_index = int((i + 1) * n / num_buckets)

        frequency = upper_index - lower_index
        frequencies.append(frequency)

    return cleaned_boundaries, frequencies


# ============================================================
# NUMERIC HISTOGRAM SELECTIVITY
# ============================================================

def estimate_numeric_selectivity(
    value,
    boundaries,
    frequencies,
    sample_size
):
    """
    Estimate P(X < value) using a piecewise-linear histogram.

    For a value inside a bucket, assume values are uniformly
    distributed within that bucket.
    """

    if value <= boundaries[0]:
        return 0.0

    if value > boundaries[-1]:
        return 1.0

    for i in range(len(frequencies)):

        lower = boundaries[i]
        upper = boundaries[i + 1]

        bucket_frequency = frequencies[i]

        if value <= upper:

            cumulative = sum(frequencies[:i])

            if upper == lower:
                fraction = 1.0
            else:
                fraction = (value - lower) / (upper - lower)

            estimated_count = cumulative + (
                fraction * bucket_frequency
            )

            return estimated_count / sample_size

    return 1.0


# ============================================================
# TEXT HISTOGRAM SELECTIVITY
# ============================================================

def text_fraction_between(lower, upper, value):
    """
    Estimate the relative position of a textual value between
    two textual boundaries.

    Python string ordering follows lexicographical ordering,
    which is sufficient for the empirical histogram experiment.
    """

    if upper == lower:
        return 1.0

    if value <= lower:
        return 0.0

    if value >= upper:
        return 1.0

    # Text values do not have a meaningful arithmetic distance.
    #
    # Therefore use a rank-based approximation by treating the
    # character codes as a positional representation.
    #
    # This is only an interpolation assumption; the actual error
    # is measured against PostgreSQL's complete table distribution.

    def string_value(s):
        result = 0.0

        for char in s[:20]:
            result = result * 128.0 + ord(char)

        return result

    low_value = string_value(lower)
    high_value = string_value(upper)
    current_value = string_value(value)

    if high_value == low_value:
        return 0.5

    fraction = (
        (current_value - low_value)
        / (high_value - low_value)
    )

    return max(0.0, min(1.0, fraction))


def estimate_text_selectivity(
    value,
    boundaries,
    frequencies,
    sample_size
):
    """
    Estimate P(title < value) from the text histogram.
    """

    if value <= boundaries[0]:
        return 0.0

    if value > boundaries[-1]:
        return 1.0

    cumulative_frequency = 0

    for i in range(len(frequencies)):

        lower = boundaries[i]
        upper = boundaries[i + 1]

        if value <= upper:

            fraction = text_fraction_between(
                lower,
                upper,
                value
            )

            estimated_count = (
                cumulative_frequency
                + fraction * frequencies[i]
            )

            return estimated_count / sample_size

        cumulative_frequency += frequencies[i]

    return 1.0


# ============================================================
# GENERIC SELECTIVITY ESTIMATION
# ============================================================

def estimate_selectivity(
    value,
    boundaries,
    frequencies,
    sample_size,
    data_type
):

    if data_type == "numeric":
        return estimate_numeric_selectivity(
            value,
            boundaries,
            frequencies,
            sample_size
        )

    return estimate_text_selectivity(
        value,
        boundaries,
        frequencies,
        sample_size
    )


# ============================================================
# ACTUAL SELECTIVITY
# ============================================================

def actual_selectivity(conn, column, value, cardinality):
    """
    Calculate the actual selectivity from the complete table.

    This is deliberately NOT calculated from the sample.

    Selectivity:
        number of rows satisfying column < value
        ------------------------------------------------
                     total number of rows
    """

    query = f"""
        SELECT COUNT(*)
        FROM title
        WHERE {column} < %s;
    """

    with conn.cursor() as cur:
        cur.execute(query, (value,))
        count = cur.fetchone()[0]

    return count / cardinality

def estimate_selectivity_from_histogram(
    value,
    boundaries,
    frequencies,
    sample_size,
    data_type
):
    """
    Estimate selectivity P(X < value) using the histogram.

    At the boundaries, cumulative bucket frequencies are used.
    Within a numeric bucket, linear interpolation is used.

    For text values, interpolation is based only on the ordering
    of the strings. No arithmetic distance between strings is
    assumed.
    """

    if value <= boundaries[0]:
        return 0.0

    if value >= boundaries[-1]:
        return 1.0

    cumulative = 0

    for i in range(len(frequencies)):

        lower = boundaries[i]
        upper = boundaries[i + 1]

        frequency = frequencies[i]

        if value > upper:
            cumulative += frequency
            continue

        if value <= lower:
            return cumulative / sample_size

        # ----------------------------------------------------
        # Numeric column
        # ----------------------------------------------------

        if data_type == "numeric":

            if upper == lower:
                fraction = 0.5
            else:
                fraction = (
                    (value - lower)
                    / (upper - lower)
                )

            fraction = max(
                0.0,
                min(1.0, fraction)
            )

        # ----------------------------------------------------
        # Text column
        # ----------------------------------------------------

        else:

            # At this point the value is between two text
            # boundaries. We cannot subtract strings.
            #
            # Use the ordering position estimated from the
            # Unicode code-point representation.

            def string_score(s):
                score = 0.0

                for char in str(s)[:32]:
                    score = (
                        score * 128.0
                        + ord(char)
                    )

                return score

            low_score = string_score(lower)
            high_score = string_score(upper)
            value_score = string_score(value)

            if high_score == low_score:
                fraction = 0.5
            else:
                fraction = (
                    (value_score - low_score)
                    / (high_score - low_score)
                )

            fraction = max(
                0.0,
                min(1.0, fraction)
            )

        cumulative += frequency * fraction

        return cumulative / sample_size

    return 1.0
# ============================================================
# MAXIMUM SELECTIVITY ERROR
# ============================================================

def calculate_max_selectivity_error(
    conn,
    column,
    boundaries,
    frequencies,
    sample_size,
    cardinality,
    data_type
):
    """
    Calculate maximum selectivity error using fixed query values.

    The same query values are used for every sample size, making
    the errors directly comparable between 1000, 3000 and 5000
    samples.

    Query points are chosen from the full table at fixed
    selectivity levels: 5%, 10%, ..., 95%.
    """

    results = []

    # --------------------------------------------------------
    # Obtain fixed query values from the complete table.
    # --------------------------------------------------------

    query = f"""
        SELECT {column}
        FROM title
        WHERE {column} IS NOT NULL
        ORDER BY {column};
    """

    with conn.cursor() as cur:
        cur.execute(query)
        full_values = [row[0] for row in cur.fetchall()]

    if not full_values:
        raise RuntimeError(
            f"No non-null values found for {column}."
        )

    # Fixed percentile positions.
    percentiles = [
        i / 20
        for i in range(1, 20)
    ]

    query_values = []

    n = len(full_values)

    for p in percentiles:

        index = int(p * n)

        if index >= n:
            index = n - 1

        query_values.append(
            full_values[index]
        )

    # --------------------------------------------------------
    # Evaluate every fixed query value.
    # --------------------------------------------------------

    max_error = -1.0
    max_boundary = None

    for i, value in enumerate(query_values):

        estimated = estimate_selectivity_from_histogram(
            value,
            boundaries,
            frequencies,
            sample_size,
            data_type
        )

        actual = actual_selectivity(
            conn,
            column,
            value,
            cardinality
        )

        error = abs(
            estimated - actual
        )

        results.append({
            "query_percentile": percentiles[i] * 100,
            "query_value": value,
            "estimated_selectivity": estimated,
            "actual_selectivity": actual,
            "absolute_error": error
        })

        if error > max_error:
            max_error = error
            max_boundary = value

    return (
        max_error,
        max_boundary,
        results
    )
# ============================================================
# SAVE BOUNDARIES
# ============================================================

def save_boundaries(
    column,
    sample_size,
    boundaries,
    frequencies
):

    rows = []

    for i in range(len(frequencies)):

        rows.append({
            "bucket": i + 1,
            "lower_boundary": boundaries[i],
            "upper_boundary": boundaries[i + 1],
            "frequency": frequencies[i]
        })

    df = pd.DataFrame(rows)

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_boundaries_{sample_size}.csv"
    )

    df.to_csv(filename, index=False)

    return filename


# ============================================================
# SAVE ERROR DATA
# ============================================================

def save_error_data(
    column,
    sample_size,
    results
):

    df = pd.DataFrame(results)

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_errors_{sample_size}.csv"
    )

    df.to_csv(filename, index=False)

    return filename


# ============================================================
# HISTOGRAM PLOT
# ============================================================

def plot_histogram(
    column,
    sample_size,
    boundaries,
    frequencies
):

    labels = []

    for i in range(len(frequencies)):

        lower = str(boundaries[i])
        upper = str(boundaries[i + 1])

        labels.append(
            f"{lower}\n|\n{upper}"
        )

    plt.figure(figsize=(16, 8))

    plt.bar(
        range(len(frequencies)),
        frequencies
    )

    plt.xticks(
        range(len(frequencies)),
        labels,
        rotation=90,
        fontsize=7
    )

    plt.xlabel("Value boundaries")
    plt.ylabel("Frequency")
    plt.title(
        f"Serial Equi-Depth Histogram: "
        f"{column} ({sample_size} samples, "
        f"{BUCKETS} buckets)"
    )

    plt.tight_layout()

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_histogram_{sample_size}.png"
    )

    plt.savefig(filename, dpi=200)

    plt.close()

    return filename


# ============================================================
# SAMPLE SIZE VS TIME
# ============================================================

def plot_sample_size_vs_time(results_df):

    plt.figure(figsize=(9, 6))

    for column in ["id", "title"]:

        data = results_df[
            results_df["column"] == column
        ]

        plt.plot(
            data["sample_size"],
            data["build_time_seconds"],
            marker="o",
            label=column
        )

    plt.xlabel("Sample size")
    plt.ylabel("Histogram build time (seconds)")
    plt.title("Sample Size vs Histogram Build Time")
    plt.legend()
    plt.grid(True)

    filename = os.path.join(
        RESULTS_DIR,
        "sample_size_vs_time.png"
    )

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()

    return filename


# ============================================================
# SAMPLE SIZE VS ERROR
# ============================================================

def plot_sample_size_vs_error(results_df):

    plt.figure(figsize=(9, 6))

    for column in ["id", "title"]:

        data = results_df[
            results_df["column"] == column
        ]

        plt.plot(
            data["sample_size"],
            data["max_selectivity_error"],
            marker="o",
            label=column
        )

    plt.xlabel("Sample size")
    plt.ylabel("Maximum absolute selectivity error")
    plt.title(
        "Sample Size vs Maximum Selectivity Error"
    )

    plt.legend()
    plt.grid(True)

    filename = os.path.join(
        RESULTS_DIR,
        "sample_size_vs_error.png"
    )

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()

    return filename


# ============================================================
# LINEAR REGRESSION
# ============================================================

def extrapolate_full_table_time(
    sample_sizes,
    times,
    full_table_size
):

    x = np.array(sample_sizes, dtype=float)
    y = np.array(times, dtype=float)

    slope, intercept = np.polyfit(x, y, 1)

    estimated_time = (
        slope * full_table_size
        + intercept
    )

    return slope, intercept, estimated_time


# ============================================================
# MAIN EXPERIMENT
# ============================================================

def main():

    print("=" * 60)
    print("Assignment 1 - Serial Histogram Experiment")
    print("=" * 60)

    print(f"Buckets: {BUCKETS}")
    print(f"Sample sizes: {SAMPLE_SIZES}")
    print()

    conn = connect_database()

    cardinality = get_cardinality(conn)

    print(
        f"Title table cardinality: "
        f"{cardinality:,}"
    )

    print()

    all_results = []
    extrapolation_results = []

    for sample_size in SAMPLE_SIZES:

        print("-" * 60)
        print(
            f"Sampling {sample_size} rows..."
        )

        id_sample = get_sample(
            conn,
            "id",
            sample_size
        )

        title_sample = get_sample(
            conn,
            "title",
            sample_size
        )

        print(
            f"Actual ID sampled rows: "
            f"{len(id_sample):,}"
        )

        print(
            f"Actual title sampled rows: "
            f"{len(title_sample):,}"
        )

        # ----------------------------------------------------
        # ID HISTOGRAM
        # ----------------------------------------------------

        print()
        print("Building id histogram...")

        start = time.perf_counter()

        id_boundaries, id_frequencies = (
            build_equi_depth_histogram(
                id_sample,
                BUCKETS
            )
        )

        build_time = time.perf_counter() - start

        print(
            f"Build time: "
            f"{build_time:.6f} seconds"
        )

        id_error, id_boundary, id_error_results = (
            calculate_max_selectivity_error(
                conn,
                "id",
                id_boundaries,
                id_frequencies,
                len(id_sample),
                cardinality,
                "numeric"
            )
        )

        print(
            f"Maximum selectivity error: "
            f"{id_error:.6f}"
        )

        print(
            f"Maximum-error boundary: "
            f"{id_boundary}"
        )

        save_boundaries(
            "id",
            sample_size,
            id_boundaries,
            id_frequencies
        )

        save_error_data(
            "id",
            sample_size,
            id_error_results
        )

        plot_histogram(
            "id",
            sample_size,
            id_boundaries,
            id_frequencies
        )

        all_results.append({
            "column": "id",
            "sample_size": sample_size,
            "build_time_seconds": build_time,
            "max_selectivity_error": id_error
        })

        # ----------------------------------------------------
        # TITLE HISTOGRAM
        # ----------------------------------------------------

        print()
        print("Building title histogram...")

        start = time.perf_counter()

        title_boundaries, title_frequencies = (
            build_equi_depth_histogram(
                title_sample,
                BUCKETS
            )
        )

        build_time = time.perf_counter() - start

        print(
            f"Build time: "
            f"{build_time:.6f} seconds"
        )

        title_error, title_boundary, title_error_results = (
            calculate_max_selectivity_error(
                conn,
                "title",
                title_boundaries,
                title_frequencies,
                len(title_sample),
                cardinality,
                "text"
            )
        )

        print(
            f"Maximum selectivity error: "
            f"{title_error:.6f}"
        )

        print(
            f"Maximum-error boundary: "
            f"{title_boundary}"
        )

        save_boundaries(
            "title",
            sample_size,
            title_boundaries,
            title_frequencies
        )

        save_error_data(
            "title",
            sample_size,
            title_error_results
        )

        plot_histogram(
            "title",
            sample_size,
            title_boundaries,
            title_frequencies
        )

        all_results.append({
            "column": "title",
            "sample_size": sample_size,
            "build_time_seconds": build_time,
            "max_selectivity_error": title_error
        })

    # ========================================================
    # RESULTS TABLE
    # ========================================================

    results_df = pd.DataFrame(all_results)

    results_file = os.path.join(
        RESULTS_DIR,
        "experiment_results.csv"
    )

    results_df.to_csv(
        results_file,
        index=False
    )

    print()
    print("=" * 60)
    print("EXPERIMENT RESULTS")
    print("=" * 60)

    print(
        results_df.to_string(index=False)
    )

    # ========================================================
    # FULL TABLE EXTRAPOLATION
    # ========================================================

    print()
    print("=" * 60)
    print("FULL TABLE TIME EXTRAPOLATION")
    print("=" * 60)

    for column in ["id", "title"]:

        data = results_df[
            results_df["column"] == column
        ]

        slope, intercept, estimated_time = (
            extrapolate_full_table_time(
                data["sample_size"].values,
                data["build_time_seconds"].values,
                cardinality
            )
        )

        print()
        print(f"Column: {column}")
        print(f"Slope: {slope:.12f}")
        print(f"Intercept: {intercept:.12f}")
        print(
            f"Extrapolated full-table time: "
            f"{estimated_time:.6f} seconds"
        )

        extrapolation_results.append({
            "column": column,
            "slope": slope,
            "intercept": intercept,
            "full_table_cardinality": cardinality,
            "extrapolated_time_seconds": estimated_time
        })

    extrapolation_df = pd.DataFrame(
        extrapolation_results
    )

    extrapolation_file = os.path.join(
        RESULTS_DIR,
        "full_table_extrapolation.csv"
    )

    extrapolation_df.to_csv(
        extrapolation_file,
        index=False
    )

    # ========================================================
    # PLOTS
    # ========================================================

    plot_sample_size_vs_time(
        results_df
    )

    plot_sample_size_vs_error(
        results_df
    )

    # ========================================================
    # FINISH
    # ========================================================

    conn.close()

    print()
    print("=" * 60)
    print("ALL RESULTS GENERATED SUCCESSFULLY")
    print("=" * 60)

    print()
    print("Results are stored in:")
    print(RESULTS_DIR)


if __name__ == "__main__":
    main()
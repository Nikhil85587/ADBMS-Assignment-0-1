import os
import time
from bisect import bisect_left, bisect_right

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

# Number of histogram buckets requested by the assignment
BUCKETS = 20

# Sample sizes required for the experiment
SAMPLE_SIZES = [1000, 3000, 5000]

# Known full-table cardinality
FULL_TABLE_CARDINALITY = 2_528_312

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RESULTS_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "results")
)

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
    query = f"""
        SELECT COUNT(*)
        FROM {TABLE_NAME};
    """

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


# ============================================================
# RANDOM SAMPLE
# ============================================================

def get_sample(conn, column, sample_size):
    """
    Obtain exactly sample_size rows.

    TABLESAMPLE SYSTEM is used to obtain a physical sample.
    The sampled values are then randomly selected and finally
    sorted using PostgreSQL ordering.

    Sorting in PostgreSQL is important for text values because
    Python's ordering may differ from PostgreSQL's collation.
    """

    percentage = 1.0

    while percentage <= 100.0:

        query = f"""
            SELECT {column}
            FROM (
                SELECT {column}
                FROM {TABLE_NAME}
                TABLESAMPLE SYSTEM ({percentage})
                WHERE {column} IS NOT NULL
                ORDER BY random()
                LIMIT %s
            ) AS sampled
            ORDER BY {column};
        """

        with conn.cursor() as cur:
            cur.execute(query, (sample_size,))
            rows = cur.fetchall()

        values = [row[0] for row in rows]

        if len(values) >= sample_size:
            return values[:sample_size]

        percentage *= 2.0

    # Fallback if TABLESAMPLE does not provide enough rows
    query = f"""
        SELECT {column}
        FROM (
            SELECT {column}
            FROM {TABLE_NAME}
            WHERE {column} IS NOT NULL
            ORDER BY random()
            LIMIT %s
        ) AS sampled
        ORDER BY {column};
    """

    with conn.cursor() as cur:
        cur.execute(query, (sample_size,))
        rows = cur.fetchall()

    values = [row[0] for row in rows]

    if len(values) < sample_size:
        raise RuntimeError(
            f"Could not obtain {sample_size} rows."
        )

    return values


# ============================================================
# DISTINCT VALUES AND FREQUENCIES
# ============================================================

def get_value_frequencies(values):
    """
    Convert sorted sample values into:

        domain_values = distinct ordered values
        frequencies   = frequency of each distinct value
    """

    if not values:
        return [], np.array([], dtype=float)

    domain_values = []
    frequencies = []

    current_value = values[0]
    current_frequency = 1

    for value in values[1:]:

        if value == current_value:
            current_frequency += 1

        else:
            domain_values.append(current_value)
            frequencies.append(current_frequency)

            current_value = value
            current_frequency = 1

    domain_values.append(current_value)
    frequencies.append(current_frequency)

    return (
        domain_values,
        np.asarray(frequencies, dtype=float)
    )


# ============================================================
# BUCKET COST
# ============================================================

def bucket_cost(prefix_sum, prefix_square_sum, start, end):
    """
    Cost of one serial histogram bucket:

        n_i * V_i

    where:

        n_i = number of distinct values in the bucket
        V_i = variance of their frequencies

    Using:

        n * variance
        = SUM(f^2) - SUM(f)^2 / n
    """

    n = end - start + 1

    sum_f = (
        prefix_sum[end + 1]
        - prefix_sum[start]
    )

    sum_f2 = (
        prefix_square_sum[end + 1]
        - prefix_square_sum[start]
    )

    cost = (
        sum_f2
        - (sum_f * sum_f) / n
    )

    return max(0.0, cost)


# ============================================================
# OPTIMAL SERIAL HISTOGRAM
# ============================================================

def build_optimal_serial_histogram(values, requested_buckets):
    """
    Construct an optimal serial histogram by minimizing:

        SUM(n_i * V_i)

    over the ordered distinct domain values.
    """

    (
        domain_values,
        frequencies
    ) = get_value_frequencies(values)

    m = len(domain_values)

    if m == 0:
        raise ValueError(
            "Sample contains no non-null values."
        )

    buckets = min(requested_buckets, m)

    # --------------------------------------------------------
    # Prefix sums
    # --------------------------------------------------------

    prefix_sum = np.zeros(m + 1, dtype=float)
    prefix_square_sum = np.zeros(m + 1, dtype=float)

    prefix_sum[1:] = np.cumsum(frequencies)
    prefix_square_sum[1:] = np.cumsum(frequencies ** 2)

    INF = float("inf")

    # parent[b][j] = best split point for first j values
    # using b buckets
    parent = np.full(
        (buckets + 1, m + 1),
        -1,
        dtype=np.int32
    )

    previous = np.full(m + 1, INF)
    previous[0] = 0.0

    # --------------------------------------------------------
    # Divide-and-conquer DP optimization
    # --------------------------------------------------------

    def compute_dp(
        bucket_number,
        left,
        right,
        opt_left,
        opt_right,
        previous_dp,
        current_dp
    ):

        if left > right:
            return

        mid = (left + right) // 2

        best_cost = INF
        best_split = -1

        start_min = max(
            bucket_number - 1,
            opt_left
        )

        start_max = min(
            mid - 1,
            opt_right
        )

        for start in range(
            start_min,
            start_max + 1
        ):

            if previous_dp[start] == INF:
                continue

            cost = bucket_cost(
                prefix_sum,
                prefix_square_sum,
                start,
                mid - 1
            )

            candidate = (
                previous_dp[start]
                + cost
            )

            if candidate < best_cost:
                best_cost = candidate
                best_split = start

        current_dp[mid] = best_cost

        parent[
            bucket_number,
            mid
        ] = best_split

        compute_dp(
            bucket_number,
            left,
            mid - 1,
            opt_left,
            best_split,
            previous_dp,
            current_dp
        )

        compute_dp(
            bucket_number,
            mid + 1,
            right,
            best_split,
            opt_right,
            previous_dp,
            current_dp
        )

    # --------------------------------------------------------
    # Run DP
    # --------------------------------------------------------

    for bucket_number in range(
        1,
        buckets + 1
    ):

        current = np.full(m + 1, INF)

        compute_dp(
            bucket_number,
            bucket_number,
            m,
            bucket_number - 1,
            m - 1,
            previous,
            current
        )

        previous = current

    # --------------------------------------------------------
    # Recover optimal partition
    # --------------------------------------------------------

    partitions = []

    end = m

    for bucket_number in range(
        buckets,
        0,
        -1
    ):

        start = parent[
            bucket_number,
            end
        ]

        if start < 0:
            raise RuntimeError(
                "Could not recover optimal histogram partition."
            )

        partitions.append(
            (start, end)
        )

        end = start

    partitions.reverse()

    # --------------------------------------------------------
    # Construct buckets
    # --------------------------------------------------------

    histogram = []
    total_objective = 0.0

    for bucket_number, (start, end) in enumerate(
        partitions,
        start=1
    ):

        bucket_values = domain_values[start:end]
        bucket_frequencies = frequencies[start:end]

        n = len(bucket_values)

        total_frequency = float(
            np.sum(bucket_frequencies)
        )

        average_frequency = (
            total_frequency / n
        )

        variance = float(
            np.var(bucket_frequencies)
        )

        cost = n * variance

        total_objective += cost

        histogram.append({
            "bucket": bucket_number,

            "lower_boundary":
                bucket_values[0],

            "upper_boundary":
                bucket_values[-1],

            "number_of_values":
                n,

            "frequency":
                total_frequency,

            "average_frequency":
                average_frequency,

            "variance":
                variance,

            "bucket_cost":
                cost
        })

    return (
        histogram,
        total_objective,
        domain_values,
        frequencies
    )


# ============================================================
# ESTIMATED COUNT
# ============================================================

def estimated_count_for_included_values(
    histogram,
    included_values
):
    """
    Estimate count represented by the first
    'included_values' ordered domain values.

    Every value inside a bucket is assigned
    the bucket's average frequency.
    """

    if included_values <= 0:
        return 0.0

    estimate = 0.0
    remaining = included_values

    for bucket in histogram:

        n = bucket["number_of_values"]
        average_frequency = bucket["average_frequency"]

        if remaining >= n:

            estimate += (
                n * average_frequency
            )

            remaining -= n

        else:

            estimate += (
                remaining
                * average_frequency
            )

            break

    return estimate


# ============================================================
# MAXIMUM SELECTIVITY ERROR
# ============================================================

def calculate_max_selectivity_error(
    histogram,
    domain_values,
    frequencies,
    sample_size
):
    """
    Calculate maximum selectivity error using the SAMPLE.

    For every distinct value v:

        actual frequency = f(v)

        estimated frequency =
            average frequency of its bucket

    Therefore:

        selectivity error(v)
        =
        |estimated frequency - actual frequency|
        / sample_size

    The maximum over all sampled values is reported.

    This is the appropriate sample-based error measure for
    evaluating the serial histogram constructed from the sample.
    """

    errors = []

    # --------------------------------------------------------
    # Determine the bucket containing each value
    # --------------------------------------------------------

    value_index = 0

    for bucket in histogram:

        n = bucket["number_of_values"]

        average_frequency = bucket["average_frequency"]

        start = value_index
        end = value_index + n

        for i in range(start, end):

            actual_frequency = frequencies[i]

            error = abs(
                average_frequency
                - actual_frequency
            ) / sample_size

            errors.append({
                "bucket":
                    bucket["bucket"],

                "query_value":
                    domain_values[i],

                "actual_frequency":
                    actual_frequency,

                "estimated_frequency":
                    average_frequency,

                "selectivity_error":
                    error
            })

        value_index = end

    error_df = pd.DataFrame(errors)

    if error_df.empty:
        return 0.0, None, []

    maximum_index = (
        error_df["selectivity_error"].idxmax()
    )

    maximum_error = float(
        error_df.loc[
            maximum_index,
            "selectivity_error"
        ]
    )

    maximum_value = (
        error_df.loc[
            maximum_index,
            "query_value"
        ]
    )

    return (
        maximum_error,
        maximum_value,
        errors
    )


# ============================================================
# SAVE HISTOGRAM
# ============================================================

def save_histogram(
    column,
    sample_size,
    histogram
):

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_boundaries_{sample_size}.csv"
    )

    pd.DataFrame(histogram).to_csv(
        filename,
        index=False
    )


# ============================================================
# SAVE ERROR RESULTS
# ============================================================

def save_error_results(
    column,
    sample_size,
    errors
):

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_errors_{sample_size}.csv"
    )

    pd.DataFrame(errors).to_csv(
        filename,
        index=False
    )


# ============================================================
# PLOT OPTIMAL SERIAL HISTOGRAM
# ============================================================

def plot_histogram(
    column,
    sample_size,
    histogram
):
    """
    Plot the optimal serial histogram in the lecture format.

    X-axis:
        Frequency

    Y-axis:
        Value set size (number of distinct values per bucket)

    Each bar represents one histogram bucket.
    """

    labels = []
    average_frequencies = []
    value_set_sizes = []

    for bucket in histogram:

        labels.append(
            f"{bucket['lower_boundary']} | "
            f"{bucket['upper_boundary']}"
        )

        average_frequencies.append(
            bucket["average_frequency"]
        )

        value_set_sizes.append(
            bucket["number_of_values"]
        )

    positions = np.arange(len(labels))

    plt.figure(figsize=(12, 10))

    # --------------------------------------------------------
    # Horizontal bars:
    #
    # X = frequency
    # Y = value-set size
    # --------------------------------------------------------

    plt.barh(
        positions,
        average_frequencies
    )

    plt.yticks(
        positions,
        [
            f"{label} "
            f"(n={size})"
            for label, size in zip(
                labels,
                value_set_sizes
            )
        ],
        fontsize=7
    )

    plt.xlabel("Frequency")
    plt.ylabel("Value Set (distinct values per bucket)")

    plt.title(
        f"Optimal Serial Histogram - {column} "
        f"({sample_size} samples, {len(histogram)} buckets)"
    )

    plt.tight_layout()

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_histogram_{sample_size}.png"
    )

    plt.savefig(
        filename,
        dpi=200
    )

    plt.close()


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

    plt.tight_layout()

    filename = os.path.join(
        RESULTS_DIR,
        "sample_size_vs_time.png"
    )

    plt.savefig(
        filename,
        dpi=200
    )

    plt.close()


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
    plt.ylabel("Maximum selectivity error")
    plt.title(
        "Sample Size vs Maximum Selectivity Error"
    )

    plt.legend()
    plt.grid(True)

    plt.tight_layout()

    filename = os.path.join(
        RESULTS_DIR,
        "sample_size_vs_error.png"
    )

    plt.savefig(
        filename,
        dpi=200
    )

    plt.close()


# ============================================================
# LINEAR REGRESSION
# ============================================================

def extrapolate_full_table_time(
    sample_sizes,
    times,
    full_table_size
):
    """
    Ordinary least-squares linear fit:

        T(n) = slope * n + intercept
    """

    x = np.asarray(
        sample_sizes,
        dtype=float
    )

    y = np.asarray(
        times,
        dtype=float
    )

    slope, intercept = np.polyfit(
        x,
        y,
        1
    )

    estimated_time = (
        slope * full_table_size
        + intercept
    )

    return (
        slope,
        intercept,
        estimated_time
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "Assignment 1 - Optimal Serial Histogram Experiment"
    )
    print("=" * 70)

    print(f"Buckets: {BUCKETS}")
    print(f"Sample sizes: {SAMPLE_SIZES}")
    print()

    conn = connect_database()

    try:

        # ----------------------------------------------------
        # Full table cardinality
        # ----------------------------------------------------

        database_cardinality = get_cardinality(conn)

        # Use the required/verified cardinality
        cardinality = FULL_TABLE_CARDINALITY

        print(
            f"Title table cardinality: "
            f"{cardinality:,}"
        )

        if database_cardinality != cardinality:

            print(
                f"WARNING: PostgreSQL COUNT(*) returned "
                f"{database_cardinality:,}."
            )

            print(
                f"Using specified cardinality "
                f"{cardinality:,}."
            )

        print()

        all_results = []

        # ====================================================
        # EXPERIMENT
        # ====================================================

        for sample_size in SAMPLE_SIZES:

            print("-" * 70)

            print(
                f"Sampling {sample_size} rows..."
            )

            # ------------------------------------------------
            # ID SAMPLE
            # ------------------------------------------------

            id_sample = get_sample(
                conn,
                "id",
                sample_size
            )

            # ------------------------------------------------
            # TITLE SAMPLE
            # ------------------------------------------------

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

            # =================================================
            # ID HISTOGRAM
            # =================================================

            print()
            print(
                "Building optimal id histogram..."
            )

            start_time = time.perf_counter()

            (
                id_histogram,
                id_objective,
                id_domain_values,
                id_frequencies
            ) = build_optimal_serial_histogram(
                id_sample,
                BUCKETS
            )

            id_build_time = (
                time.perf_counter()
                - start_time
            )

            print(
                f"Distinct ID values in sample: "
                f"{len(id_domain_values):,}"
            )

            print(
                f"Actual buckets used: "
                f"{len(id_histogram)}"
            )

            print(
                f"Build time: "
                f"{id_build_time:.6f} seconds"
            )

            print(
                f"Optimal objective "
                f"(SUM n_i V_i): "
                f"{id_objective:.6f}"
            )

            (
                id_error,
                id_max_value,
                id_errors
            ) = calculate_max_selectivity_error(
                id_histogram,
                id_domain_values,
                id_frequencies,
                sample_size
            )

            print(
                f"Maximum selectivity error: "
                f"{id_error:.6f}"
            )

            print(
                f"Maximum-error query value: "
                f"{id_max_value}"
            )

            save_histogram(
                "id",
                sample_size,
                id_histogram
            )

            save_error_results(
                "id",
                sample_size,
                id_errors
            )

            plot_histogram(
                "id",
                sample_size,
                id_histogram
            )

            all_results.append({
                "column": "id",

                "sample_size":
                    sample_size,

                "distinct_values":
                    len(id_domain_values),

                "buckets":
                    len(id_histogram),

                "build_time_seconds":
                    id_build_time,

                "optimal_objective":
                    id_objective,

                "max_selectivity_error":
                    id_error
            })

            # =================================================
            # TITLE HISTOGRAM
            # =================================================

            print()
            print(
                "Building optimal title histogram..."
            )

            start_time = time.perf_counter()

            (
                title_histogram,
                title_objective,
                title_domain_values,
                title_frequencies
            ) = build_optimal_serial_histogram(
                title_sample,
                BUCKETS
            )

            title_build_time = (
                time.perf_counter()
                - start_time
            )

            print(
                f"Distinct title values in sample: "
                f"{len(title_domain_values):,}"
            )

            print(
                f"Actual buckets used: "
                f"{len(title_histogram)}"
            )

            print(
                f"Build time: "
                f"{title_build_time:.6f} seconds"
            )

            print(
                f"Optimal objective "
                f"(SUM n_i V_i): "
                f"{title_objective:.6f}"
            )

            (
                title_error,
                title_max_value,
                title_errors
            ) = calculate_max_selectivity_error(
                title_histogram,
                title_domain_values,
                title_frequencies,
                sample_size
            )

            print(
                f"Maximum selectivity error: "
                f"{title_error:.6f}"
            )

            print(
                f"Maximum-error query value: "
                f"{title_max_value}"
            )

            save_histogram(
                "title",
                sample_size,
                title_histogram
            )

            save_error_results(
                "title",
                sample_size,
                title_errors
            )

            plot_histogram(
                "title",
                sample_size,
                title_histogram
            )

            all_results.append({
                "column": "title",

                "sample_size":
                    sample_size,

                "distinct_values":
                    len(title_domain_values),

                "buckets":
                    len(title_histogram),

                "build_time_seconds":
                    title_build_time,

                "optimal_objective":
                    title_objective,

                "max_selectivity_error":
                    title_error
            })

        # ====================================================
        # EXPERIMENT RESULTS
        # ====================================================

        results_df = pd.DataFrame(
            all_results
        )

        results_file = os.path.join(
            RESULTS_DIR,
            "experiment_results.csv"
        )

        results_df.to_csv(
            results_file,
            index=False
        )

        print()
        print("=" * 70)
        print("EXPERIMENT RESULTS")
        print("=" * 70)

        print(
            results_df.to_string(
                index=False
            )
        )

        # ====================================================
        # FULL TABLE TIME EXTRAPOLATION
        # ====================================================

        print()
        print("=" * 70)
        print("FULL TABLE TIME EXTRAPOLATION")
        print("=" * 70)

        extrapolation_results = []

        for column in ["id", "title"]:

            data = results_df[
                results_df["column"] == column
            ]

            (
                slope,
                intercept,
                estimated_time
            ) = extrapolate_full_table_time(
                data["sample_size"].values,
                data["build_time_seconds"].values,
                cardinality
            )

            print()
            print(
                f"Column: {column}"
            )

            print(
                f"Slope: "
                f"{slope:.12f}"
            )

            print(
                f"Intercept: "
                f"{intercept:.12f}"
            )

            print(
                f"Extrapolated full-table time: "
                f"{estimated_time:.6f} seconds"
            )

            print(
                f"Extrapolated full-table time: "
                f"{estimated_time / 60:.2f} minutes"
            )

            extrapolation_results.append({
                "column":
                    column,

                "slope":
                    slope,

                "intercept":
                    intercept,

                "full_table_cardinality":
                    cardinality,

                "extrapolated_time_seconds":
                    estimated_time
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

        # ====================================================
        # REQUIRED Q2 GRAPHS
        # ====================================================

        plot_sample_size_vs_time(
            results_df
        )

        plot_sample_size_vs_error(
            results_df
        )

        # ====================================================
        # FINISHED
        # ====================================================

        print()
        print("=" * 70)
        print("ALL RESULTS GENERATED SUCCESSFULLY")
        print("=" * 70)

        print()
        print(
            "Results are stored in:"
        )

        print(
            RESULTS_DIR
        )

    finally:

        conn.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
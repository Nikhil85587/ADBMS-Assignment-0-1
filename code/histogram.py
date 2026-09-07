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

# Number of histogram buckets requested by the assignment
BUCKETS = 20

# The same Optimal Serial Histogram algorithm is used for both columns.
# For id, all frequencies are 1, so every partition has zero serial
# objective. The DP therefore uses an equal-depth tie-breaker to choose
# balanced buckets. For title, varying frequencies make the minimum-cost
# serial partition determine the bucket boundaries.

# Sample sizes required for the experiment
SAMPLE_SIZES = [1000, 3000, 5000]

# Number of independent trials (fresh random sample each time) to run
# per sample size. Build time and max selectivity error are averaged
# over these trials, since TABLESAMPLE + ORDER BY random() produces a
# different sample (and therefore a different histogram/error) on
# every run.
NUM_TRIALS = 3

# When expanding the raw title sample to reach the required number of
# distinct title values, grow the raw row count by this factor each
# retry.
TITLE_SAMPLE_GROWTH_FACTOR = 1.5

# Safety cap: never draw more than this multiple of the target
# distinct count when growing the title sample (avoids an infinite
# loop if the table simply does not contain enough distinct titles).
TITLE_SAMPLE_MAX_MULTIPLIER = 25

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
            values = values[:sample_size]

            # ---- Row check -------------------------------------
            # Confirm the number of rows actually fetched matches
            # the number of rows requested before returning.
            assert len(values) == sample_size, (
                f"Row check failed for column '{column}': "
                f"requested {sample_size} rows, "
                f"got {len(values)}."
            )

            print(
                f"  [row check] {column}: requested={sample_size}, "
                f"fetched={len(values)} -> OK"
            )

            return values

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

    values = values[:sample_size]

    # ---- Row check -------------------------------------------
    assert len(values) == sample_size, (
        f"Row check failed for column '{column}' (fallback path): "
        f"requested {sample_size} rows, got {len(values)}."
    )

    print(
        f"  [row check] {column}: requested={sample_size}, "
        f"fetched={len(values)} -> OK (fallback path)"
    )

    return values


# ============================================================
# TITLE SAMPLE
# ============================================================

def get_title_sample_with_distinct_target(conn, target_distinct):
    """
    Obtain a title sample containing exactly target_distinct DISTINCT
    title values. Duplicate rows are retained because their frequencies
    are required by the serial histogram.

    The nominal sample size for title therefore means the number of
    DISTINCT titles, not the number of raw rows. We repeatedly draw a
    larger random raw sample until it contains at least the requested
    number of distinct titles. If the candidate contains more than the
    target, exactly target_distinct title values are selected at random
    and all sampled duplicate rows belonging to those selected values
    are retained.

    Returns:
        values          - sorted raw sample, duplicates included
        raw_rows_drawn  - number of raw rows retained
        distinct_count  - exactly target_distinct
    """

    if target_distinct <= 0:
        raise ValueError("target_distinct must be positive.")

    raw_target = max(
        target_distinct,
        int(np.ceil(target_distinct * TITLE_SAMPLE_GROWTH_FACTOR))
    )

    max_raw_rows = int(
        target_distinct * TITLE_SAMPLE_MAX_MULTIPLIER
    )

    while raw_target <= max_raw_rows:

        candidate = get_sample(
            conn,
            "title",
            raw_target
        )

        candidate_distinct = list(dict.fromkeys(candidate))

        if len(candidate_distinct) < target_distinct:
            print(
                f"  [title distinct-check] candidate_raw_rows="
                f"{len(candidate)}, distinct_titles="
                f"{len(candidate_distinct)} < target={target_distinct}; "
                f"expanding raw sample."
            )

            raw_target = int(
                np.ceil(raw_target * TITLE_SAMPLE_GROWTH_FACTOR)
            )
            continue

        # The candidate contains enough distinct titles. Select exactly
        # target_distinct unique titles, then retain every occurrence of
        # those selected titles in the candidate. This preserves duplicate
        # frequencies while making the distinct count exact.
        if len(candidate_distinct) == target_distinct:
            selected_titles = set(candidate_distinct)
        else:
            selected_titles = set(
                np.random.choice(
                    np.asarray(candidate_distinct, dtype=object),
                    size=target_distinct,
                    replace=False
                ).tolist()
            )

        values = [
            value
            for value in candidate
            if value in selected_titles
        ]

        # candidate is already sorted according to PostgreSQL's ordering,
        # so filtering it preserves the database collation order.
        distinct_count = len(set(values))

        print(
            f"  [title distinct-check] target_distinct="
            f"{target_distinct}, raw_rows={len(values)}, "
            f"distinct_titles={distinct_count} -> OK"
        )

        # This is the correct check for the title experiment: the target
        # refers to DISTINCT values, while raw_rows may be larger because
        # duplicate title occurrences are intentionally retained.
        assert distinct_count == target_distinct, (
            f"Distinct-value check failed for 'title': expected "
            f"{target_distinct} distinct titles, got {distinct_count}."
        )

        assert len(values) >= target_distinct, (
            f"Raw-row check failed for 'title': need at least "
            f"{target_distinct} rows to contain {target_distinct} "
            f"distinct titles, got {len(values)}."
        )

        return values, len(values), distinct_count

    raise RuntimeError(
        f"Could not obtain {target_distinct} distinct title values "
        f"within the {TITLE_SAMPLE_MAX_MULTIPLIER}x raw-row safety cap."
    )


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
        best_balance = INF

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

            # Primary criterion: minimize the optimal serial
            # histogram objective SUM(n_i * V_i).
            #
            # Secondary criterion: if multiple partitions have the
            # same minimum objective, prefer a bucket size close to
            # the ideal equal-depth size m / requested_buckets.
            # This matters especially for id, where every frequency
            # is 1 and every valid partition has objective 0.
            bucket_size = mid - start
            ideal_size = m / buckets
            balance = abs(bucket_size - ideal_size)

            if (
                candidate < best_cost - 1e-12
                or (
                    abs(candidate - best_cost) <= 1e-12
                    and balance < best_balance
                )
            ):
                best_cost = candidate
                best_split = start
                best_balance = balance

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
# SAVE HISTOGRAM METADATA (sidecar file)
# ============================================================
#
# NOTE: for "id", raw_rows_sampled == distinct_values == sample_size,
# since id is the primary key.
#
# For "title", raw_rows_sampled can be larger than the nominal
# sample_size because sample_size is the DISTINCT-title target.
# Duplicate title values are retained because their frequencies are
# needed by the optimal serial histogram.

def save_histogram_metadata(
    column,
    sample_size,
    raw_rows_sampled,
    distinct_values,
    distinct_target=None
):

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_metadata_{sample_size}.csv"
    )

    pd.DataFrame([{
        "column": column,
        "target_sample_size": sample_size,
        "distinct_target": (
            distinct_target
            if distinct_target is not None
            else sample_size
        ),
        "raw_rows_sampled": raw_rows_sampled,
        "distinct_values_used": distinct_values,
    }]).to_csv(
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
# SAVE PER-TRIAL DETAIL (BEFORE AVERAGING)
# ============================================================

def save_trial_summary(column, sample_size, trial_records):
    """
    Persist the raw per-trial build_time / max_selectivity_error
    numbers (one row per trial) before they get averaged, so the
    averaging is fully auditable.
    """

    filename = os.path.join(
        RESULTS_DIR,
        f"{column}_trials_{sample_size}.csv"
    )

    pd.DataFrame(trial_records).to_csv(
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
    Plot the optimal serial histogram using vertical bars.

    X-axis: histogram bucket in sorted value order.
    Y-axis: average frequency of values in that bucket.
    """

    positions = np.arange(len(histogram))
    average_frequencies = [
        bucket["average_frequency"]
        for bucket in histogram
    ]

    labels = [
        f"{bucket['lower_boundary']} | {bucket['upper_boundary']}"
        for bucket in histogram
    ]

    plt.figure(figsize=(14, 8))
    plt.bar(positions, average_frequencies)

    plt.xticks(
        positions,
        [
            f"B{i+1}\n(n={bucket['number_of_values']})"
            for i, bucket in enumerate(histogram)
        ],
        fontsize=8
    )

    plt.xlabel("Histogram Bucket (sorted value order)")
    plt.ylabel("Average Frequency")
    plt.title(
        f"Optimal Serial Histogram - {column} "
        f"(target={sample_size} distinct titles, {len(histogram)} buckets)"
        if column == "title"
        else
        f"Optimal Serial Histogram - {column} "
        f"({sample_size} rows sampled, {len(histogram)} buckets)"
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
                f"Sample size (target): {sample_size}"
            )

            print(
                f"Running {NUM_TRIALS} independent trials "
                f"(fresh random sample each time) and averaging "
                f"build time / max selectivity error..."
            )

            id_trial_records = []
            title_trial_records = []

            # Full detail (histogram, errors, domain values) is kept
            # only for trial 1, which is saved/plotted as the
            # representative histogram for this sample size.
            id_trial1_detail = None
            title_trial1_detail = None

            for trial in range(1, NUM_TRIALS + 1):

                print()
                print(
                    f"  >> Trial {trial}/{NUM_TRIALS} "
                    f"(sample_size={sample_size})"
                )

                # =========================================
                # ID SAMPLE (exact row count == sample_size,
                # since id is the primary key -> no distinct-
                # value expansion needed)
                # =========================================

                id_sample = get_sample(
                    conn,
                    "id",
                    sample_size
                )

                # Row check (point 4)
                assert len(id_sample) == sample_size, (
                    f"Row check failed for 'id' trial {trial}: "
                    f"expected {sample_size}, got {len(id_sample)}"
                )

                # =========================================
                # TITLE SAMPLE (expand raw row count until the
                # sample contains >= title_distinct_target DISTINCT
                # titles, where title_distinct_target is at least
                # MIN_TITLE_DISTINCT_TARGET even if the nominal
                # sample_size for this run is smaller)
                # =========================================

                title_distinct_target = sample_size

                (
                    title_sample,
                    title_raw_rows,
                    title_distinct_found
                ) = get_title_sample_with_distinct_target(
                    conn,
                    sample_size
                )

                # Correct title checks: sample_size is the DISTINCT
                # title target. Raw rows may be larger because duplicate
                # title occurrences are intentionally retained.
                assert title_distinct_found == sample_size, (
                    f"Distinct-value check failed for 'title' trial {trial}: "
                    f"expected {sample_size} distinct titles, "
                    f"got {title_distinct_found}"
                )
                assert len(title_sample) >= sample_size, (
                    f"Raw-row check failed for 'title' trial {trial}: "
                    f"expected at least {sample_size} raw rows, "
                    f"got {len(title_sample)}"
                )

                # -----------------------------------------
                # ID HISTOGRAM
                # -----------------------------------------

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

                (
                    id_error,
                    id_max_value,
                    id_errors
                ) = calculate_max_selectivity_error(
                    id_histogram,
                    id_domain_values,
                    id_frequencies,
                    len(id_sample)
                )

                print(
                    f"     id    : build_time="
                    f"{id_build_time:.6f}s, "
                    f"buckets={len(id_histogram)}, "
                    f"max_sel_error={id_error:.6f}"
                )

                id_trial_records.append({
                    "trial": trial,
                    "sample_size": sample_size,
                    "raw_rows_sampled": len(id_sample),
                    "distinct_values": len(id_domain_values),
                    "buckets": len(id_histogram),
                    "build_time_seconds": id_build_time,
                    "optimal_objective": id_objective,
                    "max_selectivity_error": id_error,
                    "max_error_query_value": id_max_value
                })

                if trial == 1:
                    id_trial1_detail = {
                        "histogram": id_histogram,
                        "errors": id_errors
                    }

                # -----------------------------------------
                # TITLE HISTOGRAM
                # -----------------------------------------

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

                (
                    title_error,
                    title_max_value,
                    title_errors
                ) = calculate_max_selectivity_error(
                    title_histogram,
                    title_domain_values,
                    title_frequencies,
                    len(title_sample)
                )

                print(
                    f"     title : build_time="
                    f"{title_build_time:.6f}s, "
                    f"raw_rows={title_raw_rows}, "
                    f"distinct={title_distinct_found}, "
                    f"buckets={len(title_histogram)}, "
                    f"max_sel_error={title_error:.6f}"
                )

                title_trial_records.append({
                    "trial": trial,
                    "sample_size": sample_size,
                    "distinct_target": title_distinct_target,
                    "raw_rows_sampled": len(title_sample),
                    "distinct_values": len(title_domain_values),
                    "buckets": len(title_histogram),
                    "build_time_seconds": title_build_time,
                    "optimal_objective": title_objective,
                    "max_selectivity_error": title_error,
                    "max_error_query_value": title_max_value
                })

                if trial == 1:
                    title_trial1_detail = {
                        "histogram": title_histogram,
                        "errors": title_errors
                    }

            # =================================================
            # PERSIST PER-TRIAL DETAIL + REPRESENTATIVE HISTOGRAM
            # (trial 1) FOR THIS SAMPLE SIZE
            # =================================================

            save_trial_summary(
                "id", sample_size, id_trial_records
            )

            save_trial_summary(
                "title", sample_size, title_trial_records
            )

            save_histogram(
                "id", sample_size, id_trial1_detail["histogram"]
            )

            save_histogram_metadata(
                "id",
                sample_size,
                raw_rows_sampled=id_trial_records[0]["raw_rows_sampled"],
                distinct_values=id_trial_records[0]["distinct_values"]
            )

            save_error_results(
                "id", sample_size, id_trial1_detail["errors"]
            )

            plot_histogram(
                "id", sample_size, id_trial1_detail["histogram"]
            )

            save_histogram(
                "title", sample_size, title_trial1_detail["histogram"]
            )

            save_histogram_metadata(
                "title",
                sample_size,
                raw_rows_sampled=title_trial_records[0]["raw_rows_sampled"],
                distinct_values=title_trial_records[0]["distinct_values"],
                distinct_target=title_trial_records[0]["distinct_target"]
            )

            save_error_results(
                "title", sample_size, title_trial1_detail["errors"]
            )

            plot_histogram(
                "title", sample_size, title_trial1_detail["histogram"]
            )

            # =================================================
            # AVERAGE OVER THE NUM_TRIALS RUNS
            # =================================================

            id_trials_df = pd.DataFrame(id_trial_records)
            title_trials_df = pd.DataFrame(title_trial_records)

            id_avg_build_time = id_trials_df[
                "build_time_seconds"
            ].mean()

            id_avg_error = id_trials_df[
                "max_selectivity_error"
            ].mean()

            id_avg_objective = id_trials_df[
                "optimal_objective"
            ].mean()

            title_avg_build_time = title_trials_df[
                "build_time_seconds"
            ].mean()

            title_avg_error = title_trials_df[
                "max_selectivity_error"
            ].mean()

            title_avg_objective = title_trials_df[
                "optimal_objective"
            ].mean()

            title_avg_raw_rows = title_trials_df[
                "raw_rows_sampled"
            ].mean()

            print()
            print(
                f"  Averages over {NUM_TRIALS} trials "
                f"(sample_size={sample_size}):"
            )

            print(
                f"     id    : avg_build_time="
                f"{id_avg_build_time:.6f}s, "
                f"avg_max_sel_error={id_avg_error:.6f}"
            )

            print(
                f"     title : avg_build_time="
                f"{title_avg_build_time:.6f}s, "
                f"avg_raw_rows={title_avg_raw_rows:.1f}, "
                f"avg_max_sel_error={title_avg_error:.6f}"
            )

            all_results.append({
                "column": "id",

                "sample_size":
                    sample_size,

                "distinct_values":
                    id_trial_records[0]["distinct_values"],

                "buckets":
                    id_trial_records[0]["buckets"],

                "build_time_seconds":
                    id_avg_build_time,

                "optimal_objective":
                    id_avg_objective,

                "max_selectivity_error":
                    id_avg_error,

                "num_trials":
                    NUM_TRIALS,

                "avg_raw_rows_sampled":
                    sample_size
            })

            all_results.append({
                "column": "title",

                "sample_size":
                    sample_size,

                "distinct_values":
                    title_trial_records[0]["distinct_values"],

                "buckets":
                    title_trial_records[0]["buckets"],

                "build_time_seconds":
                    title_avg_build_time,

                "optimal_objective":
                    title_avg_objective,

                "max_selectivity_error":
                    title_avg_error,

                "num_trials":
                    NUM_TRIALS,

                "avg_raw_rows_sampled":
                    title_avg_raw_rows
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

            # For id, the nominal sample size equals the raw rows processed.
            # For title, sample_size is the DISTINCT-title target, while
            # the actual raw workload is larger because duplicate rows are
            # retained. Therefore regression must use the measured average
            # raw rows for title.
            if column == "title":
                x_values = data["avg_raw_rows_sampled"].values
            else:
                x_values = data["sample_size"].values

            (
                slope,
                intercept,
                estimated_time
            ) = extrapolate_full_table_time(
                x_values,
                data["build_time_seconds"].values,
                cardinality
            )

            print()
            print(
                f"Column: {column}"
            )

            if column == "title":
                print(
                    "Regression x-variable: average raw rows processed "
                    "to obtain the distinct-title target"
                )
            else:
                print(
                    "Regression x-variable: sample_size "
                    "(raw rows processed)"
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
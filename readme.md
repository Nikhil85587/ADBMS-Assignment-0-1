# Assignment 1 - Histogram

## Overview

This assignment studies PostgreSQL histograms and implements a custom
serial equi-depth histogram using samples from the `title` table of the
Join Order Benchmark (2013 Snapshot).

The experiment covers:

- PostgreSQL's built-in histograms for `id` and `title`
- Custom serial histogram construction
- Different sample sizes
- Histogram construction time
- Selectivity estimation error
- Full-table time extrapolation
- Visualization of histograms and experimental results

---

## Database

**Database:** Join Order Benchmark (2013 Snapshot)

**Main table:** `title`

**Cardinality:** 2,528,312 rows

**PostgreSQL Version:** 18.1

---

## Project Structure

```text
Assignment-1/
│
├── ADBMS_Assignment_0.pdf
├── ADBMS_Assignment_1.pdf
│
├── code/
│   ├── histogram.py
│   └── q1_plots.py
│
└── results/
    └── ...
```

### `ADBMS_Assignment_0.pdf`

Contains the complete assignment-0 report.
### `ADBMS_Assignment_1.pdf`

Contains the complete assignment-1 report.

### `code/histogram.py`

Python implementation for Q2. It:

1. Connects to PostgreSQL.
2. Samples the `title` table using `TABLESAMPLE`.
3. Creates serial equi-depth histograms.
4. Measures histogram construction time.
5. Calculates maximum selectivity error.
6. Repeats the experiment for sample sizes 1000, 3000 and 5000.
7. Performs linear regression for full-table time extrapolation.
8. Generates result files and plots.

### `code/q1_plots.py`

Extracts PostgreSQL histogram boundaries from `pg_stats` and generates
the Q1 histogram visualizations for the `id` and `title` columns.

Generated files:

```text
q1_id_histogram.png
q1_title_histogram.png
```

### `results/`

Contains the generated experimental results and plots.

---

## Requirements

The experiment was conducted using Python 3.11.

Required Python packages:

```text
psycopg2-binary
pandas
matplotlib
numpy
```

Install them using:

```bash
pip install psycopg2-binary pandas matplotlib numpy
```

---

## Software Versions

```text
Python       3.11.9
PostgreSQL   18.1
pandas       2.2.3
matplotlib   3.10.1
numpy        2.2.4
psycopg2     2.9.9
```

---

## PostgreSQL Configuration

Before running the programs, PostgreSQL must be running and the Join
Order Benchmark database must be imported.

The database connection parameters are specified in the Python files.

Example:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}
```

Replace these values with the PostgreSQL configuration used on the
experimental machine.

---

# Q1 - PostgreSQL Histograms

PostgreSQL histogram statistics are obtained from the `pg_stats`
system view.

The following query was used:

```sql
SELECT
    attname,
    n_distinct,
    null_frac,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE tablename = 'title'
  AND attname IN ('id', 'title');
```

The cardinality of the `title` table was verified using:

```sql
SELECT COUNT(*) FROM title;
```

Result:

```text
2,528,312
```

The PostgreSQL histograms contain 101 boundaries, corresponding to
100 buckets.

---

## Generating Q1 Plots

Navigate to the `code` directory:

```bash
cd code
```

Run:

```bash
python q1_plots.py
```

The program generates:

```text
q1_id_histogram.png
q1_title_histogram.png
```

Move these files to the directory containing `main.tex` if required
by the LaTeX report.

---

# Q2 - Serial Histogram

A custom serial equi-depth histogram was implemented in Python.

The experiment uses:

```text
Number of buckets: 20
Sample sizes:      1000, 3000, 5000
Columns:           id, title
Sampling method:   TABLESAMPLE
```

The choice of 20 buckets is within the required range of 10--50
buckets.

---

## Running the Experiment

Navigate to the `code` directory:

```bash
cd code
```

Run:

```bash
python histogram.py
```

For every sample size and column, the program reports:

* Actual sample size
* Histogram construction time
* Maximum selectivity error
* Maximum-error boundary

The program also performs linear regression to extrapolate the
histogram construction time for the full `title` table.

---

## Experimental Results

The final experiment produced the following results:

| Column  | Sample Size | Build Time (seconds) | Maximum Selectivity Error |
| ------- | ----------- | --------------------- | -------------------------- |
| `id`    | 1000        | 0.000122              | 0.021839                   |
| `title` | 1000        | 0.000251              | 0.050015                   |
| `id`    | 3000        | 0.000374              | 0.045663                   |
| `title` | 3000        | 0.000583              | 0.050010                   |
| `id`    | 5000        | 0.001368              | 0.051186                   |
| `title` | 5000        | 0.001162              | 0.050015                   |

---

## Full-Table Time Extrapolation

The `title` table contains:

```text
2,528,312 rows
```

Linear regression was performed using the measured construction times
for sample sizes 1000, 3000 and 5000.

The extrapolated times are:

| Column  | Extrapolated Time |
| ------- | ------------------ |
| `id`    | 0.786625 seconds   |
| `title` | 0.575489 seconds   |

These values are extrapolated histogram construction times and do not
represent the time required to scan the complete database.

---

## Q1 Selectivity Results

For the query:

```sql
SELECT *
FROM title
WHERE title < 'Race';
```

PostgreSQL estimated:

```text
1,917,391 rows
```

Actual execution returned:

```text
1,919,892 rows
```

Therefore:

```text
Estimated selectivity = 0.758368
Actual selectivity    = 0.759357
Absolute error        = 0.000989
```

For:

```sql
SELECT *
FROM title
WHERE id < 350000;
```

PostgreSQL estimated:

```text
340,649 rows
```

Actual execution returned:

```text
349,999 rows
```

Therefore:

```text
Estimated selectivity = 0.134734
Actual selectivity    = 0.138432
Absolute error        = 0.003698
```

---

## Q1 Maximum Selectivity Errors

The maximum selectivity errors calculated over the PostgreSQL
histogram boundaries were:

| Column  | Maximum Error | Boundary   |
| ------- | -------------- | ---------- |
| `id`    | 0.004393       | `314506`   |
| `title` | 0.064477       | `(#55.74)` |

The error is calculated as:

```text
Absolute Error =
|Estimated Selectivity - Actual Selectivity|
```

For `id`:

```text
|0.120000 - 0.124393|
= 0.004393
```

For `title`:

```text
|0.080000 - 0.144477|
= 0.064477
```

---

## Q2 Histogram Configuration

The custom histogram uses 20 buckets.

For the 3000-row sample:

```text
3000 / 20 = 150
```

Therefore, each bucket contains approximately 150 sampled tuples.

The histograms are generated separately for:

```text
id
title
```

---

## Visualizations

The project contains visualizations for:

1. PostgreSQL `id` histogram
2. PostgreSQL `title` histogram
3. Custom `id` histograms for different sample sizes
4. Custom `title` histograms for different sample sizes
5. Sample size versus construction time
6. Sample size versus maximum selectivity error

---

## Effect of Number of Buckets

### Fewer Buckets

Using fewer buckets:

* Reduces histogram construction and storage overhead.
* Represents larger ranges of values in each bucket.
* Provides lower resolution.
* Can increase selectivity estimation error.

### More Buckets

Using more buckets:

* Provides a finer representation of the data distribution.
* Can improve selectivity estimation.
* Requires more processing and storage.
* May provide limited benefits when the sample size is small.

Thus, the number of buckets represents a trade-off between
computational cost and estimation accuracy.

---

## Reproducibility

To reproduce the experiment:

1. Install PostgreSQL.
2. Import the Join Order Benchmark (2013 Snapshot).
3. Verify that the `title` table contains 2,528,312 rows.
4. Install the required Python packages.
5. Configure the PostgreSQL connection parameters.
6. Run:

```bash
python q1_plots.py
```

7. Run:

```bash
python histogram.py
```

8. Check the generated files in the `results` directory.


---


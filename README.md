# ADBMS Assignment 1 — Empirical Investigation of Histograms

## 1. Overview

This project implements and evaluates histogram construction techniques for the `title` table in PostgreSQL.

The experiment covers:

* PostgreSQL's built-in histograms using `pg_stats`
* Optimal serial histograms
* Sample sizes of **1,000**, **3,000**, and **5,000**
* **20 histogram buckets**
* Histogram construction for both:

  * `title.id`
  * `title.title`
* Selectivity-error analysis
* Histogram construction-time analysis
* Full-table time extrapolation using linear regression
* Vertical and horizontal-bar histogram visualizations

---

## 2. Directory Structure

```text
ADBMS Assignment-1/
│
├── ADBMS_Assignment_0.pdf
├── ADBMS_Assignment_1.pdf
├── README.md
├── requirements.txt
├── run.bat
│
├── code/
│   ├── histogram.py
│   ├── plot.py
│   ├── plot_histogram.py
│   ├── q1_plots.py
│   └── test_connection.py
│
└── results/
    ├── experiment_results.csv
    ├── full_table_extrapolation.csv
    │
    ├── id_boundaries_1000.csv
    ├── id_boundaries_3000.csv
    ├── id_boundaries_5000.csv
    ├── id_errors_1000.csv
    ├── id_errors_3000.csv
    ├── id_errors_5000.csv
    │
    ├── title_boundaries_1000.csv
    ├── title_boundaries_3000.csv
    ├── title_boundaries_5000.csv
    ├── title_errors_1000.csv
    ├── title_errors_3000.csv
    ├── title_errors_5000.csv
    │
    ├── id_histogram_1000.png
    ├── id_histogram_3000.png
    ├── id_histogram_5000.png
    ├── title_histogram_1000.png
    ├── title_histogram_3000.png
    ├── title_histogram_5000.png
    │
    ├── q1_id_histogram.png
    ├── q1_title_histogram.png
    ├── sample_size_vs_error.png
    ├── sample_size_vs_time.png
    │
    ├── plot_histogram.py   (older, unused snapshot — see Note in §6)
    │
    └── vertical_histograms/
        ├── id_histogram_1000_vertical.png
        ├── id_histogram_3000_vertical.png
        ├── id_histogram_5000_vertical.png
        ├── title_histogram_1000_vertical.png
        ├── title_histogram_3000_vertical.png
        └── title_histogram_5000_vertical.png
```

---

## 3. Requirements

### Software

* Python 3.x
* PostgreSQL
* A PostgreSQL database containing the `title` table

### Python Libraries

The required Python packages are listed in `requirements.txt`:

```text
psycopg2-binary==2.9.9
pandas==2.2.3
matplotlib==3.10.1
numpy==2.2.4
```

Install them using:

```bash
pip install -r requirements.txt
```

---

## 4. Database Configuration

The Python programs connect to PostgreSQL using the configuration defined near the top of the scripts.



The codeships with a placeholder:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}
```

Before running the experiment, update the database name, username, and password in code\histogram.py, code\q1_plots.py, code\test_connection.py.

The database must contain the following table:

```text
title
```

with the columns:

```text
id
title
```



## 5. Running the Complete Experiment

The easiest way to run the project on Windows is:

```text
run.bat
```

Double-click `run.bat` or execute it from Command Prompt:

```cmd
run.bat
```

The script performs the following steps:

### Step 1 — PostgreSQL Histogram Experiment

It runs:

```cmd
python code\q1_plots.py
```

This reads PostgreSQL's histogram statistics from `pg_stats` and generates:

```text
results/q1_id_histogram.png
results/q1_title_histogram.png
```

### Step 2 — Optimal Serial Histogram Experiment

It runs:

```cmd
python code\histogram.py
```

This performs the main histogram experiment using sample sizes:

```text
1000
3000
5000
```

and constructs:

```text
20 buckets
```

for both:

```text
id
title
```

`run.bat` creates the `results/` folder automatically if it does not already exist, and stops with an error message if either step fails.

**Note:** `run.bat` only runs `q1_plots.py` and `histogram.py`. The two visualization scripts described below (`plot_histogram.py` and `plot.py`) are **not** invoked automatically — run them manually after `histogram.py` if you want the `results/*_histogram_*.png` and `results/vertical_histograms/` plots regenerated.

---

## 6. Description of the Programs

### `code/q1_plots.py`

This program investigates PostgreSQL's built-in histogram statistics.

It:

1. Connects to PostgreSQL.
2. Reads statistics from `pg_stats`.
3. Extracts histogram boundaries for `title.id` and `title.title`.
4. Determines the number of histogram buckets.
5. Computes the approximate bucket frequencies.
6. Generates PostgreSQL histogram plots.

Output:

```text
results/q1_id_histogram.png
results/q1_title_histogram.png
```

---

### `code/histogram.py`

This is the main implementation of the optimal serial histogram experiment.

It:

1. Connects to PostgreSQL.
2. Obtains random samples from the `title` table.
3. Uses sample sizes of 1,000, 3,000, and 5,000.
4. Computes frequencies of distinct values.
5. Constructs an optimal serial histogram using dynamic programming to minimize:

```text
SUM(n_i * V_i)
```

where:

* `n_i` = number of distinct values in bucket `i`
* `V_i` = variance of frequencies within bucket `i`

6. Computes the maximum selectivity error.
7. Measures histogram construction time.
8. Performs full-table time extrapolation.
9. Writes the boundary/error CSV files that `plot_histogram.py` and `plot.py` read from.

`histogram.py` does not itself generate the `*_histogram_*.png` or `vertical_histograms/` plots — those come from the two visualization scripts below.

---

### `code/plot_histogram.py`

This program generates the **vertical bar** histogram visualizations from the boundary CSV files produced by `histogram.py`. It also includes a `fix_mojibake` helper that repairs `title` text that was incorrectly decoded as Latin-1/Windows-1252 instead of UTF-8, so bucket-boundary labels render correctly.

It uses:

```text
X-axis = Value boundaries
Y-axis = Frequency
```

The generated plots are stored directly in:

```text
results/
```

as:

```text
id_histogram_1000.png / id_histogram_3000.png / id_histogram_5000.png
title_histogram_1000.png / title_histogram_3000.png / title_histogram_5000.png
```

---

### `code/plot.py`

This program generates the **horizontal bar** (exchanged-axes) versions of the same histograms, reading the same boundary CSV files. It does **not** recompute the histograms — it only re-visualizes the data already produced by `histogram.py`.

It uses:

```text
X-axis = Frequency
Y-axis = Value Set / Bucket Boundaries
```

with the first bucket plotted at the top of the chart. The generated plots are stored in:

```text
results/vertical_histograms/
```

as `<column>_histogram_<sample_size>_vertical.png`. (Despite living in the `vertical_histograms/` folder and using the `_vertical` filename suffix, these are the horizontal-bar plots — the folder/file naming refers to the exchanged-axes variant, not to bar orientation. See the note below.)

---

### `code/test_connection.py`

This is a small utility intended to test PostgreSQL connectivity. Update its database configuration before using it.

---

### Note: stale copy of `plot_histogram.py` in `results/`

`results/plot_histogram.py` is an **older snapshot** of the script and is not used by `run.bat` or by any other script — it is left over from an earlier iteration and produces a horizontal bar chart (the opposite orientation of the current `code/plot_histogram.py`). It can be safely deleted; it is kept here only as a leftover output artifact, not as part of the pipeline.

---

## 7. Histogram Construction

For each sample:

```text
Sample size = 1000
Sample size = 3000
Sample size = 5000
```

the sampled values are sorted according to PostgreSQL ordering.

The distinct values and their frequencies are then computed.

For example:

```text
Value     Frequency
A         5
B         2
C         8
D         4
...
```

The optimal serial histogram divides the ordered domain into 20 contiguous buckets.

The objective function minimized is:

```text
Σ(n_i × V_i)
```

where `n_i` represents the number of distinct values in bucket `i` and `V_i` represents the variance of their frequencies.

---

## 8. Selectivity Error

The experiment estimates the frequency of values using the average frequency of the bucket to which the value belongs.

For a value with actual frequency `f` and estimated frequency `f̂`, the selectivity error is calculated as:

```text
|f̂ - f| / sample_size
```

The maximum error across the sampled values is recorded.

The results are stored in:

```text
results/id_errors_1000.csv
results/id_errors_3000.csv
results/id_errors_5000.csv

results/title_errors_1000.csv
results/title_errors_3000.csv
results/title_errors_5000.csv
```

---

## 9. Output Files

### Boundary CSV Files

These contain the bucket boundaries and statistics of each optimal histogram.

Example:

```text
id_boundaries_1000.csv
title_boundaries_1000.csv
```

Each bucket contains information such as:

```text
bucket
lower_boundary
upper_boundary
number_of_values
frequency
average_frequency
variance
bucket_cost
```

---

### Error CSV Files

These contain the selectivity-error calculations for individual sampled values.

Example:

```text
id_errors_1000.csv
title_errors_1000.csv
```

---

### Experiment Results

```text
experiment_results.csv
```

contains the measured results for the different sample sizes and columns, including histogram construction time and maximum selectivity error.

---

### Full-Table Extrapolation

```text
full_table_extrapolation.csv
```

contains the estimated time required to construct the histogram using the full table.

The extrapolation is obtained using a linear regression of the form:

```text
T(n) = slope × n + intercept
```

---

## 10. Graphs

The project produces several types of graphs.

### PostgreSQL Histograms

```text
q1_id_histogram.png
q1_title_histogram.png
```

These visualize PostgreSQL's histogram statistics obtained from `pg_stats`. Generated by `code/q1_plots.py`.

### Optimal Serial Histograms — Vertical Bars

For each sample size:

```text
id_histogram_1000.png
id_histogram_3000.png
id_histogram_5000.png

title_histogram_1000.png
title_histogram_3000.png
title_histogram_5000.png
```

Generated by `code/plot_histogram.py` (X = value boundaries, Y = frequency).

### Optimal Serial Histograms — Horizontal / Exchanged-Axes Bars

```text
results/vertical_histograms/id_histogram_1000_vertical.png
results/vertical_histograms/id_histogram_3000_vertical.png
results/vertical_histograms/id_histogram_5000_vertical.png
results/vertical_histograms/title_histogram_1000_vertical.png
results/vertical_histograms/title_histogram_3000_vertical.png
results/vertical_histograms/title_histogram_5000_vertical.png
```

Generated by `code/plot.py` (X = frequency, Y = value boundaries).

### Sample Size vs Time

```text
sample_size_vs_time.png
```

This compares histogram construction time for different sample sizes.

### Sample Size vs Error

```text
sample_size_vs_error.png
```

This compares maximum selectivity error for different sample sizes.

---

## 11. Reproducing the Results

To reproduce the experiment from scratch:

### Step 1

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### Step 2

Make sure PostgreSQL is running.

### Step 3

Create or connect to the required database and ensure that the `title` table is available.

### Step 4

Update the PostgreSQL connection details in:

```text
code/q1_plots.py
code/histogram.py
code/test_connection.py   (if you plan to use it)
```

### Step 5

Run:

```cmd
run.bat
```

### Step 6 (optional)

If you also want the visualization PNGs regenerated from the CSVs produced in Step 5, run:

```cmd
python code\plot_histogram.py
python code\plot.py
```

After successful execution, the generated CSV files and graphs will be available inside:

```text
results/
```

---

## 12. Notes

* The experiment uses **20 histogram buckets**.
* The sample sizes are **1,000, 3,000, and 5,000**.
* Both `id` and `title` are evaluated.
* The optimal serial histogram is constructed from the sampled data.
* Existing CSV files and graphs in `results/` are output artifacts and can be regenerated by running the experiment.
* `plot_histogram.py` and `plot.py` only change visualization; neither recomputes the underlying histogram.
* `results/plot_histogram.py` is a stale, unused snapshot of an earlier version of the script (see §6) and can be removed.
* `histogram.py` and `q1_plots.py` currently contain a real database password rather than a placeholder — replace it before sharing the project (see §4).

---

## 13. Summary

This project provides an empirical investigation of histogram construction by comparing PostgreSQL's built-in histogram statistics with an optimal serial histogram constructed from samples.

The experiment evaluates how:

* sample size affects histogram construction time,
* sample size affects selectivity error,
* the distribution of values affects bucket construction,
* and histogram construction time can be extrapolated to the full table.

All source code is contained in the `code/` directory, while generated experimental results and visualizations are contained in the `results/` directory.

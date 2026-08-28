import psycopg2
import ast
import matplotlib.pyplot as plt
import numpy as np

# ============================================================
# PostgreSQL connection
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}


# ============================================================
# Fetch PostgreSQL histogram boundaries
# ============================================================

def get_histogram_bounds(conn, column_name):
    query = """
        SELECT histogram_bounds::text
        FROM pg_stats
        WHERE tablename = 'title'
          AND attname = %s;
    """

    with conn.cursor() as cur:
        cur.execute(query, (column_name,))
        result = cur.fetchone()

    if result is None:
        raise RuntimeError(
            f"No histogram statistics found for column '{column_name}'."
        )

    text = result[0]

    # PostgreSQL array text -> Python list
    text = text.strip("{}")

    if column_name == "id":
        bounds = [int(x) for x in text.split(",")]
    else:
        # PostgreSQL text arrays can contain quoted strings.
        # Parse using PostgreSQL's array representation carefully.
        import re

        bounds = []
        current = ""
        inside_quotes = False
        escape = False

        for char in text:
            if escape:
                current += char
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                inside_quotes = not inside_quotes
            elif char == "," and not inside_quotes:
                bounds.append(current)
                current = ""
            else:
                current += char

        if current:
            bounds.append(current)

    return bounds


# ============================================================
# Plot ID histogram
# ============================================================

def plot_id_histogram(bounds):
    number_of_buckets = len(bounds) - 1

    # PostgreSQL equi-depth histogram:
    # approximately equal frequency in every bucket.
    frequency = 1.0 / number_of_buckets

    # Use bucket numbers as horizontal positions.
    y_positions = np.arange(number_of_buckets)

    plt.figure(figsize=(12, 8))

    plt.barh(
        y_positions,
        [frequency] * number_of_buckets,
        height=0.8
    )

    # Show boundary labels on Y-axis.
    labels = []

    for i in range(number_of_buckets):
        labels.append(f"{bounds[i]} - {bounds[i + 1]}")

    plt.yticks(y_positions, labels, fontsize=7)

    plt.xlabel("Frequency")
    plt.ylabel("Value boundaries")
    plt.title("PostgreSQL Histogram for title.id")

    plt.tight_layout()

    plt.savefig(
        "q1_id_histogram.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close()

    print("Created: q1_id_histogram.png")


# ============================================================
# Plot title histogram
# ============================================================

def plot_title_histogram(bounds):
    number_of_buckets = len(bounds) - 1

    frequency = 1.0 / number_of_buckets

    y_positions = np.arange(number_of_buckets)

    plt.figure(figsize=(12, 12))

    plt.barh(
        y_positions,
        [frequency] * number_of_buckets,
        height=0.8
    )

    labels = []

    for i in range(number_of_buckets):
        lower = str(bounds[i])
        upper = str(bounds[i + 1])

        labels.append(f"{lower} - {upper}")

    plt.yticks(y_positions, labels, fontsize=6)

    plt.xlabel("Frequency")
    plt.ylabel("Value boundaries")
    plt.title("PostgreSQL Histogram for title.title")

    plt.tight_layout()

    plt.savefig(
        "q1_title_histogram.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close()

    print("Created: q1_title_histogram.png")


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 60)
    print("Q1 - PostgreSQL Histogram Visualization")
    print("=" * 60)

    print("\nConnecting to PostgreSQL...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("Connected successfully!")

    except Exception as e:
        print("Could not connect to PostgreSQL.")
        print(e)
        return

    try:
        print("\nFetching id histogram...")
        id_bounds = get_histogram_bounds(conn, "id")

        print(f"Number of id boundaries: {len(id_bounds)}")
        print(f"Number of id buckets: {len(id_bounds) - 1}")

        print("\nFetching title histogram...")
        title_bounds = get_histogram_bounds(conn, "title")

        print(f"Number of title boundaries: {len(title_bounds)}")
        print(f"Number of title buckets: {len(title_bounds) - 1}")

        print("\nCreating plots...")

        plot_id_histogram(id_bounds)
        plot_title_histogram(title_bounds)

        print("\n" + "=" * 60)
        print("Q1 PLOTS GENERATED SUCCESSFULLY")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
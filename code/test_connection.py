import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}

print("Connected to PostgreSQL successfully!")

DB_CONFIG.close()

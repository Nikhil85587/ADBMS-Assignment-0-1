import psycopg2

connection = {
    "host": "localhost",
    "port": 5432,
    "database": "YOUR_DATABASE_NAME",
    "user": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
}

print("Connected to PostgreSQL successfully!")

connection.close()
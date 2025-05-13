import os
import psycopg2

# Подключаемся к Render Postgres
DATABASE_URL = os.getenv("DATABASE_URL")

def run_sql_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

if __name__ == "__main__":
    run_sql_file("scripts/add_updated_at_column.sql")

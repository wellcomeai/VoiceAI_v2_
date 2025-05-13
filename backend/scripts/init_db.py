import os
import psycopg2

print("🔧 Запуск init_db.py...")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("⛔ DATABASE_URL не установлен!")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

with open("scripts/add_updated_at_column.sql", "r") as sql_file:
    query = sql_file.read()
    cursor.execute(query)
    conn.commit()

print("✅ Миграция применена успешно.")

cursor.close()
conn.close()

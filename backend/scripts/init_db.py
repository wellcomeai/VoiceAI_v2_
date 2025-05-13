from sqlalchemy import create_engine, text
import os

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(db_url)

with engine.connect() as conn:
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns 
                WHERE table_name='conversations' AND column_name='updated_at'
            ) THEN
                ALTER TABLE conversations ADD COLUMN updated_at TIMESTAMP DEFAULT now();
            END IF;
        END $$;
    """))
    print("✅ 'updated_at' ensured in 'conversations' table.")

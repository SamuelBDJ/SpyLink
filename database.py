import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "spy-link.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    return connection


def init_db():
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            slug TEXT NOT NULL UNIQUE,

            destination_url TEXT NOT NULL,

            description TEXT,

            location_enabled INTEGER NOT NULL DEFAULT 1,

            active INTEGER NOT NULL DEFAULT 1,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            consent_given INTEGER NOT NULL DEFAULT 0,

            latitude REAL,

            longitude REAL,

            accuracy REAL,

            location_status TEXT NOT NULL DEFAULT 'not_requested',

            location_error TEXT,

            user_agent TEXT,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # Migração para bancos já existentes
    existing_columns = [
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(access_logs)"
        ).fetchall()
    ]

    migrations = {
        "latitude": "ALTER TABLE access_logs ADD COLUMN latitude REAL",
        "longitude": "ALTER TABLE access_logs ADD COLUMN longitude REAL",
        "accuracy": "ALTER TABLE access_logs ADD COLUMN accuracy REAL",
        "location_status": """
            ALTER TABLE access_logs
            ADD COLUMN location_status TEXT NOT NULL DEFAULT 'not_requested'
        """,
        "location_error": """
            ALTER TABLE access_logs
            ADD COLUMN location_error TEXT
        """
    }

    for column, sql in migrations.items():

        if column not in existing_columns:
            cursor.execute(sql)

    connection.commit()

    connection.close()



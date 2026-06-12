import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def migrate(db: sqlite3.Connection) -> None:
    current = db.execute(
        "select name from sqlite_master where type = 'table' and name = 'schema_migrations'"
    ).fetchone()
    if current:
        row = db.execute("select max(version) as version from schema_migrations").fetchone()
        if row["version"] == SCHEMA_VERSION:
            return

    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.execute("insert or ignore into schema_migrations(version) values (?)", (SCHEMA_VERSION,))
    db.commit()

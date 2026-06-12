import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _schema_statements(schema_sql: str) -> list[str]:
    return [statement.strip() for statement in schema_sql.split(";") if statement.strip()]


def current_version(db: sqlite3.Connection) -> int:
    current = db.execute(
        "select name from sqlite_master where type = 'table' and name = 'schema_migrations'"
    ).fetchone()
    if current is None:
        return 0

    row = db.execute("select max(version) from schema_migrations").fetchone()
    if row is None or row[0] is None:
        return 0
    return row[0]


def migrate(db: sqlite3.Connection) -> None:
    version = current_version(db)
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}."
        )
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise RuntimeError(
            f"Database schema version {version} is older than supported version {SCHEMA_VERSION}, "
            "and incremental migrations are not defined yet."
        )

    with db:
        db.execute("begin")
        for statement in _schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            db.execute(statement)
        db.execute("insert or ignore into schema_migrations(version) values (?)", (SCHEMA_VERSION,))

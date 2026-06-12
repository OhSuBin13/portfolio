import sqlite3

from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def table_names(db: sqlite3.Connection) -> set[str]:
    rows = db.execute(
        "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_migrate_creates_core_tables(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert {
        "schema_migrations",
        "accounts",
        "assets",
        "holdings",
        "transactions",
        "price_snapshots",
        "fx_rates",
        "goals",
        "import_runs",
        "import_rows",
        "backups",
        "settings",
    }.issubset(table_names(db))

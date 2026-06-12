import sqlite3

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def migration_versions(db: sqlite3.Connection) -> list[int]:
    rows = db.execute("select version from schema_migrations order by version").fetchall()
    return [row[0] for row in rows]


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


def test_migrate_records_schema_version(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert migration_versions(db) == [1]


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [1]


def test_migrate_supports_plain_sqlite_connections(tmp_path):
    db = sqlite3.connect(tmp_path / "portfolio.sqlite")

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [1]


def test_migrate_rejects_newer_schema_version(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.execute(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        )
        """
    )
    db.execute("insert into schema_migrations(version) values (2)")
    db.commit()

    with pytest.raises(RuntimeError, match="newer"):
        migrate(db)


def test_holdings_require_existing_account_and_asset(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into holdings(account_id, asset_id) values (1, 1)")


def test_assets_allow_multiple_null_symbols_but_reject_duplicate_symbol_market(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    db.execute(
        "insert into assets(symbol, name, type, market) values (?, ?, ?, ?)",
        ("AAPL", "Apple", "stock_etf", "US"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into assets(symbol, name, type, market) values (?, ?, ?, ?)",
            ("AAPL", "Apple Duplicate", "stock_etf", "US"),
        )

    db.execute(
        "insert into assets(symbol, name, type, market) values (?, ?, ?, ?)",
        (None, "Manual Cash", "cash", "KR"),
    )
    db.execute(
        "insert into assets(symbol, name, type, market) values (?, ?, ?, ?)",
        (None, "Manual Savings", "savings", "KR"),
    )


def test_account_type_check_constraint_rejects_invalid_values(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into accounts(name, type) values (?, ?)", ("Bad", "checking"))


def test_transaction_type_check_constraint_rejects_invalid_values(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into transactions(occurred_on, type) values (?, ?)",
            ("2026-06-12", "rebalance"),
        )


def test_price_snapshot_status_check_constraint_rejects_invalid_values(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    asset_id = db.execute(
        "insert into assets(name, type) values (?, ?)",
        ("Manual Asset", "stock_etf"),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into price_snapshots(
              asset_id, source, price, currency, price_krw, fetched_at, status
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, "manual", 100, "KRW", 100, "2026-06-12T00:00:00", "unknown"),
        )

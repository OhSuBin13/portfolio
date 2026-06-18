import sqlite3

import pytest

from portfolio_app import migrations
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


def index_names(db: sqlite3.Connection) -> set[str]:
    rows = db.execute(
        "select name from sqlite_master where type = 'index' and name not like 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


SUMMARY_QUERY_INDEXES = {
    "idx_fx_rates_summary_pair_latest",
    "idx_price_snapshots_summary_asset_latest",
    "idx_transactions_summary_holding_fx",
    "idx_transactions_summary_income_month",
    "idx_transactions_summary_usd_fx",
}


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
        "backups",
        "settings",
        "portfolio_snapshots",
    }.issubset(table_names(db))


def test_migrate_records_schema_version(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert migration_versions(db) == [7]


def test_migrate_creates_summary_query_indexes(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert SUMMARY_QUERY_INDEXES.issubset(index_names(db))


def test_update_account_repository_updates_existing_account(tmp_path):
    from portfolio_app import repositories

    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")

    assert hasattr(repositories, "update_account")
    updated = repositories.update_account(
        db,
        account_id=account_id,
        name="해외 증권",
        type="brokerage",
    )

    account = repositories.fetch_account(db, account_id=account_id)
    assert updated is True
    assert account is not None
    assert account["name"] == "해외 증권"
    assert account["type"] == "brokerage"


def test_delete_account_repository_deletes_existing_account(tmp_path):
    from portfolio_app import repositories

    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")

    deleted = repositories.delete_account(db, account_id=account_id)
    missing_deleted = repositories.delete_account(db, account_id=account_id)

    assert deleted is True
    assert repositories.fetch_account(db, account_id=account_id) is None
    assert missing_deleted is False


def test_migrate_adds_optional_fx_rate_change_percent(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    columns = db.execute("pragma table_info(fx_rates)").fetchall()
    assert "change_percent" in {row["name"] for row in columns}
    db.execute(
        """
        insert into fx_rates(
          base_currency, quote_currency, rate, source, fetched_at, change_percent
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1513.2, "naver_finance", "2026-06-16T06:30:00+00:00", -0.15),
    )


def test_migrate_removes_account_currency_from_version_4_database(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        insert into accounts(id, name, type, currency, created_at, updated_at)
        values (42, '해외 증권', 'brokerage', 'USD', '2026-06-12T00:00:00', '2026-06-12T00:00:00');
        insert into schema_migrations(version) values (4);
        """
    )
    db.commit()

    migrate(db)

    account_columns = {row["name"] for row in db.execute("pragma table_info(accounts)").fetchall()}
    row = db.execute("select id, name, type, created_at, updated_at from accounts").fetchone()
    assert migration_versions(db) == [4, 5, 6, 7]
    assert "currency" not in account_columns
    assert dict(row) == {
        "id": 42,
        "name": "해외 증권",
        "type": "brokerage",
        "created_at": "2026-06-12T00:00:00",
        "updated_at": "2026-06-12T00:00:00",
    }


def test_migrate_seeds_builtin_cash_assets_without_symbol_or_market(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)
    migrate(db)

    rows = db.execute(
        """
        select name, type, currency, symbol, market
        from assets
        where type = 'cash'
        order by currency
        """
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "name": "원화 현금",
            "type": "cash",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
        {
            "name": "달러 현금",
            "type": "cash",
            "currency": "USD",
            "symbol": None,
            "market": None,
        },
    ]


def test_migrate_seeds_builtin_initial_assets_without_symbol_or_market(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    rows = db.execute(
        """
        select name, type, currency, symbol, market
        from assets
        where type in ('cash', 'savings', 'debt')
        order by type, currency
        """
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "name": "원화 현금",
            "type": "cash",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
        {
            "name": "달러 현금",
            "type": "cash",
            "currency": "USD",
            "symbol": None,
            "market": None,
        },
        {
            "name": "부채",
            "type": "debt",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
        {
            "name": "예금",
            "type": "savings",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
    ]


def test_migrate_upgrades_version_2_database_with_builtin_savings_and_debt_assets(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table assets (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text,
          manual_price_krw real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create unique index idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null;
        insert into assets(symbol, name, type, currency, market)
        values (null, '원화 현금', 'cash', 'KRW', null);
        insert into assets(symbol, name, type, currency, market)
        values ('SAVINGS', '직접 만든 예금', 'savings', 'KRW', 'KR');
        insert into schema_migrations(version) values (2);
        """
    )
    db.commit()

    migrate(db)

    rows = db.execute(
        """
        select name, type, currency, symbol, market
        from assets
        where type in ('savings', 'debt')
        order by type, name
        """
    ).fetchall()
    assert migration_versions(db) == [2, 3, 4, 5, 6, 7]
    assert [dict(row) for row in rows] == [
        {
            "name": "부채",
            "type": "debt",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
        {
            "name": "직접 만든 예금",
            "type": "savings",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        },
    ]


def test_migrate_upgrades_version_5_database_with_portfolio_snapshots(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        insert into schema_migrations(version) values (5);
        """
    )
    db.commit()

    migrate(db)

    columns = {
        row["name"]
        for row in db.execute("pragma table_info(portfolio_snapshots)").fetchall()
    }
    assert migration_versions(db) == [5, 6, 7]
    assert {
        "id",
        "snapshot_date",
        "net_worth_krw",
        "gross_assets_krw",
        "debt_krw",
        "monthly_income_krw",
        "asset_mix_json",
        "source",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_migrate_upgrades_version_6_database_with_summary_query_indexes(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table transactions (
          id integer primary key,
          occurred_on text not null,
          type text not null,
          account_id integer,
          asset_id integer,
          amount real not null default 0,
          currency text not null default 'KRW',
          fx_rate_to_krw real
        );
        create table price_snapshots (
          id integer primary key,
          asset_id integer not null,
          status text not null default 'ok',
          fetched_at text not null
        );
        create table fx_rates (
          id integer primary key,
          base_currency text not null,
          quote_currency text not null default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          change_percent real
        );
        insert into schema_migrations(version) values (6);
        """
    )
    db.commit()

    migrate(db)

    assert migration_versions(db) == [6, 7]
    assert SUMMARY_QUERY_INDEXES.issubset(index_names(db))


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [7]


def test_migrate_supports_plain_sqlite_connections(tmp_path):
    db = sqlite3.connect(tmp_path / "portfolio.sqlite")

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [7]


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
    db.execute("insert into schema_migrations(version) values (8)")
    db.commit()

    with pytest.raises(RuntimeError, match="newer"):
        migrate(db)


def test_migrate_rolls_back_partial_schema_when_schema_application_fails(tmp_path, monkeypatch):
    schema_path = tmp_path / "broken_schema.sql"
    schema_path.write_text(
        """
        create table partial_table (id integer primary key);
        create table broken_table (
        """,
        encoding="utf-8",
    )
    db = connect(tmp_path / "portfolio.sqlite")
    monkeypatch.setattr(migrations, "SCHEMA_PATH", schema_path)

    with pytest.raises((sqlite3.Error, RuntimeError)):
        migrate(db)

    assert "partial_table" not in table_names(db)
    assert "schema_migrations" not in table_names(db) or migration_versions(db) == []


def test_migrate_rejects_existing_version_without_incremental_migration(tmp_path, monkeypatch):
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
    db.execute("insert into schema_migrations(version) values (7)")
    db.commit()
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 8)

    with pytest.raises(RuntimeError, match="incremental migrations are not defined"):
        migrate(db)

    assert migration_versions(db) == [7]


def test_migrate_upgrades_version_1_database_with_builtin_cash_assets(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table assets (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text not null default 'KR',
          manual_price_krw real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create unique index idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null;
        insert into schema_migrations(version) values (1);
        """
    )
    db.commit()

    migrate(db)

    rows = db.execute(
        """
        select name, currency, symbol, market
        from assets
        where type = 'cash'
        order by currency
        """
    ).fetchall()
    assert migration_versions(db) == [1, 2, 3, 4, 5, 6, 7]
    assert [dict(row) for row in rows] == [
        {"name": "원화 현금", "currency": "KRW", "symbol": None, "market": None},
        {"name": "달러 현금", "currency": "USD", "symbol": None, "market": None},
    ]


def test_migrate_normalizes_existing_version_1_cash_asset_without_duplicating_it(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table assets (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text not null default 'KR',
          manual_price_krw real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create unique index idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null;
        insert into assets(id, symbol, name, type, currency, market)
        values (10, 'KRW', '직접 만든 현금', 'cash', 'KRW', 'KR');
        insert into schema_migrations(version) values (1);
        """
    )
    db.commit()

    migrate(db)

    rows = db.execute(
        """
        select id, name, currency, symbol, market
        from assets
        where type = 'cash' and currency = 'KRW'
        order by id
        """
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "id": 10,
            "name": "직접 만든 현금",
            "currency": "KRW",
            "symbol": None,
            "market": None,
        }
    ]


def test_holdings_require_existing_account_and_asset(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into holdings(account_id, asset_id) values (1, 1)")


def test_portfolio_snapshots_enforce_unique_kst_date(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-06-17", 1_000_000, 1_000_000, 0, 0, "{}", "manual"),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into portfolio_snapshots(
              snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
              monthly_income_krw, asset_mix_json, source
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-17", 2_000_000, 2_000_000, 0, 0, "{}", "manual"),
        )


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

    account_columns = {row["name"] for row in db.execute("pragma table_info(accounts)").fetchall()}
    assert "currency" not in account_columns

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into accounts(name, type) values (?, ?)", ("Bad", "checking"))


def test_currency_check_constraints_reject_invalid_values(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = db.execute(
        "insert into accounts(name, type) values (?, ?)",
        ("원화 현금", "cash"),
    ).lastrowid
    asset_id = db.execute(
        "insert into assets(name, type, currency, market) values (?, ?, ?, ?)",
        ("KRW", "cash", "KRW", "KR"),
    ).lastrowid

    invalid_statements = [
        (
            "insert into assets(name, type, currency, market) values (?, ?, ?, ?)",
            ("Invalid Asset", "cash", "EUR", "EU"),
        ),
        (
            """
            insert into transactions(occurred_on, type, account_id, asset_id, amount, currency)
            values (?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-12", "deposit", account_id, asset_id, 100, "EUR"),
        ),
        (
            """
            insert into price_snapshots(asset_id, source, price, currency, price_krw, fetched_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, "manual", 100, "EUR", 100, "2026-06-12T00:00:00"),
        ),
        (
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            ("EUR", "KRW", 1500, "manual", "2026-06-12T00:00:00"),
        ),
        (
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            ("USD", "EUR", 0.0007, "manual", "2026-06-12T00:01:00"),
        ),
    ]

    for sql, params in invalid_statements:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, params)


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

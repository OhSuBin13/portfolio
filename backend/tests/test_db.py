import sqlite3

import pytest

from portfolio_app import migrations
from portfolio_app.db import connect
from portfolio_app.migrations import migrate

TOSS_ONLY_TABLES = {
    "schema_migrations",
    "fx_rates",
    "goals",
    "backups",
    "settings",
}
TOSS_ONLY_INDEXES = {"idx_fx_rates_summary_pair_latest"}
REMOVED_LOCAL_LEDGER_TABLES = {
    "accounts",
    "assets",
    "holdings",
    "import_rows",
    "import_runs",
    "transactions",
    "price_snapshots",
    "portfolio_snapshots",
}


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


def column_names(db: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in db.execute(f"pragma table_info({table_name})").fetchall()}


def assert_toss_only_schema(db: sqlite3.Connection) -> None:
    assert table_names(db) == TOSS_ONLY_TABLES
    assert_removed_local_ledger_tables_gone(db)
    assert index_names(db) == TOSS_ONLY_INDEXES


def assert_removed_local_ledger_tables_gone(db: sqlite3.Connection) -> None:
    assert REMOVED_LOCAL_LEDGER_TABLES.isdisjoint(table_names(db))


def create_schema_migrations(db: sqlite3.Connection, version: int) -> None:
    db.execute(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        )
        """
    )
    db.execute("insert into schema_migrations(version) values (?)", (version,))


def create_toss_only_survivor_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table fx_rates (
          id integer primary key,
          base_currency text not null check (base_currency in ('USD','KRW')),
          quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          change_percent real,
          unique(base_currency, quote_currency, fetched_at)
        );
        create index idx_fx_rates_summary_pair_latest
        on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);

        create table goals (
          id integer primary key,
          name text not null,
          type text not null check (type in ('net_worth','monthly_income')),
          target_amount_krw real not null check (target_amount_krw > 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );

        create table backups (
          id integer primary key,
          path text not null,
          reason text not null,
          created_at text not null default current_timestamp
        );

        create table settings (
          key text primary key,
          value text not null,
          updated_at text not null default current_timestamp
        );
        """
    )


def create_v9_local_ledger_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );

        create table assets (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text,
          manual_price_krw real,
          is_listed integer check (is_listed in (0,1)),
          instrument_type text,
          metadata_source text not null default 'manual'
            check (metadata_source in ('manual','toss')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create unique index idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null;

        create table holdings (
          id integer primary key,
          account_id integer not null references accounts(id) on delete cascade,
          asset_id integer not null references assets(id) on delete cascade,
          quantity real not null default 0,
          average_cost real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_id, asset_id)
        );

        create table transactions (
          id integer primary key,
          occurred_on text not null,
          type text not null check (
            type in (
              'deposit',
              'withdrawal',
              'buy',
              'sell',
              'dividend',
              'interest',
              'fee',
              'debt_payment',
              'adjustment'
            )
          ),
          account_id integer references accounts(id) on delete set null,
          asset_id integer references assets(id) on delete set null,
          quantity real,
          amount real not null default 0,
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          fx_rate_to_krw real,
          memo text not null default '',
          created_at text not null default current_timestamp
        );
        create index idx_transactions_summary_holding_fx
        on transactions(account_id, asset_id, occurred_on desc, id desc)
        where fx_rate_to_krw is not null;
        create index idx_transactions_summary_income_month
        on transactions(occurred_on, id)
        where type in ('dividend', 'interest');
        create index idx_transactions_summary_usd_fx
        on transactions(occurred_on desc, id desc)
        where currency = 'USD'
          and fx_rate_to_krw is not null
          and fx_rate_to_krw > 0;

        create table price_snapshots (
          id integer primary key,
          asset_id integer not null references assets(id) on delete cascade,
          source text not null,
          price real not null,
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          price_krw real not null,
          fetched_at text not null,
          status text not null default 'ok' check (status in ('ok','stale','failed','manual')),
          error_message text not null default ''
        );
        create index idx_price_snapshots_summary_asset_latest
        on price_snapshots(asset_id, fetched_at desc, id desc)
        where status in ('ok', 'manual', 'stale');

        create table portfolio_snapshots (
          id integer primary key,
          snapshot_date text not null unique,
          net_worth_krw real not null,
          gross_assets_krw real not null check (gross_assets_krw >= 0),
          debt_krw real not null check (debt_krw >= 0),
          monthly_income_krw real not null default 0 check (monthly_income_krw >= 0),
          asset_mix_json text not null default '{}',
          source text not null check (source in ('scheduled','manual','market_sync','import')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );

        insert into accounts(id, name, type) values (1, '토스 증권', 'brokerage');
        insert into assets(id, symbol, name, type, currency, market, is_listed, metadata_source)
        values (1, 'VOO', 'Vanguard S&P 500 ETF', 'stock_etf', 'USD', 'US', 1, 'manual');
        insert into holdings(id, account_id, asset_id, quantity, average_cost)
        values (1, 1, 1, 2, 500);
        insert into transactions(
          id, occurred_on, type, account_id, asset_id, quantity, amount, currency, fx_rate_to_krw
        )
        values (1, '2026-06-28', 'buy', 1, 1, 2, 1000, 'USD', 1400);
        insert into price_snapshots(id, asset_id, source, price, currency, price_krw, fetched_at)
        values (1, 1, 'manual', 510, 'USD', 714000, '2026-06-28T00:00:00+00:00');
        insert into portfolio_snapshots(
          id, snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (1, '2026-06-28', 1000000, 1000000, 0, 0, '{}', 'manual');
        """
    )


def create_legacy_import_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table import_runs (
          id integer primary key,
          source text not null,
          created_at text not null default current_timestamp
        );
        create table import_rows (
          id integer primary key,
          import_run_id integer not null references import_runs(id) on delete cascade,
          raw_json text not null
        );
        insert into import_runs(id, source) values (1, 'manual');
        insert into import_rows(id, import_run_id, raw_json) values (1, 1, '{}');
        """
    )


def test_migrate_creates_toss_only_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")

    migrate(db)

    assert migration_versions(db) == [10]
    assert_toss_only_schema(db)


def test_migrate_keeps_fx_rate_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert column_names(db, "fx_rates") == {
        "id",
        "base_currency",
        "quote_currency",
        "rate",
        "source",
        "fetched_at",
        "change_percent",
    }
    db.execute(
        """
        insert into fx_rates(
          base_currency, quote_currency, rate, source, fetched_at, change_percent
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1513.2, "toss", "2026-06-16T06:30:00+00:00", -0.15),
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            ("EUR", "KRW", 1500, "toss", "2026-06-16T06:31:00+00:00"),
        )


def test_goals_require_positive_target_amount_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into goals(name, type, target_amount_krw)
            values (?, ?, ?)
            """,
            ("잘못된 목표", "net_worth", 0),
        )


def test_migrate_from_v9_drops_local_ledger_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 9)
    create_toss_only_survivor_tables(db)
    create_v9_local_ledger_tables(db)
    create_legacy_import_tables(db)
    db.execute(
        """
        insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
        values (?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1400, "toss", "2026-06-28T00:00:00+00:00"),
    )
    db.execute(
        """
        insert into goals(name, type, target_amount_krw)
        values (?, ?, ?)
        """,
        ("순자산 1억", "net_worth", 100000000),
    )
    db.execute("insert into backups(path, reason) values (?, ?)", ("backup.sqlite", "startup"))
    db.execute("insert into settings(key, value) values (?, ?)", ("theme", "dark"))
    db.commit()

    migrate(db)

    assert migration_versions(db) == [9, 10]
    assert_toss_only_schema(db)
    assert db.execute("select count(*) from fx_rates").fetchone()[0] == 1
    assert db.execute("select count(*) from goals").fetchone()[0] == 1
    assert db.execute("select count(*) from backups").fetchone()[0] == 1
    assert db.execute("select value from settings where key = 'theme'").fetchone()[0] == "dark"


def test_migrate_upgrades_version_7_database_to_v10_and_preserves_goals(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table goals (
          id integer primary key,
          name text not null,
          type text not null check (type in ('net_worth','monthly_income')),
          target_amount_krw real not null,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
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
        create table fx_rates (
          id integer primary key,
          base_currency text not null check (base_currency in ('USD','KRW')),
          quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          change_percent real,
          unique(base_currency, quote_currency, fetched_at)
        );
        create index idx_fx_rates_summary_pair_latest
        on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);
        create table backups (
          id integer primary key,
          path text not null,
          reason text not null,
          created_at text not null default current_timestamp
        );
        create table settings (
          key text primary key,
          value text not null,
          updated_at text not null default current_timestamp
        );
        insert into goals(id, name, type, target_amount_krw, created_at, updated_at)
        values (42, '순자산 1억', 'net_worth', 100000000, '2026-06-19', '2026-06-19');
        insert into schema_migrations(version) values (7);
        """
    )
    db.commit()

    migrate(db)

    row = db.execute("select * from goals where id = 42").fetchone()
    assert migration_versions(db) == [7, 8, 9, 10]
    assert_toss_only_schema(db)
    assert row["target_amount_krw"] == 100_000_000
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into goals(name, type, target_amount_krw)
            values (?, ?, ?)
            """,
            ("잘못된 목표", "monthly_income", -1),
        )


def test_migrate_upgrades_version_4_database_to_v10_and_removes_local_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
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
        create table fx_rates (
          id integer primary key,
          base_currency text not null check (base_currency in ('USD','KRW')),
          quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          change_percent real,
          unique(base_currency, quote_currency, fetched_at)
        );
        create index idx_fx_rates_summary_pair_latest
        on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);
        create table backups (
          id integer primary key,
          path text not null,
          reason text not null,
          created_at text not null default current_timestamp
        );
        create table settings (
          key text primary key,
          value text not null,
          updated_at text not null default current_timestamp
        );
        insert into accounts(id, name, type, currency, created_at, updated_at)
        values (42, '해외 증권', 'brokerage', 'USD', '2026-06-12T00:00:00', '2026-06-12T00:00:00');
        insert into schema_migrations(version) values (4);
        """
    )
    db.commit()

    migrate(db)

    assert migration_versions(db) == [4, 5, 6, 7, 8, 9, 10]
    assert_toss_only_schema(db)


def test_migrate_upgrades_version_1_database_to_v10_and_removes_local_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
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
        create table fx_rates (
          id integer primary key,
          base_currency text not null,
          quote_currency text not null default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          unique(base_currency, quote_currency, fetched_at)
        );
        insert into fx_rates(id, base_currency, quote_currency, rate, source, fetched_at)
        values (1, 'USD', 'KRW', 1400, 'toss', '2026-06-28T00:00:00+00:00');
        insert into schema_migrations(version) values (1);
        """
    )
    create_legacy_import_tables(db)
    db.commit()

    migrate(db)

    assert migration_versions(db) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert_toss_only_schema(db)
    assert db.execute("select count(*) from fx_rates").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            ("EUR", "KRW", 1500, "toss", "2026-06-28T01:00:00+00:00"),
        )


def test_migrate_is_idempotent(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [10]
    assert_toss_only_schema(db)


def test_migrate_supports_plain_sqlite_connections(tmp_path):
    db = sqlite3.connect(tmp_path / "portfolio.sqlite")

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [10]


def test_migrate_rejects_newer_schema_version(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 11)
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

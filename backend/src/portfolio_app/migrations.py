import sqlite3
from pathlib import Path

SCHEMA_VERSION = 8
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
BUILTIN_INITIAL_ASSETS = (
    ("원화 현금", "cash", "KRW"),
    ("달러 현금", "cash", "USD"),
    ("예금", "savings", "KRW"),
    ("부채", "debt", "KRW"),
)


def _schema_statements(schema_sql: str) -> list[str]:
    return [statement.strip() for statement in schema_sql.split(";") if statement.strip()]


def _pragma_column_names(rows: list[sqlite3.Row] | list[tuple]) -> set[str]:
    return {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}


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


def _seed_builtin_initial_assets(db: sqlite3.Connection) -> None:
    for name, asset_type, currency in BUILTIN_INITIAL_ASSETS:
        db.execute(
            """
            insert into assets(symbol, name, type, currency, market)
            select null, ?, ?, ?, null
            where not exists (
              select 1
              from assets
              where symbol is null
                and market is null
                and type = ?
                and currency = ?
            )
            """,
            (name, asset_type, currency, asset_type, currency),
        )


def _create_assets_table_sql(table_name: str) -> str:
    return f"""
        create table {table_name} (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text,
          manual_price_krw real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        )
        """


def _create_accounts_table_sql(table_name: str) -> str:
    return f"""
        create table {table_name} (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        )
        """


def _create_goals_table_sql(table_name: str) -> str:
    return f"""
        create table {table_name} (
          id integer primary key,
          name text not null,
          type text not null check (type in ('net_worth','monthly_income')),
          target_amount_krw real not null check (target_amount_krw > 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        )
        """


def _create_asset_indexes(db: sqlite3.Connection) -> None:
    db.execute(
        """
        create unique index if not exists idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null
        """
    )


def _table_exists(db: sqlite3.Connection, table_name: str) -> bool:
    return (
        db.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _create_summary_indexes(db: sqlite3.Connection) -> None:
    if _table_exists(db, "transactions"):
        db.execute(
            """
            create index if not exists idx_transactions_summary_holding_fx
            on transactions(account_id, asset_id, occurred_on desc, id desc)
            where fx_rate_to_krw is not null
            """
        )
        db.execute(
            """
            create index if not exists idx_transactions_summary_income_month
            on transactions(occurred_on, id)
            where type in ('dividend', 'interest')
            """
        )
        db.execute(
            """
            create index if not exists idx_transactions_summary_usd_fx
            on transactions(occurred_on desc, id desc)
            where currency = 'USD'
              and fx_rate_to_krw is not null
              and fx_rate_to_krw > 0
            """
        )

    if _table_exists(db, "price_snapshots"):
        db.execute(
            """
            create index if not exists idx_price_snapshots_summary_asset_latest
            on price_snapshots(asset_id, fetched_at desc, id desc)
            where status in ('ok', 'manual', 'stale')
            """
        )

    if _table_exists(db, "fx_rates"):
        db.execute(
            """
            create index if not exists idx_fx_rates_summary_pair_latest
            on fx_rates(base_currency, quote_currency, fetched_at desc, id desc)
            """
        )


def _migrate_from_1_to_2(db: sqlite3.Connection) -> None:
    db.execute("pragma foreign_keys = off")
    try:
        with db:
            db.execute("begin")
            db.execute("drop index if exists idx_assets_symbol_market")
            db.execute(_create_assets_table_sql("assets_v2"))
            db.execute(
                """
                insert into assets_v2(
                  id, symbol, name, type, currency, market, manual_price_krw, created_at, updated_at
                )
                select id, symbol, name, type, currency, market, manual_price_krw,
                       created_at, updated_at
                from assets
                """
            )
            db.execute("drop table assets")
            db.execute("alter table assets_v2 rename to assets")
            db.execute("update assets set symbol = null, market = null where type = 'cash'")
            _create_asset_indexes(db)
            _seed_builtin_initial_assets(db)

            violations = db.execute("pragma foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Database foreign key check failed during schema migration.")

            db.execute("insert or ignore into schema_migrations(version) values (2)")
    finally:
        db.execute("pragma foreign_keys = on")


def _migrate_from_2_to_3(db: sqlite3.Connection) -> None:
    with db:
        db.execute(
            """
            update assets
            set symbol = null,
                market = null
            where type in ('cash', 'savings', 'debt')
            """
        )
        _seed_builtin_initial_assets(db)
        db.execute("insert or ignore into schema_migrations(version) values (3)")


def _migrate_from_3_to_4(db: sqlite3.Connection) -> None:
    table = db.execute(
        "select name from sqlite_master where type = 'table' and name = 'fx_rates'"
    ).fetchone()
    columns = db.execute("pragma table_info(fx_rates)").fetchall()
    column_names = _pragma_column_names(columns)
    with db:
        if table is not None and "change_percent" not in column_names:
            db.execute("alter table fx_rates add column change_percent real")
        db.execute("insert or ignore into schema_migrations(version) values (4)")


def _migrate_from_4_to_5(db: sqlite3.Connection) -> None:
    db.execute("pragma foreign_keys = off")
    try:
        with db:
            db.execute("begin")
            db.execute(_create_accounts_table_sql("accounts_v5"))
            db.execute(
                """
                insert into accounts_v5(id, name, type, created_at, updated_at)
                select id, name, type, created_at, updated_at
                from accounts
                """
            )
            db.execute("drop table accounts")
            db.execute("alter table accounts_v5 rename to accounts")

            violations = db.execute("pragma foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Database foreign key check failed during schema migration.")

            db.execute("insert or ignore into schema_migrations(version) values (5)")
    finally:
        db.execute("pragma foreign_keys = on")


def _migrate_from_5_to_6(db: sqlite3.Connection) -> None:
    with db:
        db.execute(
            """
            create table if not exists portfolio_snapshots (
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
            )
            """
        )
        db.execute("insert or ignore into schema_migrations(version) values (6)")


def _migrate_from_6_to_7(db: sqlite3.Connection) -> None:
    with db:
        _create_summary_indexes(db)
        db.execute("insert or ignore into schema_migrations(version) values (7)")


def _migrate_from_7_to_8(db: sqlite3.Connection) -> None:
    if not _table_exists(db, "goals"):
        with db:
            db.execute("insert or ignore into schema_migrations(version) values (8)")
        return

    db.execute("pragma foreign_keys = off")
    try:
        with db:
            db.execute("begin")
            db.execute(_create_goals_table_sql("goals_v8"))
            db.execute(
                """
                insert into goals_v8(id, name, type, target_amount_krw, created_at, updated_at)
                select id, name, type, target_amount_krw, created_at, updated_at
                from goals
                """
            )
            db.execute("drop table goals")
            db.execute("alter table goals_v8 rename to goals")

            violations = db.execute("pragma foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Database foreign key check failed during schema migration.")

            db.execute("insert or ignore into schema_migrations(version) values (8)")
    finally:
        db.execute("pragma foreign_keys = on")


def migrate(db: sqlite3.Connection) -> None:
    version = current_version(db)
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}."
        )

    if version == 0:
        with db:
            db.execute("begin")
            for statement in _schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
                db.execute(statement)
            _seed_builtin_initial_assets(db)
            db.execute(
                "insert or ignore into schema_migrations(version) values (?)",
                (SCHEMA_VERSION,),
            )
        return

    if version == 1:
        _migrate_from_1_to_2(db)
        version = 2

    if version == 2:
        _migrate_from_2_to_3(db)
        version = 3

    if version == 3:
        _migrate_from_3_to_4(db)
        version = 4

    if version == 4:
        _migrate_from_4_to_5(db)
        version = 5

    if version == 5:
        _migrate_from_5_to_6(db)
        version = 6

    if version == 6:
        _migrate_from_6_to_7(db)
        version = 7

    if version == 7:
        _migrate_from_7_to_8(db)
        version = 8

    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is older than supported version {SCHEMA_VERSION}, "
            "and incremental migrations are not defined yet."
        )

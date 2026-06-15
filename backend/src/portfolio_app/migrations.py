import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
BUILTIN_INITIAL_ASSETS = (
    ("원화 현금", "cash", "KRW"),
    ("달러 현금", "cash", "USD"),
    ("예금", "savings", "KRW"),
    ("부채", "debt", "KRW"),
)


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


def _create_asset_indexes(db: sqlite3.Connection) -> None:
    db.execute(
        """
        create unique index if not exists idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null
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

    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is older than supported version {SCHEMA_VERSION}, "
            "and incremental migrations are not defined yet."
        )

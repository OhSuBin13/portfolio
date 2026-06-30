import sqlite3

import pytest

from portfolio_app import migrations, repositories
from portfolio_app.db import connect
from portfolio_app.migrations import migrate

TOSS_ONLY_TABLES = {
    "schema_migrations",
    "fx_rates",
    "goals",
    "backups",
    "settings",
    "toss_order_import_runs",
    "toss_orders",
    "growth_month_history",
    "sp500_proxy_prices",
}
TOSS_ORDER_INDEXES = {
    "idx_toss_orders_account_ordered_at",
    "idx_toss_orders_account_status",
    "idx_toss_orders_account_symbol",
}
GROWTH_MONTH_HISTORY_INDEXES = {
    "idx_growth_month_history_account_period",
}
SP500_PROXY_PRICE_INDEXES = {
    "idx_sp500_proxy_prices_symbol_year",
}
SEEDED_SP500_PROXY_PRICES = [
    (2021, 436.57),
    (2022, 351.34),
    (2023, 436.80),
    (2024, 538.81),
    (2025, 627.13),
]
TOSS_ONLY_INDEXES = {
    "idx_fx_rates_summary_pair_latest",
    *TOSS_ORDER_INDEXES,
    *GROWTH_MONTH_HISTORY_INDEXES,
    *SP500_PROXY_PRICE_INDEXES,
}
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


def create_v11_toss_order_history_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table toss_order_import_runs (
          id integer primary key,
          account_seq text not null,
          status_filter text not null check (status_filter in ('OPEN','CLOSED')),
          symbol_filter text,
          from_date text,
          to_date text,
          run_status text not null check (run_status in ('running','success','failed')),
          imported_count integer not null default 0 check (imported_count >= 0),
          error_message text not null default '',
          started_at text not null default current_timestamp,
          completed_at text
        );

        create table toss_orders (
          id integer primary key,
          account_seq text not null,
          order_id text not null,
          symbol text not null,
          side text not null,
          order_type text not null,
          time_in_force text not null,
          order_status text not null,
          price text,
          quantity text not null,
          order_amount text,
          currency text not null,
          ordered_at text not null,
          canceled_at text,
          filled_quantity text not null,
          average_filled_price text,
          filled_amount text,
          commission text,
          tax text,
          filled_at text,
          settlement_date text,
          raw_json text not null,
          import_run_id integer references toss_order_import_runs(id) on delete set null,
          imported_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, order_id)
        );

        create index idx_toss_orders_account_ordered_at
        on toss_orders(account_seq, ordered_at desc, id desc);

        create index idx_toss_orders_account_status
        on toss_orders(account_seq, order_status, ordered_at desc, id desc);

        create index idx_toss_orders_account_symbol
        on toss_orders(account_seq, symbol, ordered_at desc, id desc);
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


def insert_valid_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    account_seq: str = "account-1",
    status_filter: str = "CLOSED",
    run_status: str = "success",
    imported_count: int = 1,
) -> int:
    return insert_toss_order_import_run(
        db,
        toss_order_import_run_values(
            account_seq=account_seq,
            status_filter=status_filter,
            run_status=run_status,
            imported_count=imported_count,
        ),
    )


def toss_order_import_run_values(
    *,
    account_seq: str = "account-1",
    status_filter: str = "CLOSED",
    run_status: str = "success",
    imported_count: int = 1,
) -> dict[str, object]:
    return {
        "account_seq": account_seq,
        "status_filter": status_filter,
        "run_status": run_status,
        "imported_count": imported_count,
    }


def insert_toss_order_import_run(db: sqlite3.Connection, values: dict[str, object]) -> int:
    cursor = db.execute(
        """
        insert into toss_order_import_runs(
          account_seq, status_filter, run_status, imported_count
        )
        values (:account_seq, :status_filter, :run_status, :imported_count)
        """,
        values,
    )
    return cursor.lastrowid


def toss_order_values(
    *,
    order_id: str = "order-1",
    account_seq: str = "account-1",
    import_run_id: int | None = None,
) -> dict[str, object]:
    return {
        "account_seq": account_seq,
        "order_id": order_id,
        "symbol": "VOO",
        "side": "BUY",
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "order_status": "FILLED",
        "price": None,
        "quantity": "2",
        "order_amount": None,
        "currency": "USD",
        "ordered_at": "2026-06-29T09:00:00+09:00",
        "canceled_at": None,
        "filled_quantity": "2",
        "average_filled_price": None,
        "filled_amount": None,
        "commission": None,
        "tax": None,
        "filled_at": None,
        "settlement_date": None,
        "raw_json": '{"orderId":"order-1"}',
        "import_run_id": import_run_id,
    }


def insert_toss_order(db: sqlite3.Connection, values: dict[str, object]) -> int:
    cursor = db.execute(
        """
        insert into toss_orders(
          account_seq,
          order_id,
          symbol,
          side,
          order_type,
          time_in_force,
          order_status,
          price,
          quantity,
          order_amount,
          currency,
          ordered_at,
          canceled_at,
          filled_quantity,
          average_filled_price,
          filled_amount,
          commission,
          tax,
          filled_at,
          settlement_date,
          raw_json,
          import_run_id
        )
        values (
          :account_seq,
          :order_id,
          :symbol,
          :side,
          :order_type,
          :time_in_force,
          :order_status,
          :price,
          :quantity,
          :order_amount,
          :currency,
          :ordered_at,
          :canceled_at,
          :filled_quantity,
          :average_filled_price,
          :filled_amount,
          :commission,
          :tax,
          :filled_at,
          :settlement_date,
          :raw_json,
          :import_run_id
        )
        """,
        values,
    )
    return cursor.lastrowid


def insert_valid_toss_order(
    db: sqlite3.Connection,
    *,
    order_id: str = "order-1",
    account_seq: str = "account-1",
    import_run_id: int | None = None,
) -> int:
    return insert_toss_order(
        db,
        toss_order_values(
            order_id=order_id,
            account_seq=account_seq,
            import_run_id=import_run_id,
        ),
    )


def assert_toss_order_history_contract(db: sqlite3.Connection) -> None:
    import_run_id = insert_valid_toss_order_import_run(db)
    order_id = insert_valid_toss_order(db, import_run_id=import_run_id)

    row = db.execute("select * from toss_orders where id = ?", (order_id,)).fetchone()
    assert row["account_seq"] == "account-1"
    assert row["order_id"] == "order-1"
    assert row["import_run_id"] == import_run_id

    with pytest.raises(sqlite3.IntegrityError):
        insert_valid_toss_order(db, order_id="order-1", import_run_id=import_run_id)

    with pytest.raises(sqlite3.IntegrityError):
        insert_valid_toss_order_import_run(
            db,
            account_seq="invalid-status-filter",
            status_filter="PENDING",
        )

    with pytest.raises(sqlite3.IntegrityError):
        insert_valid_toss_order_import_run(
            db,
            account_seq="invalid-run-status",
            run_status="cancelled",
        )

    with pytest.raises(sqlite3.IntegrityError):
        insert_valid_toss_order_import_run(
            db,
            account_seq="invalid-imported-count",
            imported_count=-1,
        )

    required_import_run_fields = (
        "account_seq",
        "status_filter",
        "run_status",
        "imported_count",
    )
    for field_name in required_import_run_fields:
        values = toss_order_import_run_values(account_seq=f"missing-{field_name}")
        values[field_name] = None
        with pytest.raises(sqlite3.IntegrityError):
            insert_toss_order_import_run(db, values)

    db.execute("delete from toss_order_import_runs where id = ?", (import_run_id,))
    assert db.execute(
        "select import_run_id from toss_orders where id = ?",
        (order_id,),
    ).fetchone()[0] is None

    required_order_fields = (
        "account_seq",
        "order_id",
        "symbol",
        "side",
        "order_type",
        "time_in_force",
        "order_status",
        "quantity",
        "currency",
        "ordered_at",
        "filled_quantity",
        "raw_json",
    )
    for field_name in required_order_fields:
        values = toss_order_values(order_id=f"missing-{field_name}")
        values[field_name] = None
        with pytest.raises(sqlite3.IntegrityError):
            insert_toss_order(db, values)


def assert_growth_month_history_contract(db: sqlite3.Connection) -> None:
    assert "growth_month_history" in table_names(db)
    assert column_names(db, "growth_month_history") == {
        "id",
        "account_seq",
        "year",
        "month",
        "net_worth_krw",
        "monthly_dividend_krw",
        "created_at",
        "updated_at",
    }
    assert index_names(db) >= GROWTH_MONTH_HISTORY_INDEXES

    db.execute(
        """
        insert into growth_month_history(account_seq, year, month, net_worth_krw)
        values (?, ?, ?, ?)
        """,
        ("account-1", 2026, 6, 1_000_000),
    )
    row = db.execute(
        """
        select *
        from growth_month_history
        where account_seq = ? and year = ? and month = ?
        """,
        ("account-1", 2026, 6),
    ).fetchone()
    assert row["monthly_dividend_krw"] == 0
    assert row["created_at"] is not None
    assert row["updated_at"] is not None

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into growth_month_history(account_seq, year, month, net_worth_krw)
            values (?, ?, ?, ?)
            """,
            ("account-1", 2026, 6, 2_000_000),
        )


def assert_sp500_proxy_prices_contract(db: sqlite3.Connection) -> None:
    assert "sp500_proxy_prices" in table_names(db)
    assert column_names(db, "sp500_proxy_prices") == {
        "id",
        "year",
        "proxy_symbol",
        "price",
        "currency",
        "created_at",
        "updated_at",
    }
    assert index_names(db) >= SP500_PROXY_PRICE_INDEXES

    db.execute(
        """
        insert into sp500_proxy_prices(year, price)
        values (?, ?)
        """,
        (2026, 500.0),
    )
    row = db.execute("select * from sp500_proxy_prices where year = 2026").fetchone()
    assert row["proxy_symbol"] == "VOO"
    assert row["currency"] == "USD"

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into sp500_proxy_prices(year, price) values (?, ?)",
            (2026, 510.0),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into sp500_proxy_prices(year, price) values (?, ?)",
            (2026, 0),
        )


def assert_seeded_sp500_proxy_prices(db: sqlite3.Connection) -> None:
    rows = db.execute(
        """
        select year, price
        from sp500_proxy_prices
        where year between 2021 and 2025
        order by year
        """
    ).fetchall()
    assert [(row["year"], row["price"]) for row in rows] == SEEDED_SP500_PROXY_PRICES


def test_migrate_creates_toss_only_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")

    migrate(db)

    assert migration_versions(db) == [14]
    assert_toss_only_schema(db)


def test_migrate_creates_toss_order_history_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")

    migrate(db)

    assert migration_versions(db) == [14]
    assert {
        "toss_order_import_runs",
        "toss_orders",
    } <= table_names(db)
    assert index_names(db) >= TOSS_ORDER_INDEXES


def test_toss_order_history_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert_toss_order_history_contract(db)


def test_growth_month_history_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert migration_versions(db) == [14]
    assert_growth_month_history_contract(db)


def test_sp500_proxy_prices_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert migration_versions(db) == [14]
    assert_sp500_proxy_prices_contract(db)
    assert_seeded_sp500_proxy_prices(db)


def test_growth_month_history_repository_helpers_upsert_and_fetch(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    june = repositories.upsert_growth_month_history(
        db,
        account_seq="account-1",
        year=2026,
        month=6,
        net_worth_krw=1_000_000,
        monthly_dividend_krw=12_500,
    )
    repositories.upsert_growth_month_history(
        db,
        account_seq="account-1",
        year=2026,
        month=5,
        net_worth_krw=900_000,
        monthly_dividend_krw=7_500,
    )
    repositories.upsert_growth_month_history(
        db,
        account_seq="account-2",
        year=2026,
        month=4,
        net_worth_krw=500_000,
        monthly_dividend_krw=2_500,
    )
    updated_june = repositories.upsert_growth_month_history(
        db,
        account_seq="account-1",
        year=2026,
        month=6,
        net_worth_krw=1_100_000,
        monthly_dividend_krw=15_000,
    )

    read_db = connect(db_path)
    fetched_june = repositories.fetch_growth_month_history_row(
        read_db,
        account_seq="account-1",
        year=2026,
        month=6,
    )
    rows = repositories.fetch_growth_month_history_rows(read_db, account_seq="account-1")

    assert updated_june["id"] == june["id"]
    assert fetched_june["net_worth_krw"] == 1_100_000
    assert fetched_june["monthly_dividend_krw"] == 15_000
    assert [(row["year"], row["month"]) for row in rows] == [(2026, 5), (2026, 6)]
    assert [row["account_seq"] for row in rows] == ["account-1", "account-1"]


def test_growth_month_history_upsert_can_defer_transaction_commit(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    db.execute("begin")
    saved = repositories.upsert_growth_month_history(
        db,
        account_seq="account-1",
        year=2026,
        month=7,
        net_worth_krw=1_200_000,
        monthly_dividend_krw=20_000,
        commit=False,
    )
    assert saved["net_worth_krw"] == 1_200_000

    db.rollback()

    assert (
        repositories.fetch_growth_month_history_row(
            db,
            account_seq="account-1",
            year=2026,
            month=7,
        )
        is None
    )


def test_sp500_proxy_price_repository_helpers_fetch_seeded_ratios(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert [
        (row["year"], row["price"]) for row in repositories.fetch_sp500_proxy_prices(db)
    ] == SEEDED_SP500_PROXY_PRICES
    ratios = repositories.fetch_sp500_proxy_annual_return_ratios(
        db,
        years=[2021, 2022, 2023, 2024, 2025, 2026],
        current_year=2026,
    )
    assert ratios[2022] == pytest.approx(351.34 / 436.57)
    assert ratios[2023] == pytest.approx(436.80 / 351.34)
    assert ratios[2024] == pytest.approx(538.81 / 436.80)
    assert ratios[2025] == pytest.approx(627.13 / 538.81)
    assert 2021 not in ratios
    assert 2026 not in ratios


def test_sp500_proxy_price_repository_helpers_upsert_seeded_price(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    saved_2025 = repositories.upsert_sp500_proxy_price(db, year=2025, price=125)
    updated_2025 = repositories.upsert_sp500_proxy_price(db, year=2025, price=130)
    saved_2026 = repositories.upsert_sp500_proxy_price(db, year=2026, price=160)

    assert updated_2025["id"] == saved_2025["id"]
    assert updated_2025["price"] == 130
    assert saved_2026["price"] == 160
    prices = {
        row["year"]: row["price"] for row in repositories.fetch_sp500_proxy_prices(db)
    }
    assert prices[2025] == 130
    assert prices[2026] == 160


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

    assert migration_versions(db) == [9, 10, 11, 12, 13, 14]
    assert_toss_only_schema(db)
    assert db.execute("select count(*) from fx_rates").fetchone()[0] == 1
    assert db.execute("select count(*) from goals").fetchone()[0] == 1
    assert db.execute("select count(*) from backups").fetchone()[0] == 1
    assert db.execute("select value from settings where key = 'theme'").fetchone()[0] == "dark"


def test_migrate_from_v10_adds_toss_order_history_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 10)
    create_toss_only_survivor_tables(db)
    db.commit()

    migrate(db)

    assert migration_versions(db) == [10, 11, 12, 13, 14]
    assert {
        "toss_order_import_runs",
        "toss_orders",
    } <= table_names(db)
    assert index_names(db) >= TOSS_ORDER_INDEXES
    assert_removed_local_ledger_tables_gone(db)


def test_migrate_from_v10_adds_toss_order_history_contract(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 10)
    create_toss_only_survivor_tables(db)
    db.commit()

    migrate(db)

    assert_toss_order_history_contract(db)


def test_migrate_from_v11_adds_growth_month_history_table(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 11)
    create_toss_only_survivor_tables(db)
    create_v11_toss_order_history_tables(db)
    db.commit()

    migrate(db)

    assert migration_versions(db) == [11, 12, 13, 14]
    assert_growth_month_history_contract(db)


def test_migrate_from_v12_adds_sp500_proxy_prices_table(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 12)
    create_toss_only_survivor_tables(db)
    create_v11_toss_order_history_tables(db)
    db.execute(
        """
        create table growth_month_history (
          id integer primary key,
          account_seq text not null,
          year integer not null check (year >= 2000 and year <= 2099),
          month integer not null check (month >= 1 and month <= 12),
          net_worth_krw real not null check (net_worth_krw >= 0),
          monthly_dividend_krw real not null default 0 check (monthly_dividend_krw >= 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, year, month)
        )
        """
    )
    db.execute(
        """
        create index idx_growth_month_history_account_period
        on growth_month_history(account_seq, year, month)
        """
    )
    db.commit()

    migrate(db)

    assert migration_versions(db) == [12, 13, 14]
    assert_sp500_proxy_prices_contract(db)
    assert_seeded_sp500_proxy_prices(db)


def test_migrate_from_v13_seeds_sp500_proxy_prices_without_overwriting_existing_rows(
    tmp_path,
):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 13)
    create_toss_only_survivor_tables(db)
    create_v11_toss_order_history_tables(db)
    db.execute(
        """
        create table growth_month_history (
          id integer primary key,
          account_seq text not null,
          year integer not null check (year >= 2000 and year <= 2099),
          month integer not null check (month >= 1 and month <= 12),
          net_worth_krw real not null check (net_worth_krw >= 0),
          monthly_dividend_krw real not null default 0 check (monthly_dividend_krw >= 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, year, month)
        )
        """
    )
    db.execute(
        """
        create index idx_growth_month_history_account_period
        on growth_month_history(account_seq, year, month)
        """
    )
    db.execute(
        """
        create table sp500_proxy_prices (
          id integer primary key,
          year integer not null check (year >= 2000 and year <= 2099),
          proxy_symbol text not null default 'VOO' check (proxy_symbol = 'VOO'),
          price real not null check (price > 0),
          currency text not null default 'USD' check (currency = 'USD'),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(proxy_symbol, year)
        )
        """
    )
    db.execute(
        """
        create index idx_sp500_proxy_prices_symbol_year
        on sp500_proxy_prices(proxy_symbol, year)
        """
    )
    db.execute("insert into sp500_proxy_prices(year, price) values (?, ?)", (2025, 700.0))
    db.commit()

    migrate(db)

    assert migration_versions(db) == [13, 14]
    assert [(row["year"], row["price"]) for row in db.execute(
        """
        select year, price
        from sp500_proxy_prices
        where year between 2021 and 2025
        order by year
        """
    ).fetchall()] == [
        (2021, 436.57),
        (2022, 351.34),
        (2023, 436.80),
        (2024, 538.81),
        (2025, 700.0),
    ]


def test_migrate_from_v10_rolls_back_partial_v11_schema_when_schema_application_fails(
    tmp_path, monkeypatch
):
    schema_path = tmp_path / "broken_schema.sql"
    schema_path.write_text(
        """
        create table if not exists toss_order_import_runs (
          id integer primary key
        );
        create table broken_table (
        """,
        encoding="utf-8",
    )
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 10)
    create_toss_only_survivor_tables(db)
    db.commit()
    monkeypatch.setattr(migrations, "SCHEMA_PATH", schema_path)

    with pytest.raises((sqlite3.Error, RuntimeError)):
        migrate(db)

    assert "toss_order_import_runs" not in table_names(db)
    assert migration_versions(db) == [10]


def test_migrate_upgrades_version_7_database_to_v11_and_preserves_goals(tmp_path):
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
    assert migration_versions(db) == [7, 8, 9, 10, 11, 12, 13, 14]
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


def test_migrate_upgrades_version_4_database_to_v11_and_removes_local_tables(tmp_path):
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

    assert migration_versions(db) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    assert_toss_only_schema(db)


def test_migrate_upgrades_version_1_database_to_v11_and_removes_local_tables(tmp_path):
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

    assert migration_versions(db) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
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

    assert migration_versions(db) == [14]
    assert_toss_only_schema(db)


def test_migrate_supports_plain_sqlite_connections(tmp_path):
    db = sqlite3.connect(tmp_path / "portfolio.sqlite")

    migrate(db)
    migrate(db)

    assert migration_versions(db) == [14]


def test_migrate_rejects_newer_schema_version(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 15)
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

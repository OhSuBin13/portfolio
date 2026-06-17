from datetime import date

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, upsert_holding
from portfolio_app.services.growth import (
    build_growth_history,
    create_or_refresh_today_snapshot,
)


def create_growth_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def builtin_asset_id(db, *, asset_type: str, currency: str = "KRW") -> int:
    row = db.execute(
        """
        select id
        from assets
        where type = ?
          and currency = ?
          and symbol is null
          and market is null
        order by id
        limit 1
        """,
        (asset_type, currency),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def insert_snapshot(db, snapshot_date: str, net_worth_krw: float) -> None:
    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_date, net_worth_krw, max(net_worth_krw, 0), 0, 0, "{}", "manual"),
    )
    db.commit()


def insert_transaction(db, occurred_on: str, transaction_type: str, amount: float) -> None:
    db.execute(
        """
        insert into transactions(occurred_on, type, amount, currency, memo)
        values (?, ?, ?, ?, ?)
        """,
        (occurred_on, transaction_type, amount, "KRW", transaction_type),
    )
    db.commit()


def test_create_or_refresh_today_snapshot_updates_one_kst_date(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        account_id = create_account(db, name="원화 현금", type="cash")
        cash_asset_id = builtin_asset_id(db, asset_type="cash")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_000_000,
            average_cost=None,
        )

        first = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_500_000,
            average_cost=None,
        )
        second = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        count = db.execute("select count(*) from portfolio_snapshots").fetchone()[0]
    finally:
        db.close()

    assert count == 1
    assert first.id == second.id
    assert first.net_worth_krw == 1_000_000
    assert second.net_worth_krw == 1_500_000
    assert second.snapshot_date == date(2026, 6, 17)


def test_create_or_refresh_today_snapshot_can_keep_existing_row(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        account_id = create_account(db, name="원화 현금", type="cash")
        cash_asset_id = builtin_asset_id(db, asset_type="cash")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_000_000,
            average_cost=None,
        )
        first = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=2_000_000,
            average_cost=None,
        )
        second = create_or_refresh_today_snapshot(
            db,
            source="market_sync",
            today=date(2026, 6, 17),
            refresh=False,
        )
    finally:
        db.close()

    assert second.id == first.id
    assert second.net_worth_krw == 1_000_000
    assert second.source == "manual"


def test_monthly_history_excludes_external_cashflow_and_includes_income(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 56_200_000)
        insert_transaction(db, "2026-06-05", "deposit", 5_000_000)
        insert_transaction(db, "2026-06-12", "withdrawal", 1_000_000)
        insert_transaction(db, "2026-06-20", "dividend", 200_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert len(rows) == 1
    row = rows[0]
    assert row.period == "2026-06"
    assert row.external_cash_flow_krw == 4_000_000
    assert row.dividend_interest_krw == 200_000
    assert row.profit_krw == 2_200_000
    assert row.growth_rate == pytest.approx(0.044)
    assert row.cumulative_profit_krw == 2_200_000
    assert row.cumulative_growth_rate == pytest.approx(0.044)


def test_monthly_history_excludes_debt_payments_from_profit(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 51_000_000)
        insert_transaction(db, "2026-06-15", "debt_payment", 1_000_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert rows[0].external_cash_flow_krw == 1_000_000
    assert rows[0].profit_krw == 0
    assert rows[0].growth_rate == 0


def test_growth_rate_is_missing_when_starting_net_worth_is_zero(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 0)
        insert_snapshot(db, "2026-06-30", 1_000_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert rows[0].profit_krw == 1_000_000
    assert rows[0].growth_rate is None
    assert rows[0].cumulative_growth_rate is None


def test_annual_history_uses_annual_snapshots_and_cashflow(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-01-02", 10_000_000)
        insert_snapshot(db, "2026-12-30", 11_300_000)
        insert_transaction(db, "2026-03-01", "deposit", 1_000_000)
        insert_transaction(db, "2026-09-01", "interest", 300_000)

        rows = build_growth_history(
            db,
            period="annual",
            from_value="2026",
            to_value="2026",
        )
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].period == "2026"
    assert rows[0].external_cash_flow_krw == 1_000_000
    assert rows[0].dividend_interest_krw == 300_000
    assert rows[0].profit_krw == 300_000
    assert rows[0].growth_rate == pytest.approx(0.03)

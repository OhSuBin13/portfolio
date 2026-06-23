from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

from portfolio_app.api.growth import (
    TodaySnapshotRequest,
    create_today_snapshot,
    get_growth_history,
    get_snapshots,
)
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def create_growth_api_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


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


def test_growth_api_routes_delegate_to_service_layer():
    backend_dir = Path(__file__).parents[1]
    api_source = (backend_dir / "src/portfolio_app/api/growth.py").read_text()

    assert "from portfolio_app.services import growth as growth_service" in api_source
    assert "growth_service.create_or_refresh_today_snapshot" in api_source
    assert "growth_service.list_snapshots" in api_source
    assert "growth_service.build_growth_history" in api_source
    assert "portfolio_snapshots" not in api_source
    assert "from transactions" not in api_source


def test_growth_api_tests_call_route_functions_directly():
    test_source = Path(__file__).read_text()

    forbidden_import = "from fastapi.testclient import " + "TestClient"
    assert forbidden_import not in test_source


def test_create_today_snapshot_endpoint_defaults_to_manual_source(tmp_path):
    db = create_growth_api_db(tmp_path)
    try:
        snapshot = create_today_snapshot(db)
    finally:
        db.close()

    payload = snapshot.model_dump(mode="json")
    assert payload["snapshot_date"]
    assert payload["net_worth_krw"] == 0
    assert payload["gross_assets_krw"] == 0
    assert payload["debt_krw"] == 0
    assert payload["asset_mix"] == {}
    assert payload["source"] == "manual"


def test_create_today_snapshot_endpoint_accepts_explicit_source(tmp_path):
    db = create_growth_api_db(tmp_path)
    try:
        snapshot = create_today_snapshot(db, TodaySnapshotRequest(source="import"))
    finally:
        db.close()

    assert snapshot.source == "import"


def test_list_snapshots_endpoint_returns_date_order(tmp_path):
    db = create_growth_api_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-02", 2_000_000)
        insert_snapshot(db, "2026-06-01", 1_000_000)
        rows = get_snapshots(
            db,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
    finally:
        db.close()

    payload = [row.model_dump(mode="json") for row in rows]
    assert [row["snapshot_date"] for row in payload] == ["2026-06-01", "2026-06-02"]


def test_growth_history_endpoint_returns_monthly_rows(tmp_path):
    db = create_growth_api_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 56_200_000)
        db.execute(
            """
            insert into transactions(occurred_on, type, amount, currency, memo)
            values (?, ?, ?, ?, ?)
            """,
            ("2026-06-05", "deposit", 5_000_000, "KRW", "입금"),
        )
        db.execute(
            """
            insert into transactions(occurred_on, type, amount, currency, memo)
            values (?, ?, ?, ?, ?)
            """,
            ("2026-06-20", "dividend", 200_000, "KRW", "배당"),
        )
        db.commit()
        rows = get_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    payload = [row.model_dump(mode="json") for row in rows]
    assert payload[0]["period"] == "2026-06"
    assert payload[0]["external_cash_flow_krw"] == 5_000_000
    assert payload[0]["dividend_interest_krw"] == 200_000
    assert payload[0]["profit_krw"] == 1_200_000


def test_growth_history_endpoint_returns_400_when_usd_cashflow_has_no_fx_rate(tmp_path):
    db = create_growth_api_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 56_200_000)
        db.execute(
            """
            insert into transactions(
              occurred_on, type, amount, currency, fx_rate_to_krw, memo
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-05", "deposit", 1_000, "USD", None, "USD 입금"),
        )
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            get_growth_history(
                db,
                period="monthly",
                from_value="2026-06",
                to_value="2026-06",
            )
    finally:
        db.close()

    assert exc_info.value.status_code == 400
    assert "환율" in exc_info.value.detail

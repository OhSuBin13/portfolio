from pathlib import Path

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    app = create_app(settings=settings)
    return TestClient(app)


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


def test_create_today_snapshot_endpoint_defaults_to_manual_source(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post("/api/growth/snapshots/today")

    assert response.status_code == 201
    payload = response.json()
    assert payload["snapshot_date"]
    assert payload["net_worth_krw"] == 0
    assert payload["gross_assets_krw"] == 0
    assert payload["debt_krw"] == 0
    assert payload["asset_mix"] == {}
    assert payload["source"] == "manual"


def test_create_today_snapshot_endpoint_accepts_explicit_source(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post("/api/growth/snapshots/today", json={"source": "import"})

    assert response.status_code == 201
    assert response.json()["source"] == "import"


def test_list_snapshots_endpoint_returns_date_order(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
    try:
        insert_snapshot(db, "2026-06-02", 2_000_000)
        insert_snapshot(db, "2026-06-01", 1_000_000)
    finally:
        db.close()

    response = client.get("/api/growth/snapshots?from=2026-06-01&to=2026-06-30")

    assert response.status_code == 200
    assert [row["snapshot_date"] for row in response.json()] == ["2026-06-01", "2026-06-02"]


def test_growth_history_endpoint_returns_monthly_rows(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
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
    finally:
        db.close()

    response = client.get("/api/growth/history?period=monthly&from=2026-06&to=2026-06")

    assert response.status_code == 200
    assert response.json()[0]["period"] == "2026-06"
    assert response.json()[0]["external_cash_flow_krw"] == 5_000_000
    assert response.json()[0]["dividend_interest_krw"] == 200_000
    assert response.json()[0]["profit_krw"] == 1_200_000


def test_growth_history_endpoint_returns_400_when_usd_cashflow_has_no_fx_rate(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
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
    finally:
        db.close()

    response = client.get("/api/growth/history?period=monthly&from=2026-06&to=2026-06")

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]

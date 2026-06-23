import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, create_asset
from portfolio_app.services.growth import create_or_refresh_today_snapshot
from portfolio_app.services.market_data import sync_market_data_for_settings
from portfolio_app.services.transactions import apply_transaction


def create_test_client(
    tmp_path,
    *,
    alpha_vantage_api_key: str = "",
    raise_server_exceptions: bool = True,
):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        alpha_vantage_api_key=alpha_vantage_api_key,
    )
    app = create_app(settings=settings)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_market_sync_implementation_lives_in_service_module():
    backend_dir = Path(__file__).parents[1]
    api_source = (backend_dir / "src/portfolio_app/api/market_data.py").read_text()
    service_source = (backend_dir / "src/portfolio_app/services/market_data.py").read_text()

    assert "async def sync_market_data_for_settings" not in api_source
    assert "create_or_refresh_today_snapshot" not in api_source
    assert "async def sync_market_data_for_settings" in service_source
    assert "create_or_refresh_market_sync_snapshot" in service_source


def test_market_data_api_uses_typed_response_schema(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    schema = create_app(settings=settings).openapi()

    manual_schema = schema["paths"]["/api/market-data/manual-price"]["post"]["responses"]["201"][
        "content"
    ]["application/json"]["schema"]
    status_schema = schema["paths"]["/api/market-data/status"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    sync_schema = schema["paths"]["/api/market-data/sync"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert manual_schema == {"$ref": "#/components/schemas/MarketPriceSnapshot"}
    assert status_schema["items"] == {"$ref": "#/components/schemas/MarketDataStatus"}
    assert sync_schema == {"$ref": "#/components/schemas/MarketSyncResponse"}
    assert "MarketSyncRow" in schema["components"]["schemas"]


def test_manual_price_endpoint_validates_stores_snapshot_and_updates_summary(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "국내 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "005930",
            "name": "삼성전자",
            "type": "stock_etf",
            "currency": "KRW",
            "market": "KR",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 2,
            "amount": 100_000,
            "currency": "KRW",
            "memo": "초기 수량",
        },
    )

    invalid = client.post(
        "/api/market-data/manual-price",
        json={"asset_id": asset["id"], "price_krw": 0},
    )
    response = client.post(
        "/api/market-data/manual-price",
        json={"asset_id": asset["id"], "price_krw": 75_000, "source": "user"},
    )

    assert invalid.status_code == 400
    assert "가격" in invalid.json()["detail"]
    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["asset_id"] == asset["id"]
    assert snapshot["source"] == "user"
    assert snapshot["price_krw"] == 75_000
    assert snapshot["status"] == "manual"
    assert client.get("/api/summary?refresh=false").json()["net_worth_krw"] == 150_000


def test_status_endpoint_returns_latest_snapshot_and_failure_info(tmp_path):
    client = create_test_client(tmp_path)
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset["id"], "alpha_vantage", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset["id"],
                "alpha_vantage",
                500,
                "USD",
                700_000,
                "2026-06-12T10:00:00",
                "stale",
                "rate limit",
            ),
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/market-data/status")

    assert response.status_code == 200
    assert response.json() == [
        {
            "asset_id": asset["id"],
            "source": "alpha_vantage",
            "price_krw": 700_000,
            "status": "stale",
            "error_message": "rate limit",
            "fetched_at": "2026-06-12T10:00:00",
        }
    ]


def test_sync_records_stale_status_when_alpha_vantage_key_missing(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "해외 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 1,
            "amount": 500,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "기존 보유",
        },
    )
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset["id"], "alpha_vantage", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()

    response = client.post("/api/market-data/sync")
    status_response = client.get("/api/market-data/status")

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "asset_id": asset["id"],
            "symbol": "VOO",
            "status": "stale",
            "error_message": "Alpha Vantage API 키가 필요합니다.",
        }
    ]
    latest = status_response.json()[0]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "stale"
    assert latest["price_krw"] == 700_000
    assert "Alpha Vantage API 키" in latest["error_message"]
    assert client.get("/api/summary?refresh=false").json()["net_worth_krw"] == 700_000
    payload = response.json()
    assert payload["snapshot"]["source"] == "market_sync"
    assert payload["snapshot"]["net_worth_krw"] == 700_000

    db = connect(client.app.state.settings.database_path)
    try:
        count = db.execute("select count(*) from portfolio_snapshots").fetchone()[0]
    finally:
        db.close()

    assert count == 1


def test_sync_reports_snapshot_error_when_summary_cannot_be_valued(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash"},
    ).json()
    usd_cash = next(
        asset
        for asset in client.get("/api/assets").json()
        if asset["type"] == "cash" and asset["currency"] == "USD"
    )
    db = connect(client.app.state.settings.database_path)
    db.execute(
        "insert into holdings(account_id, asset_id, quantity) values (?, ?, ?)",
        (account["id"], usd_cash["id"], 1_000),
    )
    db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, amount, currency, memo
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-17",
            "deposit",
            account["id"],
            usd_cash["id"],
            1_000,
            "USD",
            "환율 없는 달러 현금",
        ),
    )
    db.commit()
    db.close()

    response = client.post("/api/market-data/sync")

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "snapshot_error" in response.json()
    assert "환율" in response.json()["snapshot_error"]


def test_market_sync_refreshes_existing_market_sync_snapshot_after_price_update(
    tmp_path,
    httpx_mock,
):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        alpha_vantage_api_key="demo-key",
    )
    db = connect(settings.database_path)
    try:
        migrate(db)
        account_id = create_account(db, name="해외 증권", type="brokerage")
        asset_id = create_asset(
            db,
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            type="stock_etf",
            currency="USD",
            market="US",
        )
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="buy",
            account_id=account_id,
            asset_id=asset_id,
            quantity=1,
            amount=500,
            currency="USD",
            fx_rate_to_krw=1400,
            memo="old market sync snapshot",
        )
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, "alpha_vantage", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
        old_snapshot = create_or_refresh_today_snapshot(
            db,
            source="market_sync",
            refresh=True,
        )
        assert old_snapshot.net_worth_krw == 700_000
        httpx_mock.add_response(json={"Global Quote": {"05. price": "600.00"}})
        httpx_mock.add_response(
            text="""
            <p class="no_today"><em class="no_down"><em class="no_down">1,300.00</em></em></p>
            <p class="no_exday">
              <em class="no_down">1.00</em>
              <em class="no_down"><span class="ico minus">-</span>0.08%</em>
            </p>
            """,
        )

        response = asyncio.run(sync_market_data_for_settings(settings, db))

        assert response["snapshot"].source == "market_sync"
        assert response["snapshot"].net_worth_krw == 780_000
        row = db.execute("select * from portfolio_snapshots").fetchone()
    finally:
        db.close()
    assert row["net_worth_krw"] == 780_000


def test_sync_records_stale_status_when_http_provider_fails_with_previous_price(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        alpha_vantage_api_key="demo-key",
        raise_server_exceptions=False,
    )
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset["id"], "alpha_vantage", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "stale"
    assert "500 Internal Server Error" in response.json()["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "stale"
    assert latest["price_krw"] == 700_000
    assert "500 Internal Server Error" in latest["error_message"]


def test_sync_sanitizes_http_provider_error_without_leaking_alpha_vantage_key(
    tmp_path,
    httpx_mock,
):
    secret_key = "secret-alpha-key-123"
    client = create_test_client(
        tmp_path,
        alpha_vantage_api_key=secret_key,
        raise_server_exceptions=False,
    )
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset["id"], "alpha_vantage", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]

    assert response.status_code == 200
    error_message = response.json()["results"][0]["error_message"]
    assert error_message == "시세 제공자 요청 실패: HTTP 500 Internal Server Error"
    assert latest["error_message"] == error_message
    assert secret_key not in str(response.json())
    assert secret_key not in str(latest)
    assert "apikey=" not in str(response.json()).lower()
    assert "apikey=" not in str(latest).lower()


def test_sync_records_failed_status_without_previous_price_and_preserves_fallback_summary(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        alpha_vantage_api_key="demo-key",
        raise_server_exceptions=False,
    )
    account = client.post(
        "/api/accounts",
        json={"name": "해외 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 1,
            "amount": 500,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "fallback valuation",
        },
    )
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "failed"
    assert "500 Internal Server Error" in response.json()["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "failed"
    assert latest["price_krw"] == 0
    assert "500 Internal Server Error" in latest["error_message"]
    assert summary["net_worth_krw"] == 700_000


def test_summary_uses_manual_price_when_later_failed_snapshot_exists(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "국내 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "005930",
            "name": "삼성전자",
            "type": "stock_etf",
            "currency": "KRW",
            "market": "KR",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 2,
            "amount": 100_000,
            "currency": "KRW",
            "memo": "manual fallback",
        },
    )
    client.post(
        "/api/market-data/manual-price",
        json={"asset_id": asset["id"], "price_krw": 75_000},
    )
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            "update price_snapshots set fetched_at = ? where asset_id = ? and status = ?",
            ("2026-06-12T09:00:00", asset["id"], "manual"),
        )
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset["id"],
                "market_data",
                0,
                "KRW",
                0,
                "2026-06-12T10:00:00",
                "failed",
                "provider down",
            ),
        )
        db.commit()
    finally:
        db.close()

    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert latest["status"] == "failed"
    assert latest["price_krw"] == 0
    assert summary["net_worth_krw"] == 150_000


def test_kr_stock_sync_records_unsupported_provider_and_preserves_summary(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        alpha_vantage_api_key="demo-key",
        raise_server_exceptions=False,
    )
    account = client.post(
        "/api/accounts",
        json={"name": "국내 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "005930",
            "name": "삼성전자",
            "type": "stock_etf",
            "currency": "KRW",
            "market": "KR",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 2,
            "amount": 100_000,
            "currency": "KRW",
            "memo": "KR fallback",
        },
    )

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "failed"
    assert "KR 시장 시세 동기화" in response.json()["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "failed"
    assert "KR 시장 시세 동기화" in latest["error_message"]
    assert summary["net_worth_krw"] == 100_000


def test_us_stock_sync_uses_alpha_quote_and_fx_rate_for_summary(tmp_path, httpx_mock):
    client = create_test_client(tmp_path, alpha_vantage_api_key="demo-key")
    account = client.post(
        "/api/accounts",
        json={"name": "해외 증권", "type": "brokerage"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "buy",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 2,
            "amount": 1000,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "US stock",
        },
    )
    httpx_mock.add_response(json={"Global Quote": {"05. price": "600.00"}})
    httpx_mock.add_response(
        text="""
        <p class="no_today"><em class="no_down"><em class="no_down">1,300.00</em></em></p>
        <p class="no_exday">
          <em class="no_down">1.00</em>
          <em class="no_down"><span class="ico minus">-</span>0.08%</em>
        </p>
        """,
    )

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "ok"
    assert latest["status"] == "ok"
    assert latest["source"] == "alpha_vantage"
    assert latest["price_krw"] == 780_000
    assert summary["net_worth_krw"] == 1_560_000

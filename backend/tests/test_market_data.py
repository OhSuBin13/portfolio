import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.repositories import create_account, create_asset
from portfolio_app.services.growth import create_or_refresh_today_snapshot
from portfolio_app.services.market_data import insert_price_snapshot, sync_market_data_for_settings
from portfolio_app.services.transactions import apply_transaction


def create_test_client(
    tmp_path,
    *,
    toss_api_key: str = "",
    toss_secret_key: str = "",
    raise_server_exceptions: bool = True,
):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        toss_api_key=toss_api_key,
        toss_secret_key=toss_secret_key,
        market_sync_enabled=False,
        backup_enabled=False,
    )
    app = create_app(settings=settings)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def run_market_sync(client: TestClient) -> dict[str, object]:
    db = connect(client.app.state.settings.database_path)
    try:
        return asyncio.run(sync_market_data_for_settings(client.app.state.settings, db))
    finally:
        db.close()


def add_toss_fx_rate_response(httpx_mock, *, rate: str = "1300.00") -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "fx-token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://openapi.tossinvest.com/api/v1/exchange-rate"
            "?baseCurrency=USD&quoteCurrency=KRW"
        ),
        json={
            "result": {
                "baseCurrency": "USD",
                "quoteCurrency": "KRW",
                "rate": rate,
                "midRate": rate,
                "basisPoint": "0",
                "rateChangeType": "EQUAL",
                "validFrom": "2026-03-25T09:30:00+09:00",
                "validUntil": "2026-03-25T09:31:00+09:00",
            }
        },
    )


def test_market_sync_implementation_lives_in_service_module():
    backend_dir = Path(__file__).parents[1]
    api_source = (backend_dir / "src/portfolio_app/api/market_data.py").read_text()
    service_source = (backend_dir / "src/portfolio_app/services/market_data.py").read_text()

    assert "async def sync_market_data_for_settings" not in api_source
    assert "create_or_refresh_today_snapshot" not in api_source
    assert "async def sync_market_data_for_settings" in service_source
    assert "create_or_refresh_market_sync_snapshot" in service_source


def test_alpha_vantage_provider_code_is_removed():
    backend_dir = Path(__file__).parents[1]
    service_source = (backend_dir / "src/portfolio_app/services/market_data.py").read_text()
    config_source = (backend_dir / "src/portfolio_app/config.py").read_text()
    settings_source = (
        backend_dir.parent / "frontend/src/components/SettingsPage.tsx"
    ).read_text()

    combined_source = "\n".join([service_source, config_source, settings_source])

    assert "AlphaVantageProvider" not in combined_source
    assert "alpha_vantage" not in combined_source
    assert "alphavantage.co" not in combined_source
    assert "Alpha Vantage" not in combined_source


def test_market_data_api_exposes_status_only(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    schema = create_app(settings=settings).openapi()
    backend_dir = Path(__file__).parents[1]
    api_source = (backend_dir / "src/portfolio_app/api/market_data.py").read_text()

    status_schema = schema["paths"]["/api/market-data/status"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert "/api/market-data/manual-price" not in schema["paths"]
    assert "/api/market-data/sync" not in schema["paths"]
    assert status_schema["items"] == {"$ref": "#/components/schemas/MarketDataStatus"}
    assert "def create_manual_price" not in api_source
    assert "def sync_market_data" not in api_source


def test_manual_price_snapshot_updates_summary(tmp_path):
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
    db = connect(client.app.state.settings.database_path)
    try:
        row = insert_price_snapshot(
            db,
            asset_id=asset["id"],
            source="user",
            price=75_000,
            currency="KRW",
            price_krw=75_000,
            status="manual",
        )
        db.commit()
    finally:
        db.close()

    assert row["asset_id"] == asset["id"]
    assert row["source"] == "user"
    assert row["price_krw"] == 75_000
    assert row["status"] == "manual"
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
            (asset["id"], "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
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
                "toss",
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
            "source": "toss",
            "price_krw": 700_000,
            "status": "stale",
            "error_message": "rate limit",
            "fetched_at": "2026-06-12T10:00:00",
        }
    ]


def test_sync_records_stale_status_when_toss_credentials_missing(tmp_path):
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
            (asset["id"], "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()

    payload = run_market_sync(client)
    status_response = client.get("/api/market-data/status")

    assert payload["results"] == [
        {
            "asset_id": asset["id"],
            "symbol": "VOO",
            "status": "stale",
            "error_message": "Toss API 인증 정보가 필요합니다.",
        }
    ]
    latest = status_response.json()[0]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "stale"
    assert latest["price_krw"] == 700_000
    assert "Toss API 인증 정보" in latest["error_message"]
    assert client.get("/api/summary?refresh=false").json()["net_worth_krw"] == 700_000
    assert payload["snapshot"].source == "market_sync"
    assert payload["snapshot"].net_worth_krw == 700_000

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

    payload = run_market_sync(client)

    assert payload["results"] == []
    assert "snapshot_error" in payload
    assert "환율" in str(payload["snapshot_error"])


def test_market_sync_refreshes_existing_market_sync_snapshot_after_price_update(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    db = connect(client.app.state.settings.database_path)
    try:
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
            (asset_id, "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
        old_snapshot = create_or_refresh_today_snapshot(
            db,
            source="market_sync",
            refresh=True,
        )
        assert old_snapshot.net_worth_krw == 700_000
    finally:
        db.close()

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=VOO",
        json={"result": [{"symbol": "VOO", "lastPrice": "600.00", "currency": "USD"}]},
    )
    add_toss_fx_rate_response(httpx_mock)

    payload = run_market_sync(client)

    assert payload["snapshot"].source == "market_sync"
    assert payload["snapshot"].net_worth_krw == 780_000
    db = connect(client.app.state.settings.database_path)
    try:
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
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
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
            (asset["id"], "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]

    assert payload["results"][0]["status"] == "stale"
    assert "500 Internal Server Error" in payload["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "stale"
    assert latest["price_krw"] == 700_000
    assert "500 Internal Server Error" in latest["error_message"]


def test_sync_sanitizes_http_provider_error_without_leaking_toss_secret(
    tmp_path,
    httpx_mock,
):
    secret_key = "secret-toss-key-123"
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key=secret_key,
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
            (asset["id"], "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.commit()
    finally:
        db.close()
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        status_code=500,
        json={"message": "provider down"},
    )

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]

    error_message = payload["results"][0]["error_message"]
    assert error_message == "시세 제공자 요청 실패: HTTP 500 Internal Server Error"
    assert latest["error_message"] == error_message
    assert secret_key not in str(payload)
    assert secret_key not in str(latest)
    assert "client_secret" not in str(payload).lower()
    assert "client_secret" not in str(latest).lower()


def test_sync_records_failed_status_without_previous_price_and_preserves_fallback_summary(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
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
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert payload["results"][0]["status"] == "failed"
    assert "500 Internal Server Error" in payload["results"][0]["error_message"]
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
    db = connect(client.app.state.settings.database_path)
    try:
        insert_price_snapshot(
            db,
            asset_id=asset["id"],
            source="user",
            price=75_000,
            currency="KRW",
            price_krw=75_000,
            status="manual",
        )
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


def test_kr_stock_sync_records_missing_toss_credentials_and_preserves_summary(
    tmp_path,
):
    client = create_test_client(
        tmp_path,
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

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert payload["results"][0]["status"] == "failed"
    assert "Toss API 인증 정보" in payload["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "failed"
    assert "Toss API 인증 정보" in latest["error_message"]
    assert summary["net_worth_krw"] == 100_000


def test_kr_stock_sync_uses_toss_quote_for_summary(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
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
            "memo": "KR stock",
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=005930",
        json={
            "result": [
                {
                    "symbol": "005930",
                    "timestamp": "2026-06-27T10:00:00+09:00",
                    "lastPrice": "75000",
                    "currency": "KRW",
                }
            ]
        },
    )

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert payload["results"] == [
        {
            "asset_id": asset["id"],
            "symbol": "005930",
            "status": "ok",
            "error_message": "",
        }
    ]
    assert latest["asset_id"] == asset["id"]
    assert latest["source"] == "toss"
    assert latest["status"] == "ok"
    assert latest["price_krw"] == 75_000
    assert summary["net_worth_krw"] == 150_000


def test_us_stock_sync_uses_toss_quote_and_fx_rate_for_summary(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
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
            "quantity": 2,
            "amount": 1000,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "US stock",
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=VOO",
        json={"result": [{"symbol": "VOO", "lastPrice": "600.00", "currency": "USD"}]},
    )
    add_toss_fx_rate_response(httpx_mock)

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()
    db = connect(client.app.state.settings.database_path)
    try:
        fx_row = db.execute(
            """
            select base_currency, quote_currency, rate, source, fetched_at
            from fx_rates
            order by id
            limit 1
            """
        ).fetchone()
    finally:
        db.close()

    assert payload["results"][0]["status"] == "ok"
    assert latest["status"] == "ok"
    assert latest["source"] == "toss"
    assert latest["price_krw"] == 780_000
    assert summary["net_worth_krw"] == 1_560_000
    assert dict(fx_row) == {
        "base_currency": "USD",
        "quote_currency": "KRW",
        "rate": 1300,
        "source": "toss",
        "fetched_at": "2026-03-25T09:30:00+09:00",
    }


def test_us_stock_sync_batches_toss_quotes_and_reuses_fx_rate(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    account = client.post(
        "/api/accounts",
        json={"name": "해외 증권", "type": "brokerage"},
    ).json()
    voo = client.post(
        "/api/assets",
        json={
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    qqq = client.post(
        "/api/assets",
        json={
            "symbol": "QQQ",
            "name": "Invesco QQQ Trust",
            "type": "stock_etf",
            "currency": "USD",
            "market": "US",
        },
    ).json()
    for asset in [voo, qqq]:
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
                "memo": "US stock batch",
            },
        )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=VOO%2CQQQ",
        json={
            "result": [
                {"symbol": "VOO", "lastPrice": "600.00", "currency": "USD"},
                {"symbol": "QQQ", "lastPrice": "400.00", "currency": "USD"},
            ]
        },
    )
    add_toss_fx_rate_response(httpx_mock)

    payload = run_market_sync(client)
    summary = client.get("/api/summary?refresh=false").json()
    requests = httpx_mock.get_requests()
    price_requests = [
        request
        for request in requests
        if request.method == "GET" and request.url.path == "/api/v1/prices"
    ]
    fx_requests = [
        request
        for request in requests
        if request.method == "GET" and request.url.path == "/api/v1/exchange-rate"
    ]

    assert [result["status"] for result in payload["results"]] == ["ok", "ok"]
    assert summary["net_worth_krw"] == 1_300_000
    assert [request.url.params["symbols"] for request in price_requests] == ["VOO,QQQ"]
    assert len(fx_requests) == 1


def test_us_stock_sync_uses_toss_quote_when_credentials_exist(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
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
            "quantity": 2,
            "amount": 1000,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "US stock",
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=VOO",
        json={
            "result": [
                {
                    "symbol": "VOO",
                    "timestamp": "2026-06-27T10:00:00+09:00",
                    "lastPrice": "600.00",
                    "currency": "USD",
                }
            ]
        },
    )
    add_toss_fx_rate_response(httpx_mock)

    payload = run_market_sync(client)
    latest = client.get("/api/market-data/status").json()[0]
    summary = client.get("/api/summary?refresh=false").json()

    assert payload["results"][0]["status"] == "ok"
    assert latest["status"] == "ok"
    assert latest["source"] == "toss"
    assert latest["price_krw"] == 780_000
    assert summary["net_worth_krw"] == 1_560_000

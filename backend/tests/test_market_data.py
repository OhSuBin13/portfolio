import pytest
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.services.market_data import (
    CoinGeckoProvider,
    FrankfurterProvider,
    MarketQuote,
    keep_last_good_quote,
)


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


def test_keep_last_good_quote_uses_previous_value_on_error():
    previous = MarketQuote(symbol="VOO", price=500.0, currency="USD", source="alpha_vantage")

    result = keep_last_good_quote(previous=previous, error_message="rate limit")

    assert result.price == 500.0
    assert result.status == "stale"
    assert result.error_message == "rate limit"


@pytest.mark.asyncio
async def test_coingecko_provider_parses_simple_price(httpx_mock):
    httpx_mock.add_response(json={"bitcoin": {"krw": 150_000_000}})
    provider = CoinGeckoProvider()

    quote = await provider.fetch_crypto_quote("bitcoin", vs_currency="krw")

    assert quote.symbol == "bitcoin"
    assert quote.price == 150_000_000
    assert quote.currency == "KRW"


@pytest.mark.asyncio
async def test_frankfurter_provider_parses_pair_rate(httpx_mock):
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FrankfurterProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1375.5


def test_manual_price_endpoint_validates_stores_snapshot_and_updates_summary(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "국내 증권", "type": "brokerage", "currency": "KRW"},
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
    assert client.get("/api/summary").json()["net_worth_krw"] == 150_000


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
        json={"name": "해외 증권", "type": "brokerage", "currency": "USD"},
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
    assert client.get("/api/summary").json()["net_worth_krw"] == 700_000


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


def test_sync_records_failed_status_when_http_provider_fails_without_previous_price(
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
    httpx_mock.add_response(status_code=500, json={"message": "provider down"})

    response = client.post("/api/market-data/sync")
    latest = client.get("/api/market-data/status").json()[0]

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "failed"
    assert "500 Internal Server Error" in response.json()["results"][0]["error_message"]
    assert latest["asset_id"] == asset["id"]
    assert latest["status"] == "failed"
    assert latest["price_krw"] == 0
    assert "500 Internal Server Error" in latest["error_message"]

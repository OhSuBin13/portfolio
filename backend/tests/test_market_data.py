import logging

import pytest
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.services.market_data import (
    AlphaVantageProvider,
    FallbackFxRateProvider,
    FrankfurterProvider,
    MarketQuote,
    NaverFinanceProvider,
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
async def test_alpha_vantage_logs_unexpected_payload_without_api_key(httpx_mock, caplog):
    secret_key = "secret-alpha-key-123"
    httpx_mock.add_response(json={"Information": "rate limit reached"})
    provider = AlphaVantageProvider(secret_key)

    with (
        caplog.at_level(logging.WARNING, logger="portfolio_app.services.market_data"),
        pytest.raises(ValueError, match="시세 정보를 찾을 수 없습니다"),
    ):
        await provider.fetch_equity_quote("mu")

    records = [
        record
        for record in caplog.records
        if record.message.startswith("Alpha Vantage quote response missing Global Quote")
    ]
    assert len(records) == 1
    assert records[0].symbol == "MU"
    assert records[0].payload_summary == {
        "keys": ["Information"],
        "messages": {"Information": "rate limit reached"},
    }
    assert "symbol=MU" in records[0].message
    assert "rate limit reached" in records[0].message
    logged = "\n".join(str(record.__dict__) for record in caplog.records)
    assert secret_key not in logged
    assert "apikey" not in logged.lower()


@pytest.mark.asyncio
async def test_frankfurter_provider_parses_pair_rate(httpx_mock):
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FrankfurterProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1375.5


@pytest.mark.asyncio
async def test_naver_finance_provider_parses_usd_krw_rate_and_change_percent(httpx_mock):
    httpx_mock.add_response(
        text="""
        <div class="spot">
          <div class="today">
            <p class="no_today">
              <em class="no_down"><em class="no_down">
                <span class="no1">1</span><span class="shim">,</span><span class="no5">5</span>
                <span class="no1">1</span><span class="no3">3</span><span class="jum">.</span>
                <span class="no2">2</span><span class="no0">0</span>
              </em></em>
            </p>
            <p class="no_exday">
              <span class="txt_comparison">전일대비</span>
              <em class="no_down"><span class="ico down"></span><span class="no2">2</span></em>
              <em class="no_down">
                <span class="parenthesis1">(</span>
                <span class="ico minus">-</span><span class="no0">0</span><span class="jum">.</span>
                <span class="no1">1</span><span class="no5">5</span><span class="per">%</span>
                <span class="parenthesis2">)</span>
              </em>
            </p>
          </div>
        </div>
        """,
        headers={"content-type": "text/html;charset=EUC-KR"},
    )
    provider = NaverFinanceProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1513.2
    assert rate.change_percent == -0.15
    assert rate.source == "naver_finance"


@pytest.mark.asyncio
async def test_fallback_fx_rate_provider_uses_frankfurter_when_naver_fails(httpx_mock):
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FallbackFxRateProvider(NaverFinanceProvider(), FrankfurterProvider())

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.rate == 1375.5
    assert rate.change_percent is None
    assert rate.source == "frankfurter"


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
    monkeypatch,
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

    async def fail_if_alpha_is_called(_self, _symbol):
        raise AssertionError("Alpha Vantage must not be called for KR assets.")

    monkeypatch.setattr(
        "portfolio_app.services.market_data.AlphaVantageProvider.fetch_equity_quote",
        fail_if_alpha_is_called,
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

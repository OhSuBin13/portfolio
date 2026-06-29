import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.repositories import create_account, create_asset
from portfolio_app.services.growth import create_or_refresh_today_snapshot
from portfolio_app.services.market_data import insert_price_snapshot, sync_market_data_for_settings
from portfolio_app.services.summary import build_summary
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


def connect_client_db(client: TestClient):
    return connect(client.app.state.settings.database_path)


def run_market_sync(client: TestClient) -> dict[str, object]:
    db = connect_client_db(client)
    try:
        return asyncio.run(sync_market_data_for_settings(client.app.state.settings, db))
    finally:
        db.close()


def latest_market_status(client: TestClient) -> list[dict[str, object]]:
    db = connect_client_db(client)
    try:
        rows = db.execute(
            """
            select ps.asset_id, ps.source, ps.price_krw, ps.status, ps.error_message, ps.fetched_at
            from price_snapshots ps
            where ps.id = (
                select latest.id
                from price_snapshots latest
                where latest.asset_id = ps.asset_id
                order by latest.fetched_at desc, latest.id desc
                limit 1
            )
            order by ps.asset_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def local_summary(client: TestClient):
    db = connect_client_db(client)
    try:
        return build_summary(db)
    finally:
        db.close()


def create_market_holding(
    client: TestClient,
    *,
    symbol: str,
    name: str,
    market: str,
    currency: str,
    quantity: float,
    amount: float,
    fx_rate_to_krw: float | None = None,
) -> int:
    db = connect_client_db(client)
    try:
        account_id = create_account(db, name=f"{market} 증권", type="brokerage")
        asset_id = create_asset(
            db,
            symbol=symbol,
            name=name,
            type="stock_etf",
            currency=currency,
            market=market,
        )
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="buy",
            account_id=account_id,
            asset_id=asset_id,
            quantity=quantity,
            amount=amount,
            currency=currency,
            fx_rate_to_krw=fx_rate_to_krw,
            memo=f"{symbol} 보유",
        )
        return asset_id
    finally:
        db.close()


def add_toss_fx_rate_response(
    httpx_mock,
    *,
    rate: str = "1300.00",
    include_token: bool = True,
) -> None:
    if include_token:
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
    combined_source = "\n".join([service_source, config_source])

    assert "AlphaVantageProvider" not in combined_source
    assert "alpha_vantage" not in combined_source
    assert "alphavantage.co" not in combined_source
    assert "Alpha Vantage" not in combined_source


def test_market_data_api_is_not_registered_in_toss_only_app(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        market_sync_enabled=False,
        backup_enabled=False,
    )
    app = create_app(settings=settings)
    client = TestClient(app)
    schema = app.openapi()
    backend_dir = Path(__file__).parents[1]
    api_source = (backend_dir / "src/portfolio_app/api/market_data.py").read_text()

    assert "/api/market-data/status" not in schema["paths"]
    assert "/api/market-data/manual-price" not in schema["paths"]
    assert "/api/market-data/sync" not in schema["paths"]
    assert client.get("/api/market-data/status").status_code == 404
    assert "def create_manual_price" not in api_source
    assert "def sync_market_data" not in api_source


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/accounts"),
        ("post", "/api/accounts"),
        ("get", "/api/assets"),
        ("post", "/api/assets"),
        ("get", "/api/transactions"),
        ("post", "/api/transactions"),
    ],
)
def test_local_ledger_routes_are_not_registered_in_toss_only_app(tmp_path, method, path):
    client = create_test_client(tmp_path)

    response = client.post(path, json={}) if method == "post" else client.get(path)

    assert response.status_code == 404


def test_insert_price_snapshot_updates_local_summary_service(tmp_path):
    client = create_test_client(tmp_path)
    asset_id = create_market_holding(
        client,
        symbol="005930",
        name="삼성전자",
        market="KR",
        currency="KRW",
        quantity=2,
        amount=100_000,
    )
    db = connect_client_db(client)
    try:
        row = insert_price_snapshot(
            db,
            asset_id=asset_id,
            source="user",
            price=75_000,
            currency="KRW",
            price_krw=75_000,
            status="manual",
        )
        db.commit()
    finally:
        db.close()

    result = local_summary(client)

    assert row["asset_id"] == asset_id
    assert row["source"] == "user"
    assert row["price_krw"] == 75_000
    assert row["status"] == "manual"
    assert result.summary.net_worth_krw == 150_000


def test_latest_market_status_reads_latest_snapshot_from_storage(tmp_path):
    client = create_test_client(tmp_path)
    asset_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
    )
    db = connect_client_db(client)
    try:
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, "toss", 500, "USD", 700_000, "2026-06-12T09:00:00", "ok", ""),
        )
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
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

    assert latest_market_status(client) == [
        {
            "asset_id": asset_id,
            "source": "toss",
            "price_krw": 700_000,
            "status": "stale",
            "error_message": "rate limit",
            "fetched_at": "2026-06-12T10:00:00",
        }
    ]


def test_sync_records_stale_status_when_toss_credentials_missing(tmp_path):
    client = create_test_client(tmp_path)
    asset_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
    )
    db = connect_client_db(client)
    try:
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
    finally:
        db.close()

    payload = run_market_sync(client)
    latest = latest_market_status(client)[0]

    assert payload["results"] == [
        {
            "asset_id": asset_id,
            "symbol": "VOO",
            "status": "stale",
            "error_message": "Toss API 인증 정보가 필요합니다.",
        }
    ]
    assert latest["asset_id"] == asset_id
    assert latest["status"] == "stale"
    assert latest["price_krw"] == 700_000
    assert "Toss API 인증 정보" in latest["error_message"]
    assert local_summary(client).summary.net_worth_krw == 700_000
    assert payload["snapshot"].source == "market_sync"
    assert payload["snapshot"].net_worth_krw == 700_000


def test_sync_reports_snapshot_error_when_summary_cannot_be_valued(tmp_path):
    client = create_test_client(tmp_path)
    db = connect_client_db(client)
    try:
        account_id = create_account(db, name="달러 현금", type="cash")
        usd_cash = db.execute(
            """
            select *
            from assets
            where type = 'cash' and currency = 'USD'
            """
        ).fetchone()
        db.execute(
            "insert into holdings(account_id, asset_id, quantity) values (?, ?, ?)",
            (account_id, usd_cash["id"], 1_000),
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
                account_id,
                usd_cash["id"],
                1_000,
                "USD",
                "환율 없는 달러 현금",
            ),
        )
        db.commit()
    finally:
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
    db = connect_client_db(client)
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
    add_toss_fx_rate_response(httpx_mock, include_token=False)

    payload = run_market_sync(client)

    assert payload["snapshot"].source == "market_sync"
    assert payload["snapshot"].net_worth_krw == 780_000
    db = connect_client_db(client)
    try:
        row = db.execute("select * from portfolio_snapshots").fetchone()
    finally:
        db.close()
    assert row["net_worth_krw"] == 780_000


@pytest.mark.parametrize(
    ("status", "previous_price_krw"),
    [
        ("stale", 700_000),
        ("failed", 0),
    ],
)
def test_sync_records_provider_failure_status(
    tmp_path,
    httpx_mock,
    status,
    previous_price_krw,
):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
        raise_server_exceptions=False,
    )
    asset_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
    )
    if previous_price_krw > 0:
        db = connect_client_db(client)
        try:
            db.execute(
                """
                insert into price_snapshots(
                    asset_id, source, price, currency, price_krw, fetched_at, status, error_message
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, "toss", 500, "USD", previous_price_krw, "2026-06-12T09:00:00", "ok", ""),
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
    latest = latest_market_status(client)[0]

    assert payload["results"][0]["status"] == status
    assert "500 Internal Server Error" in payload["results"][0]["error_message"]
    assert latest["asset_id"] == asset_id
    assert latest["status"] == status
    assert latest["price_krw"] == previous_price_krw
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
    asset_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
    )
    db = connect_client_db(client)
    try:
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
    finally:
        db.close()
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        status_code=500,
        json={"message": "provider down"},
    )

    payload = run_market_sync(client)
    latest = latest_market_status(client)[0]

    error_message = payload["results"][0]["error_message"]
    assert error_message == "시세 제공자 요청 실패: HTTP 500 Internal Server Error"
    assert latest["error_message"] == error_message
    assert secret_key not in str(payload)
    assert secret_key not in str(latest)
    assert "client_secret" not in str(payload).lower()
    assert "client_secret" not in str(latest).lower()


def test_summary_uses_manual_price_when_later_failed_snapshot_exists(tmp_path):
    client = create_test_client(tmp_path)
    asset_id = create_market_holding(
        client,
        symbol="005930",
        name="삼성전자",
        market="KR",
        currency="KRW",
        quantity=2,
        amount=100_000,
    )
    db = connect_client_db(client)
    try:
        insert_price_snapshot(
            db,
            asset_id=asset_id,
            source="user",
            price=75_000,
            currency="KRW",
            price_krw=75_000,
            status="manual",
        )
        db.execute(
            "update price_snapshots set fetched_at = ? where asset_id = ? and status = ?",
            ("2026-06-12T09:00:00", asset_id, "manual"),
        )
        db.execute(
            """
            insert into price_snapshots(
                asset_id, source, price, currency, price_krw, fetched_at, status, error_message
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
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

    latest = latest_market_status(client)[0]
    result = local_summary(client)

    assert latest["status"] == "failed"
    assert latest["price_krw"] == 0
    assert result.summary.net_worth_krw == 150_000


def test_kr_stock_sync_records_missing_toss_credentials_and_preserves_summary(
    tmp_path,
):
    client = create_test_client(
        tmp_path,
        raise_server_exceptions=False,
    )
    asset_id = create_market_holding(
        client,
        symbol="005930",
        name="삼성전자",
        market="KR",
        currency="KRW",
        quantity=2,
        amount=100_000,
    )

    payload = run_market_sync(client)
    latest = latest_market_status(client)[0]
    result = local_summary(client)

    assert payload["results"][0]["status"] == "failed"
    assert "Toss API 인증 정보" in payload["results"][0]["error_message"]
    assert latest["asset_id"] == asset_id
    assert latest["status"] == "failed"
    assert "Toss API 인증 정보" in latest["error_message"]
    assert result.summary.net_worth_krw == 100_000


def test_kr_stock_sync_uses_toss_quote_for_summary(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    asset_id = create_market_holding(
        client,
        symbol="005930",
        name="삼성전자",
        market="KR",
        currency="KRW",
        quantity=2,
        amount=100_000,
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
    latest = latest_market_status(client)[0]
    result = local_summary(client)

    assert payload["results"] == [
        {
            "asset_id": asset_id,
            "symbol": "005930",
            "status": "ok",
            "error_message": "",
        }
    ]
    assert latest["asset_id"] == asset_id
    assert latest["source"] == "toss"
    assert latest["status"] == "ok"
    assert latest["price_krw"] == 75_000
    assert result.summary.net_worth_krw == 150_000


def test_us_stock_sync_uses_toss_quote_and_fx_rate_for_summary(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    asset_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=2,
        amount=1000,
        fx_rate_to_krw=1400,
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
    add_toss_fx_rate_response(httpx_mock, include_token=False)

    payload = run_market_sync(client)
    latest = latest_market_status(client)[0]
    result = local_summary(client)
    db = connect_client_db(client)
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
    token_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "POST" and request.url.path == "/oauth2/token"
    ]

    assert payload["results"][0]["status"] == "ok"
    assert latest["asset_id"] == asset_id
    assert latest["status"] == "ok"
    assert latest["source"] == "toss"
    assert latest["price_krw"] == 780_000
    assert result.summary.net_worth_krw == 1_560_000
    assert len(token_requests) == 1
    assert dict(fx_row) == {
        "base_currency": "USD",
        "quote_currency": "KRW",
        "rate": 1300,
        "source": "toss",
        "fetched_at": "2026-03-25T00:30:00+00:00",
    }


def test_us_stock_sync_batches_toss_quotes_and_reuses_fx_rate(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    voo_id = create_market_holding(
        client,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
    )
    qqq_id = create_market_holding(
        client,
        symbol="QQQ",
        name="Invesco QQQ Trust",
        market="US",
        currency="USD",
        quantity=1,
        amount=500,
        fx_rate_to_krw=1400,
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
    add_toss_fx_rate_response(httpx_mock, include_token=False)

    payload = run_market_sync(client)
    result = local_summary(client)
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

    assert [row["asset_id"] for row in payload["results"]] == [voo_id, qqq_id]
    assert [row["status"] for row in payload["results"]] == ["ok", "ok"]
    assert result.summary.net_worth_krw == 1_300_000
    assert [request.url.params["symbols"] for request in price_requests] == ["VOO,QQQ"]
    assert len(fx_requests) == 1

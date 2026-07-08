import pytest
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.main import create_app

LOCAL_FRONTEND_ORIGIN = "http://127.0.0.1:5173"


def create_test_client(tmp_path, **settings_overrides):
    settings_values = {
        "data_dir": tmp_path,
        "database_path": tmp_path / "portfolio.sqlite",
        "backup_dir": tmp_path / "backups",
        "toss_api_key": "",
        "toss_secret_key": "",
    }
    settings_values.update(settings_overrides)
    settings = Settings(**settings_values)
    app = create_app(settings=settings)
    return TestClient(app)


def assert_korean_validation_error(response, expected_text):
    detail = response.json()["detail"]
    detail_text = str(detail)

    assert response.status_code in {400, 422}
    assert expected_text in detail_text
    assert "Field required" not in detail_text
    assert "Extra inputs are not permitted" not in detail_text
    assert "Input should be" not in detail_text
    assert "valid date" not in detail_text
    assert "valid integer" not in detail_text
    assert "Unable to parse input string" not in detail_text


def mock_zero_buying_power(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=KRW",
        json={"result": {"currency": "KRW", "cashBuyingPower": "0"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=USD",
        json={"result": {"currency": "USD", "cashBuyingPower": "0"}},
    )


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_exposes_toss_only_portfolio_paths(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    paths = set(schema["paths"])
    assert {
        "/api/summary",
        "/api/toss/accounts",
        "/api/toss/holdings",
        "/api/growth/month-history",
        "/api/growth/month-history/{year}/{month}",
        "/api/growth/annual-history",
        "/api/growth/sp500-proxy-prices",
        "/api/growth/sp500-proxy-prices/{year}",
        "/api/goals",
        "/api/backups",
    } <= paths
    assert {
        "/api/accounts",
        "/api/assets",
        "/api/assets/stock-metadata",
        "/api/transactions",
        "/api/growth",
        "/api/growth/history",
        "/api/growth/snapshots",
        "/api/growth/snapshots/today",
        "/api/goals/progress",
        "/api/market-data/status",
    }.isdisjoint(paths)
    summary_parameters = schema["paths"]["/api/summary"]["get"]["parameters"]
    assert summary_parameters == [
        {
            "name": "account_seq",
            "in": "query",
            "required": True,
            "schema": {"type": "string", "minLength": 1, "title": "Account Seq"},
        }
    ]


def test_openapi_exposes_growth_history_contract(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    put_month = paths["/api/growth/month-history/{year}/{month}"]["put"]
    delete_month = paths["/api/growth/month-history/{year}/{month}"]["delete"]
    get_months = paths["/api/growth/month-history"]["get"]
    get_annual = paths["/api/growth/annual-history"]["get"]
    get_sp500_proxy_prices = paths["/api/growth/sp500-proxy-prices"]["get"]
    put_sp500_proxy_price = paths["/api/growth/sp500-proxy-prices/{year}"]["put"]

    assert put_month["tags"] == ["growth"]
    assert put_month["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GrowthMonthHistoryUpsert"
    }
    assert put_month["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GrowthMonthHistoryRow"
    }
    assert delete_month["tags"] == ["growth"]
    assert delete_month["responses"]["204"]["description"] == "Successful Response"

    month_schema = get_months["responses"]["200"]["content"]["application/json"]["schema"]
    assert month_schema["type"] == "array"
    assert month_schema["items"] == {"$ref": "#/components/schemas/GrowthMonthHistoryRow"}

    annual_schema = get_annual["responses"]["200"]["content"]["application/json"]["schema"]
    assert annual_schema["type"] == "array"
    assert annual_schema["items"] == {"$ref": "#/components/schemas/GrowthAnnualHistoryRow"}
    annual_component = schema["components"]["schemas"]["GrowthAnnualHistoryRow"]
    assert "sp500_annual_return_ratio" in annual_component["properties"]

    sp500_proxy_schema = get_sp500_proxy_prices["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert sp500_proxy_schema["type"] == "array"
    assert sp500_proxy_schema["items"] == {"$ref": "#/components/schemas/Sp500ProxyPriceRow"}
    assert put_sp500_proxy_price["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Sp500ProxyPriceRow"
    }

    account_seq_parameter = {
        "name": "account_seq",
        "in": "query",
        "required": True,
        "schema": {"type": "string", "minLength": 1, "title": "Account Seq"},
    }
    assert account_seq_parameter in get_months["parameters"]
    assert account_seq_parameter in get_annual["parameters"]
    assert account_seq_parameter in put_month["parameters"]


def test_openapi_exposes_toss_order_history_paths(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = set(response.json()["paths"])
    assert "/api/toss/order-imports" in paths
    assert "/api/toss/orders" in paths
    assert "/api/transactions" not in paths


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/accounts"),
        ("post", "/api/accounts"),
        ("get", "/api/assets"),
        ("post", "/api/assets"),
        ("get", "/api/assets/stock-metadata?symbol=005930"),
        ("get", "/api/transactions"),
        ("post", "/api/transactions"),
        ("get", "/api/growth"),
        ("get", "/api/growth/history"),
        ("get", "/api/growth/snapshots"),
        ("post", "/api/growth/snapshots/today"),
        ("get", "/api/goals/progress"),
        ("get", "/api/market-data/status"),
    ],
)
def test_local_portfolio_routes_are_not_registered(tmp_path, method, path):
    client = create_test_client(tmp_path)

    response = client.post(path, json={}) if method == "post" else client.get(path)

    assert response.status_code == 404


def test_toss_accounts_endpoint_returns_provider_accounts(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": 12345,
                    "accountType": "BROKERAGE",
                }
            ]
        },
        is_optional=True,
    )

    response = client.get("/api/toss/accounts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "account_seq": "12345",
            "account_no": "123-45-67890",
            "account_type": "BROKERAGE",
            "display_name": "토스증권 123-45-67890",
        }
    ]


def test_toss_accounts_endpoint_uses_ttl_cache(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )

    first = client.get("/api/toss/accounts")
    second = client.get("/api/toss/accounts")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    account_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/accounts"
    ]
    assert len(account_requests) == 1


def test_toss_accounts_endpoint_retries_cold_cache_rate_limit_once(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        status_code=429,
        headers={"Retry-After": "0", "X-RateLimit-Remaining": "0"},
        json={"error": {"code": "rate-limit-exceeded"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )

    response = client.get("/api/toss/accounts")

    assert response.status_code == 200
    assert response.json()[0]["account_seq"] == "acct-1"
    account_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/accounts"
    ]
    assert len(account_requests) == 2


def test_toss_holdings_endpoint_returns_provider_holdings(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "marketCountry": "KR",
                        "currency": "KRW",
                        "quantity": "10",
                        "lastPrice": "75000",
                        "averagePurchasePrice": "70000",
                        "marketValue": {"amount": "750000"},
                    }
                ]
            }
        },
        is_optional=True,
    )

    response = client.get("/api/toss/holdings?account_seq=%20acct-1%20")

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "005930",
            "name": "삼성전자",
            "market": "KR",
            "currency": "KRW",
            "quantity": 10.0,
            "average_purchase_price": 70000.0,
            "last_price": 75000.0,
            "market_value": 750000.0,
        }
    ]
    assert httpx_mock.get_requests()[1].headers["x-tossinvest-account"] == "acct-1"


def test_toss_holdings_endpoint_rejects_blank_account_seq(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/toss/holdings?account_seq=%20%20")

    assert response.status_code == 400
    assert response.json()["detail"] == "Toss 계좌 식별자를 입력해 주세요."


def test_toss_candles_endpoint_fetches_1000_daily_candles_with_pagination(
    tmp_path,
    httpx_mock,
):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    before_values = [
        None,
        "2026-03-24T09:00:00+09:00",
        "2026-03-23T09:00:00+09:00",
        "2026-03-22T09:00:00+09:00",
        "2026-03-21T09:00:00+09:00",
    ]
    next_values = [
        "2026-03-24T09:00:00+09:00",
        "2026-03-23T09:00:00+09:00",
        "2026-03-22T09:00:00+09:00",
        "2026-03-21T09:00:00+09:00",
        None,
    ]
    for index, (before, next_before) in enumerate(zip(before_values, next_values, strict=True)):
        match_params = {
            "symbol": "005930",
            "interval": "1d",
            "count": "200",
            "adjusted": "true",
        }
        if before is not None:
            match_params["before"] = before
        httpx_mock.add_response(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/candles",
            match_params=match_params,
            json={
                "result": {
                    "candles": [
                        {
                            "timestamp": f"2026-03-{25 - index:02d}T09:00:00+09:00",
                            "openPrice": str(71000 + index),
                            "highPrice": str(72000 + index),
                            "lowPrice": str(70000 + index),
                            "closePrice": str(71500 + index),
                            "volume": str(1_000_000 + index),
                            "currency": "KRW",
                        }
                    ],
                    "nextBefore": next_before,
                }
            },
            is_optional=True,
        )

    response = client.get("/api/toss/candles?symbol=%20005930%20&interval=1d&limit=1000")

    assert response.status_code == 200
    candles = response.json()
    assert len(candles) == 5
    assert candles[0] == {
        "symbol": "005930",
        "timestamp": "2026-03-25T09:00:00+09:00",
        "open": 71000.0,
        "high": 72000.0,
        "low": 70000.0,
        "close": 71500.0,
        "volume": 1000000.0,
    }
    candle_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/candles"
    ]
    assert len(candle_requests) == 5
    assert candle_requests[0].url.params["count"] == "200"
    assert "limit" not in candle_requests[0].url.params
    assert candle_requests[1].url.params["before"] == "2026-03-24T09:00:00+09:00"


def test_toss_candles_endpoint_rejects_blank_symbol(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/toss/candles?symbol=%20%20")

    assert response.status_code == 400
    assert response.json()["detail"] == "Toss 캔들 조회 종목 심볼을 입력해 주세요."


def test_chart_marker_memo_endpoint_upserts_and_lists_notes(tmp_path):
    client = create_test_client(tmp_path)

    first_response = client.post(
        "/api/toss/chart-marker-memos",
        json={
            "account_seq": " acct-1 ",
            "symbol": " voo ",
            "marker_key": "order:buy-1",
            "memo": "첫 매수 근거",
        },
    )
    second_response = client.post(
        "/api/toss/chart-marker-memos",
        json={
            "account_seq": "acct-1",
            "symbol": "VOO",
            "marker_key": "order:buy-1",
            "memo": "장기 보유 판단",
        },
    )
    list_response = client.get(
        "/api/toss/chart-marker-memos?account_seq=acct-1&symbol=voo",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["memo"] == "장기 보유 판단"
    assert list_response.status_code == 200
    assert list_response.json() == [second_response.json()]


def test_chart_marker_memo_endpoint_deletes_note(tmp_path):
    client = create_test_client(tmp_path)

    saved_response = client.post(
        "/api/toss/chart-marker-memos",
        json={
            "account_seq": "acct-1",
            "symbol": "VOO",
            "marker_key": "order:buy-1",
            "memo": "삭제할 판단 메모",
        },
    )
    delete_response = client.delete(
        "/api/toss/chart-marker-memos?account_seq=acct-1&symbol=voo&marker_key=order%3Abuy-1",
    )
    list_response = client.get(
        "/api/toss/chart-marker-memos?account_seq=acct-1&symbol=VOO",
    )

    assert saved_response.status_code == 200
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_toss_order_import_endpoint_imports_open_orders(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/orders?status=OPEN&limit=100",
        json={
            "result": {
                "orders": [
                    {
                        "orderId": "order-1",
                        "symbol": "005930",
                        "side": "BUY",
                        "orderType": "LIMIT",
                        "timeInForce": "DAY",
                        "status": "OPEN",
                        "price": "70000",
                        "quantity": "10",
                        "orderAmount": None,
                        "currency": "KRW",
                        "orderedAt": "2026-06-29T09:30:00+09:00",
                        "canceledAt": None,
                        "execution": {
                            "filledQuantity": "3",
                            "averageFilledPrice": "70100",
                            "filledAmount": "210300",
                            "commission": "100",
                            "tax": "0",
                            "filledAt": "2026-06-29T09:31:15+09:00",
                            "settlementDate": "2026-07-01",
                        },
                    }
                ],
                "nextCursor": None,
                "hasNext": False,
            }
        },
        is_optional=True,
    )

    import_response = client.post(
        "/api/toss/order-imports",
        json={"account_seq": "acct-1", "status": "OPEN"},
    )

    assert import_response.status_code == 201
    assert import_response.json()["imported_count"] == 1
    orders_response = client.get("/api/toss/orders?account_seq=acct-1")
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert orders[0]["order_id"] == "order-1"
    assert orders[0]["filled_amount"] == "210300"


def test_toss_order_import_endpoint_rejects_reversed_date_range(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://openapi.tossinvest.com/api/v1/orders"
            "?status=CLOSED&from=2026-07-01&to=2026-06-01&limit=100"
        ),
        json={"result": {"orders": [], "nextCursor": None, "hasNext": False}},
        is_optional=True,
    )

    response = client.post(
        "/api/toss/order-imports",
        json={
            "account_seq": "acct-1",
            "status": "CLOSED",
            "from_date": "2026-07-01",
            "to_date": "2026-06-01",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "조회 시작일은 종료일보다 늦을 수 없습니다."
    order_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/orders"
    ]
    assert order_requests == []


def test_toss_orders_endpoint_rejects_reversed_date_range(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get(
        "/api/toss/orders?account_seq=acct-1&from=2026-07-01&to=2026-06-01"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "조회 시작일은 종료일보다 늦을 수 없습니다."


def test_summary_endpoint_uses_toss_account_seq(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    goal = client.post(
        "/api/goals",
        json={
            "name": "순자산 100만",
            "type": "net_worth",
            "target_amount_krw": 1_000_000,
        },
    ).json()
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "marketCountry": "KR",
                        "currency": "KRW",
                        "quantity": "10",
                        "lastPrice": "75000",
                        "averagePurchasePrice": "70000",
                        "marketValue": {"amount": "750000"},
                    }
                ]
            }
        },
        is_optional=True,
    )
    mock_zero_buying_power(httpx_mock)
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
                "rate": "1400",
                "validFrom": "2026-06-29T09:00:00+09:00",
            }
        },
        is_optional=True,
    )

    response = client.get("/api/summary?account_seq=%20acct-1%20")

    assert response.status_code == 200
    body = response.json()
    assert body["net_worth_krw"] == 750000.0
    assert body["asset_mix"] == {"stock_etf": 100.0}
    assert body["asset_allocations"] == [
        {
            "asset_key": "KR:005930",
            "asset_type": "stock_etf",
            "symbol": "005930",
            "name": "삼성전자",
            "label": "005930",
            "market": "KR",
            "currency": "KRW",
            "value_krw": 750000.0,
            "percent": 100.0,
        }
    ]
    assert body["goal_progress"] == [
        {
            "goal": {
                "id": goal["id"],
                "name": "순자산 100만",
                "type": "net_worth",
                "target_amount_krw": 1_000_000,
            },
            "current_amount_krw": 750000.0,
            "percent": 75.0,
            "remaining_krw": 250000.0,
        }
    ]
    assert httpx_mock.get_requests()[1].headers["x-tossinvest-account"] == "acct-1"


def test_toss_endpoints_share_app_auth_client(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "VOO",
                        "name": "Vanguard S&P 500 ETF",
                        "marketCountry": "US",
                        "currency": "USD",
                        "quantity": "3",
                        "lastPrice": "500",
                        "averagePurchasePrice": "450",
                        "marketValue": {"amount": "1500"},
                    }
                ]
            }
        },
    )
    mock_zero_buying_power(httpx_mock)
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
                "rate": "1400",
                "validFrom": "2026-06-29T09:00:00+09:00",
            }
        },
    )

    accounts_response = client.get("/api/toss/accounts")
    summary_response = client.get("/api/summary?account_seq=acct-1")

    assert accounts_response.status_code == 200
    assert summary_response.status_code == 200
    assert summary_response.json()["usd_krw_rate"] == 1400.0
    token_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "POST" and request.url.path == "/oauth2/token"
    ]
    assert len(token_requests) == 1


def test_summary_endpoint_rejects_blank_account_seq(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary?account_seq=%20%20")

    assert response.status_code == 400
    assert response.json()["detail"] == "Toss 계좌 식별자를 입력해 주세요."


def test_summary_endpoint_returns_empty_snapshot(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={"result": {"items": []}},
    )
    mock_zero_buying_power(httpx_mock)

    response = client.get("/api/summary?account_seq=acct-1")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 0
    assert response.json()["usd_krw_rate"] is None
    assert response.json()["asset_mix"] == {}


def test_summary_allows_local_frontend_cors_origin(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={"result": {"items": []}},
    )
    mock_zero_buying_power(httpx_mock)

    response = client.get(
        "/api/summary?account_seq=acct-1",
        headers={"Origin": LOCAL_FRONTEND_ORIGIN},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_FRONTEND_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_api_post_preflight_allows_local_frontend_origin(tmp_path):
    client = create_test_client(tmp_path)

    response = client.options(
        "/api/goals",
        headers={
            "Origin": LOCAL_FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_FRONTEND_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_can_create_and_list_goal(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/goals",
        json={
            "name": "순자산 1억",
            "type": "net_worth",
            "target_amount_krw": 100_000_000,
        },
    )

    assert response.status_code == 201
    goal = response.json()
    assert goal["name"] == "순자산 1억"
    assert client.get("/api/goals").json()[0]["id"] == goal["id"]


def test_goal_create_rejects_numeric_string_target_amount(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/goals",
        json={
            "name": "순자산 1억",
            "type": "net_worth",
            "target_amount_krw": "100000000",
        },
    )

    assert_korean_validation_error(response, "target_amount_krw: 입력값 형식")

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

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.main import create_app


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


def test_summary_endpoint_documents_typed_response_model(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    summary_response = schema["components"]["schemas"]["SummaryResponse"]
    toss_allocation = schema["components"]["schemas"]["TossAssetAllocation"]
    assert schema["paths"]["/api/summary"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/SummaryResponse"}
    assert schema["paths"]["/api/summary"]["get"]["parameters"] == [
        {
            "name": "account_seq",
            "in": "query",
            "required": True,
            "schema": {"type": "string", "minLength": 1, "title": "Account Seq"},
        }
    ]
    assert "asset_mix" in summary_response["properties"]
    assert "buying_power" in summary_response["properties"]
    assert "buying_power_total_krw" in summary_response["properties"]
    assert summary_response["properties"]["asset_allocations"]["items"] == {
        "$ref": "#/components/schemas/TossAssetAllocation"
    }
    assert {
        "asset_key",
        "asset_type",
        "symbol",
        "name",
        "label",
        "market",
        "currency",
        "value_krw",
        "percent",
    } <= set(toss_allocation["properties"])
    assert toss_allocation["properties"]["asset_type"]["const"] == "stock_etf"
    assert toss_allocation["properties"]["market"]["enum"] == ["KR", "US"]
    assert toss_allocation["properties"]["currency"]["enum"] == ["USD", "KRW"]
    assert summary_response["properties"]["goal_progress"]["items"] == {
        "$ref": "#/components/schemas/GoalProgress"
    }


def test_summary_endpoint_requires_account_seq(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary")

    assert response.status_code == 400
    assert "account_seq" in str(response.json()["detail"])


def test_summary_endpoint_uses_toss_krw_holdings(tmp_path, httpx_mock):
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
    )
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

    response = client.get("/api/summary?account_seq=acct-1")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 750000.0
    assert response.json()["usd_krw_rate"] is None
    assert response.json()["asset_allocations"] == [
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
    assert httpx_mock.get_requests()[1].headers["x-tossinvest-account"] == "acct-1"


def test_summary_endpoint_fetches_toss_fx_for_usd_holdings(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_reusable=True,
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

    response = client.get("/api/summary?account_seq=acct-1")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 2_100_000.0
    assert response.json()["usd_krw_rate"] == 1400.0
    assert response.json()["asset_allocations"] == [
        {
            "asset_key": "US:VOO",
            "asset_type": "stock_etf",
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "label": "VOO",
            "market": "US",
            "currency": "USD",
            "value_krw": 2_100_000.0,
            "percent": 100.0,
        }
    ]


def test_summary_endpoint_includes_buying_power_in_goal_progress(tmp_path, httpx_mock):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    app = create_app(settings=settings)
    client = TestClient(app)
    import sqlite3

    from portfolio_app.services import goals as goal_service

    db = sqlite3.connect(settings.database_path)
    db.row_factory = sqlite3.Row
    try:
        goal_service.create_goal(
            db,
            name="순자산 목표",
            type="net_worth",
            target_amount_krw=1_000_000,
        )
    finally:
        db.close()

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={"result": {"items": []}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=KRW",
        json={"result": {"currency": "KRW", "cashBuyingPower": "500000"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=USD",
        json={"result": {"currency": "USD", "cashBuyingPower": "100"}},
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
                "validFrom": "2026-06-30T09:00:00+09:00",
            }
        },
    )

    response = client.get("/api/summary?account_seq=acct-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["net_worth_krw"] == 640000.0
    assert payload["buying_power_total_krw"] == 640000.0
    assert payload["asset_mix"] == {"cash": 100.0}
    assert payload["goal_progress"][0]["current_amount_krw"] == 640000.0
    assert payload["goal_progress"][0]["remaining_krw"] == 360000.0


def test_toss_buying_power_endpoint_returns_krw_and_usd(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=KRW",
        json={"result": {"currency": "KRW", "cashBuyingPower": "5000000"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/buying-power?currency=USD",
        json={"result": {"currency": "USD", "cashBuyingPower": "3500.5"}},
    )

    response = client.get("/api/toss/buying-power?account_seq=acct-1")

    assert response.status_code == 200
    assert response.json() == [
        {"currency": "KRW", "cash_buying_power": 5000000.0},
        {"currency": "USD", "cash_buying_power": 3500.5},
    ]


def test_summary_endpoint_maps_provider_http_errors_to_502_without_secrets(
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
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        status_code=500,
        text="provider body contains toss-secret and token-123",
    )

    response = client.get("/api/summary?account_seq=acct-1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "Toss 요청 실패: HTTP 500 Internal Server Error"
    assert "toss-secret" not in detail
    assert "token-123" not in detail

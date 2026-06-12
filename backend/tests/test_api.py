from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.main import create_app


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
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


def test_summary_endpoint_returns_empty_snapshot(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 0
    assert response.json()["asset_mix"] == {}


def test_can_create_account_asset_and_transaction(tmp_path):
    client = create_test_client(tmp_path)

    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash", "currency": "KRW"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={
            "symbol": None,
            "name": "KRW",
            "type": "cash",
            "currency": "KRW",
            "market": "KR",
        },
    ).json()
    tx = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "초기 입금",
        },
    )

    assert tx.status_code == 201
    summary = client.get("/api/summary").json()
    assert summary["net_worth_krw"] == 1_000_000
    assert client.get("/api/accounts").json()[0]["id"] == account["id"]
    assert client.get("/api/assets").json()[0]["id"] == asset["id"]
    assert client.get("/api/transactions").json()[0]["id"] == tx.json()["id"]


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


def test_summary_converts_usd_stock_holding_to_krw_with_transaction_fx_rate(tmp_path):
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
    response = client.post(
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
            "memo": "첫 해외 ETF 매수",
        },
    )

    assert response.status_code == 201
    summary = client.get("/api/summary").json()
    assert summary["net_worth_krw"] == 700_000
    assert summary["asset_mix"] == {"stock_etf": 100.0}


def test_summary_rejects_non_krw_holding_without_fx_rate(tmp_path):
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
            "memo": "환율 누락 매수",
        },
    )

    response = client.get("/api/summary")

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]


def test_account_create_validation_error_is_korean_for_missing_required_field(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/accounts",
        json={"type": "cash", "currency": "KRW"},
    )

    assert_korean_validation_error(response, "필수 입력값")


def test_asset_create_validation_error_is_korean_for_extra_field(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/assets",
        json={
            "symbol": None,
            "name": "KRW",
            "type": "cash",
            "currency": "KRW",
            "market": "KR",
            "unexpected": True,
        },
    )

    assert_korean_validation_error(response, "허용되지 않는 입력값")


def test_transaction_create_validation_error_is_korean_for_wrong_type(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": "not-an-integer",
            "asset_id": 1,
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "초기 입금",
        },
    )

    assert_korean_validation_error(response, "입력값 형식")


def test_transaction_create_validation_error_is_korean_for_invalid_date(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/transactions",
        json={
            "occurred_on": "not-a-date",
            "type": "deposit",
            "account_id": 1,
            "asset_id": 1,
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "잘못된 날짜",
        },
    )

    assert_korean_validation_error(response, "입력값 형식")

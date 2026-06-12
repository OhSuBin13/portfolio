from datetime import date, timedelta

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app

LOCAL_FRONTEND_ORIGIN = "http://127.0.0.1:5173"


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


def current_month_date() -> str:
    return date.today().isoformat()


def previous_month_date() -> str:
    return (date.today().replace(day=1) - timedelta(days=1)).isoformat()


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


def test_summary_allows_local_frontend_cors_origin(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary", headers={"Origin": LOCAL_FRONTEND_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_FRONTEND_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_api_post_preflight_allows_local_frontend_origin(tmp_path):
    client = create_test_client(tmp_path)

    response = client.options(
        "/api/transactions",
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


def test_goal_progress_reports_one_percent_for_net_worth_goal(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash", "currency": "KRW"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": None, "name": "KRW", "type": "cash", "currency": "KRW", "market": "KR"},
    ).json()
    client.post(
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
    goal = client.post(
        "/api/goals",
        json={
            "name": "순자산 1억",
            "type": "net_worth",
            "target_amount_krw": 100_000_000,
        },
    ).json()

    response = client.get("/api/goals/progress")

    assert response.status_code == 200
    assert response.json() == [
        {
            "goal": {
                "id": goal["id"],
                "name": "순자산 1억",
                "type": "net_worth",
                "target_amount_krw": 100_000_000,
            },
            "current_amount_krw": 1_000_000,
            "percent": 1,
            "remaining_krw": 99_000_000,
        }
    ]


def test_summary_counts_krw_income_and_monthly_income_goal_progress(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash", "currency": "KRW"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": None, "name": "KRW", "type": "cash", "currency": "KRW", "market": "KR"},
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "dividend",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 30_000,
            "currency": "KRW",
            "memo": "배당",
        },
    )
    client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "interest",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 70_000,
            "currency": "KRW",
            "memo": "이자",
        },
    )
    goal = client.post(
        "/api/goals",
        json={
            "name": "월 소득 100만",
            "type": "monthly_income",
            "target_amount_krw": 1_000_000,
        },
    ).json()

    summary = client.get("/api/summary").json()
    progress = client.get("/api/goals/progress").json()

    assert summary["monthly_income_krw"] == 100_000
    assert progress == [
        {
            "goal": {
                "id": goal["id"],
                "name": "월 소득 100만",
                "type": "monthly_income",
                "target_amount_krw": 1_000_000,
            },
            "current_amount_krw": 100_000,
            "percent": 10,
            "remaining_krw": 900_000,
        }
    ]


def test_summary_counts_only_current_month_income_for_monthly_income_progress(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash", "currency": "KRW"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": None, "name": "KRW", "type": "cash", "currency": "KRW", "market": "KR"},
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "dividend",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 40_000,
            "currency": "KRW",
            "memo": "이번 달 배당",
        },
    )
    client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "interest",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 60_000,
            "currency": "KRW",
            "memo": "이번 달 이자",
        },
    )
    client.post(
        "/api/transactions",
        json={
            "occurred_on": previous_month_date(),
            "type": "dividend",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 900_000,
            "currency": "KRW",
            "memo": "지난 달 배당",
        },
    )
    client.post(
        "/api/transactions",
        json={
            "occurred_on": previous_month_date(),
            "type": "interest",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 800_000,
            "currency": "KRW",
            "memo": "지난 달 이자",
        },
    )
    client.post(
        "/api/goals",
        json={
            "name": "월 소득 100만",
            "type": "monthly_income",
            "target_amount_krw": 1_000_000,
        },
    )

    summary = client.get("/api/summary").json()
    progress = client.get("/api/goals/progress").json()[0]

    assert summary["monthly_income_krw"] == 100_000
    assert progress["current_amount_krw"] == 100_000
    assert progress["percent"] == 10


def test_summary_converts_non_krw_monthly_income_with_transaction_fx_rate(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash", "currency": "USD"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": "USD", "name": "USD", "type": "cash", "currency": "USD", "market": "US"},
    ).json()
    response = client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "interest",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 100,
            "currency": "USD",
            "fx_rate_to_krw": 1400,
            "memo": "달러 이자",
        },
    )

    assert response.status_code == 201
    assert client.get("/api/summary").json()["monthly_income_krw"] == 140_000


def test_summary_rejects_non_krw_monthly_income_without_transaction_fx_rate(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash", "currency": "USD"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": "USD", "name": "USD", "type": "cash", "currency": "USD", "market": "US"},
    ).json()
    client.post(
        "/api/transactions",
        json={
            "occurred_on": current_month_date(),
            "type": "interest",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 100,
            "currency": "USD",
            "memo": "환율 누락 이자",
        },
    )
    db = connect(client.app.state.settings.database_path)
    db.execute(
        """
        insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
        values (?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1400, "test", "2026-06-13T00:00:00"),
    )
    db.commit()
    db.close()

    response = client.get("/api/summary")

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]


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


def test_summary_prefers_latest_fx_rate_over_transaction_fx_rate(tmp_path):
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
            "memo": "거래 당시 환율",
        },
    )
    db = connect(client.app.state.settings.database_path)
    db.execute(
        """
        insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
        values (?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1300, "test", "2026-06-13T00:00:00"),
    )
    db.commit()
    db.close()

    summary = client.get("/api/summary").json()

    assert summary["net_worth_krw"] == 650_000


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


def test_transaction_create_rejects_invalid_fx_rate_without_persistence(tmp_path):
    client = create_test_client(tmp_path)

    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash", "currency": "KRW"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": None, "name": "KRW", "type": "cash", "currency": "KRW", "market": "KR"},
    ).json()
    response = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "fx_rate_to_krw": -1,
            "memo": "잘못된 환율",
        },
    )

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]
    assert client.get("/api/transactions").json() == []

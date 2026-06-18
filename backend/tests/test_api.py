from datetime import date, timedelta

import pytest
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


def post_transaction(
    client,
    *,
    occurred_on,
    transaction_type,
    account_id,
    asset_id,
    amount,
    memo,
):
    return client.post(
        "/api/transactions",
        json={
            "occurred_on": occurred_on,
            "type": transaction_type,
            "account_id": account_id,
            "asset_id": asset_id,
            "quantity": None,
            "amount": amount,
            "currency": "KRW",
            "memo": memo,
        },
    )


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_summary_endpoint_returns_empty_snapshot(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary?refresh=false")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 0
    assert response.json()["usd_krw_rate"] is None
    assert response.json()["asset_mix"] == {}


def test_summary_allows_local_frontend_cors_origin(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/summary?refresh=false", headers={"Origin": LOCAL_FRONTEND_ORIGIN})

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


def test_account_mutation_preflight_allows_local_frontend_origin(tmp_path):
    client = create_test_client(tmp_path)

    for method in ("PUT", "DELETE"):
        response = client.options(
            "/api/accounts/1",
            headers={
                "Origin": LOCAL_FRONTEND_ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == LOCAL_FRONTEND_ORIGIN
        assert method in response.headers["access-control-allow-methods"]
        assert "content-type" in response.headers["access-control-allow-headers"].lower()
        assert "access-control-allow-credentials" not in response.headers


def test_can_create_account_asset_and_transaction(tmp_path):
    client = create_test_client(tmp_path)

    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash"},
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
    summary = client.get("/api/summary?refresh=false").json()
    assert summary["net_worth_krw"] == 1_000_000
    assert client.get("/api/accounts").json()[0]["id"] == account["id"]
    assert any(item["id"] == asset["id"] for item in client.get("/api/assets").json())
    assert client.get("/api/transactions").json()[0]["id"] == tx.json()["id"]


def test_transaction_endpoints_document_typed_response_model(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    transaction_response = schema["components"]["schemas"]["TransactionResponse"]
    assert schema["paths"]["/api/transactions"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/TransactionResponse"}
    assert schema["paths"]["/api/transactions"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/TransactionResponse"}
    assert {
        "id",
        "occurred_on",
        "type",
        "account_id",
        "asset_id",
        "quantity",
        "amount",
        "currency",
        "fx_rate_to_krw",
        "memo",
        "created_at",
    }.issubset(transaction_response["properties"])


def test_transactions_keep_history_with_null_account_after_account_delete(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash"},
    ).json()
    cash_asset = next(
        asset
        for asset in client.get("/api/assets").json()
        if asset["type"] == "cash" and asset["currency"] == "KRW"
    )
    created = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": cash_asset["id"],
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "초기 입금",
        },
    ).json()

    deleted = client.delete(f"/api/accounts/{account['id']}")
    transactions = client.get("/api/transactions").json()

    assert deleted.status_code == 204
    assert transactions == [
        {
            **created,
            "account_id": None,
        }
    ]


def test_list_transactions_returns_latest_transactions_first(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash"},
    ).json()
    cash_asset = next(
        asset
        for asset in client.get("/api/assets").json()
        if asset["type"] == "cash" and asset["currency"] == "KRW"
    )

    oldest = post_transaction(
        client,
        occurred_on="2026-06-10",
        transaction_type="deposit",
        account_id=account["id"],
        asset_id=cash_asset["id"],
        amount=10_000,
        memo="가장 오래된 거래",
    ).json()
    same_day_first = post_transaction(
        client,
        occurred_on="2026-06-12",
        transaction_type="deposit",
        account_id=account["id"],
        asset_id=cash_asset["id"],
        amount=20_000,
        memo="같은 날 먼저 저장",
    ).json()
    same_day_latest = post_transaction(
        client,
        occurred_on="2026-06-12",
        transaction_type="interest",
        account_id=account["id"],
        asset_id=cash_asset["id"],
        amount=1_000,
        memo="같은 날 나중에 저장",
    ).json()

    response = client.get("/api/transactions")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        same_day_latest["id"],
        same_day_first["id"],
        oldest["id"],
    ]


def test_list_transactions_filters_by_account_asset_type_and_date_range(tmp_path):
    client = create_test_client(tmp_path)
    cash_account = client.post(
        "/api/accounts",
        json={"name": "생활비", "type": "cash"},
    ).json()
    savings_account = client.post(
        "/api/accounts",
        json={"name": "예금", "type": "savings"},
    ).json()
    assets = client.get("/api/assets").json()
    cash_asset = next(
        asset for asset in assets if asset["type"] == "cash" and asset["currency"] == "KRW"
    )
    savings_asset = next(
        asset for asset in assets if asset["type"] == "savings" and asset["currency"] == "KRW"
    )

    post_transaction(
        client,
        occurred_on="2026-06-01",
        transaction_type="deposit",
        account_id=cash_account["id"],
        asset_id=cash_asset["id"],
        amount=10_000,
        memo="계좌 불일치",
    )
    matching = post_transaction(
        client,
        occurred_on="2026-06-15",
        transaction_type="interest",
        account_id=savings_account["id"],
        asset_id=savings_asset["id"],
        amount=20_000,
        memo="필터 대상",
    ).json()
    post_transaction(
        client,
        occurred_on="2026-06-20",
        transaction_type="interest",
        account_id=savings_account["id"],
        asset_id=cash_asset["id"],
        amount=30_000,
        memo="자산 불일치",
    )
    post_transaction(
        client,
        occurred_on="2026-06-10",
        transaction_type="deposit",
        account_id=savings_account["id"],
        asset_id=savings_asset["id"],
        amount=40_000,
        memo="유형 불일치",
    )
    post_transaction(
        client,
        occurred_on="2026-07-01",
        transaction_type="interest",
        account_id=savings_account["id"],
        asset_id=savings_asset["id"],
        amount=50_000,
        memo="기간 불일치",
    )

    response = client.get(
        "/api/transactions",
        params={
            "account_id": savings_account["id"],
            "asset_id": savings_asset["id"],
            "type": "interest",
            "from": "2026-06-01",
            "to": "2026-06-30",
        },
    )

    assert response.status_code == 200
    assert response.json() == [matching]


def test_can_get_update_and_delete_account(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "원화 현금", "type": "cash"},
    ).json()

    detail = client.get(f"/api/accounts/{account['id']}")

    assert detail.status_code == 200
    assert detail.json()["name"] == "원화 현금"
    assert "currency" not in detail.json()

    updated = client.put(
        f"/api/accounts/{account['id']}",
        json={"name": "해외 증권", "type": "brokerage"},
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "해외 증권"
    assert updated.json()["type"] == "brokerage"
    assert "currency" not in updated.json()

    deleted = client.delete(f"/api/accounts/{account['id']}")

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/accounts/{account['id']}").status_code == 404
    assert client.delete(f"/api/accounts/{account['id']}").status_code == 404


def test_account_payload_validation_normalizes_shared_post_put_input():
    from portfolio_app.api import accounts

    payload = accounts.AccountWritePayload(name="  해외 증권  ", type=" brokerage ")

    assert hasattr(accounts, "validate_account_payload")
    validated = accounts.validate_account_payload(payload)

    assert validated.name == "해외 증권"
    assert validated.type == "brokerage"


def test_account_payload_validation_rejects_invalid_type():
    from fastapi import HTTPException

    from portfolio_app.api import accounts

    payload = accounts.AccountWritePayload(name="원화 현금", type="checking")

    assert hasattr(accounts, "validate_account_payload")
    with pytest.raises(HTTPException) as exc_info:
        accounts.validate_account_payload(payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "지원하지 않는 계좌 유형입니다."


def test_asset_payload_validation_normalizes_stock_etf_input():
    from portfolio_app.api import assets

    payload = assets.AssetCreate(
        symbol=" voo ",
        name="  Vanguard S&P 500 ETF  ",
        type="stock_etf",
        currency=" usd ",
        market=" us ",
    )

    assert hasattr(assets, "validate_asset_payload")
    validated = assets.validate_asset_payload(payload)

    assert validated.symbol == "VOO"
    assert validated.name == "Vanguard S&P 500 ETF"
    assert validated.type == "stock_etf"
    assert validated.currency == "USD"
    assert validated.market == "US"


def test_asset_payload_validation_normalizes_builtin_asset_input():
    from portfolio_app.api import assets

    payload = assets.AssetCreate(
        symbol=" krw ",
        name="  원화 현금  ",
        type="cash",
        currency=" krw ",
        market=" kr ",
    )

    assert hasattr(assets, "validate_asset_payload")
    validated = assets.validate_asset_payload(payload)

    assert validated.symbol is None
    assert validated.name == "원화 현금"
    assert validated.type == "cash"
    assert validated.currency == "KRW"
    assert validated.market is None


def test_asset_payload_validation_rejects_missing_stock_etf_market():
    from fastapi import HTTPException

    from portfolio_app.api import assets

    payload = assets.AssetCreate(
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        type="stock_etf",
        currency="USD",
        market=None,
    )

    assert hasattr(assets, "validate_asset_payload")
    with pytest.raises(HTTPException) as exc_info:
        assets.validate_asset_payload(payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "시장을 입력해 주세요."


def test_account_create_rejects_currency_field(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash", "currency": "usd"},
    )

    assert_korean_validation_error(response, "허용되지 않는 입력값")


def test_assets_include_builtin_cash_without_manual_asset_creation(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/assets")

    assert response.status_code == 200
    cash_assets = [
        asset for asset in response.json() if asset["type"] == "cash" and asset["currency"] == "KRW"
    ]
    assert cash_assets
    assert cash_assets[0]["name"] == "원화 현금"
    assert cash_assets[0]["symbol"] is None
    assert cash_assets[0]["market"] is None


def test_assets_include_builtin_savings_and_debt_without_manual_asset_creation(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/assets")

    assert response.status_code == 200
    builtin_assets = {
        (asset["type"], asset["currency"]): asset
        for asset in response.json()
        if asset["type"] in {"savings", "debt"}
    }
    assert builtin_assets[("savings", "KRW")]["name"] == "예금"
    assert builtin_assets[("savings", "KRW")]["symbol"] is None
    assert builtin_assets[("savings", "KRW")]["market"] is None
    assert builtin_assets[("debt", "KRW")]["name"] == "부채"
    assert builtin_assets[("debt", "KRW")]["symbol"] is None
    assert builtin_assets[("debt", "KRW")]["market"] is None


def test_can_record_cash_transaction_with_builtin_cash_asset(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "생활비", "type": "cash"},
    ).json()
    cash_asset = next(
        asset
        for asset in client.get("/api/assets").json()
        if asset["type"] == "cash" and asset["currency"] == "KRW"
    )

    tx = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": cash_asset["id"],
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "초기 현금",
        },
    )

    assert tx.status_code == 201
    assert client.get("/api/summary?refresh=false").json()["net_worth_krw"] == 1_000_000


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
        json={"name": "원화 현금", "type": "cash"},
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
        json={"name": "원화 현금", "type": "cash"},
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

    summary = client.get("/api/summary?refresh=false").json()
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
        json={"name": "원화 현금", "type": "cash"},
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

    summary = client.get("/api/summary?refresh=false").json()
    progress = client.get("/api/goals/progress").json()[0]

    assert summary["monthly_income_krw"] == 100_000
    assert progress["current_amount_krw"] == 100_000
    assert progress["percent"] == 10


def test_summary_converts_non_krw_monthly_income_with_transaction_fx_rate(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash"},
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
    assert client.get("/api/summary?refresh=false").json()["monthly_income_krw"] == 140_000


def test_summary_rejects_non_krw_monthly_income_without_transaction_fx_rate(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": "USD", "name": "USD", "type": "cash", "currency": "USD", "market": "US"},
    ).json()
    db = connect(client.app.state.settings.database_path)
    db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, amount, currency, memo
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_month_date(),
            "interest",
            account["id"],
            asset["id"],
            100,
            "USD",
            "환율 누락 이자",
        ),
    )
    db.execute(
        """
        insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
        values (?, ?, ?, ?, ?)
        """,
        ("USD", "KRW", 1400, "test", "2026-06-13T00:00:00"),
    )
    db.commit()
    db.close()

    response = client.get("/api/summary?refresh=false")

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]


def test_summary_converts_usd_stock_holding_to_krw_with_transaction_fx_rate(tmp_path):
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
    summary = client.get("/api/summary?refresh=false").json()
    assert summary["net_worth_krw"] == 700_000
    assert summary["asset_mix"] == {"stock_etf": 100.0}


def test_summary_prefers_latest_fx_rate_over_transaction_fx_rate(tmp_path):
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

    summary = client.get("/api/summary?refresh=false").json()

    assert summary["net_worth_krw"] == 650_000


def test_summary_rejects_non_krw_holding_without_fx_rate(tmp_path):
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
    db = connect(client.app.state.settings.database_path)
    db.execute(
        """
        insert into holdings(account_id, asset_id, quantity, average_cost)
        values (?, ?, ?, ?)
        """,
        (account["id"], asset["id"], 1, 500),
    )
    db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, quantity, amount, currency, memo
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-12",
            "buy",
            account["id"],
            asset["id"],
            1,
            500,
            "USD",
            "환율 누락 매수",
        ),
    )
    db.commit()
    db.close()

    response = client.get("/api/summary?refresh=false")

    assert response.status_code == 400
    assert "환율" in response.json()["detail"]


def test_account_create_validation_error_is_korean_for_missing_required_field(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/accounts",
        json={"type": "cash"},
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
        json={"name": "원화 현금", "type": "cash"},
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


def test_transaction_create_rejects_usd_without_fx_rate_without_persistence(tmp_path):
    client = create_test_client(tmp_path)

    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash"},
    ).json()
    asset = client.post(
        "/api/assets",
        json={"symbol": "USD", "name": "USD", "type": "cash", "currency": "USD", "market": "US"},
    ).json()
    response = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 1_000,
            "currency": "USD",
            "memo": "환율 누락 달러 입금",
        },
    )

    assert response.status_code == 400
    assert "외화 거래에는 환율" in response.json()["detail"]
    assert client.get("/api/transactions").json() == []

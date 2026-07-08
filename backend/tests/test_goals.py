from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from portfolio_app.config import Settings
from portfolio_app.main import create_app
from portfolio_app.models import Goal, GoalProgress, PortfolioSummary
from portfolio_app.services.toss_portfolio import TossSummaryResult


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_goal_endpoints_document_typed_response_models(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    goal_create_schema = schema["components"]["schemas"]["GoalCreate"]
    goal_schema = schema["components"]["schemas"]["Goal"]
    goal_progress_schema = schema["components"]["schemas"]["GoalProgress"]
    assert schema["paths"]["/api/goals"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Goal"}
    assert schema["paths"]["/api/goals"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/Goal"}
    assert "/api/goals/progress" not in schema["paths"]
    assert {"id", "name", "type", "target_amount_krw"} <= set(goal_schema["properties"])
    assert goal_create_schema["properties"]["type"]["enum"] == goal_schema["properties"][
        "type"
    ]["enum"]
    assert goal_create_schema["properties"]["target_amount_krw"]["exclusiveMinimum"] == 0.0
    assert {"goal", "current_amount_krw", "percent", "remaining_krw"} <= set(
        goal_progress_schema["properties"]
    )


def test_goal_input_validation_normalizes_input():
    from portfolio_app.services import goals as goal_service

    assert hasattr(goal_service, "validate_goal_input")
    validated = goal_service.validate_goal_input(
        name="  순자산 1억  ",
        type=" net_worth ",
        target_amount_krw=100_000_000,
    )

    assert validated.name == "순자산 1억"
    assert validated.type == "net_worth"
    assert validated.target_amount_krw == 100_000_000


def test_goal_input_validation_rejects_empty_name():
    from portfolio_app.services import goals as goal_service

    with pytest.raises(ValueError, match="목표 이름을 입력해 주세요."):
        goal_service.validate_goal_input(
            name="  ",
            type="net_worth",
            target_amount_krw=100_000_000,
        )


def test_create_goal_validates_and_normalizes_input(tmp_path):
    from portfolio_app.db import connect
    from portfolio_app.migrations import migrate
    from portfolio_app.services import goals as goal_service

    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    try:
        goal = goal_service.create_goal(
            db,
            name="  순자산 1억  ",
            type=" net_worth ",
            target_amount_krw=100_000_000,
        )
    finally:
        db.close()

    assert goal.name == "순자산 1억"
    assert goal.type == "net_worth"
    assert goal.target_amount_krw == 100_000_000


def test_goal_payload_validation_rejects_invalid_type():
    from portfolio_app.api import goals

    with pytest.raises(ValidationError):
        goals.GoalCreate(
            name="부자 되기",
            type="wealth",
            target_amount_krw=100_000_000,
        )


def test_summary_and_goal_models_reject_extra_fields():
    summary_payload = {
        "net_worth_krw": 1_000_000,
        "gross_assets_krw": 1_000_000,
        "debt_krw": 0,
        "monthly_income_krw": 100_000,
    }
    goal = Goal(
        id=1,
        name="월 소득 100만",
        type="monthly_income",
        target_amount_krw=1_000_000,
    )
    progress_payload = {
        "goal": goal,
        "current_amount_krw": 100_000,
        "percent": 10,
        "remaining_krw": 900_000,
    }

    with pytest.raises(ValidationError):
        PortfolioSummary(**summary_payload, unexpected=True)
    with pytest.raises(ValidationError):
        Goal(
            id=2,
            name="순자산 1억",
            type="net_worth",
            target_amount_krw=100_000_000,
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        GoalProgress(**progress_payload, unexpected=True)


@pytest.mark.asyncio
async def test_summary_endpoint_uses_goal_progress_service_for_supplied_summary(monkeypatch):
    from portfolio_app.api import summary as summary_api

    db = object()
    settings = SimpleNamespace(toss_api_key="toss-client", toss_secret_key="toss-secret")
    fake_auth_client = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                toss_auth_client=fake_auth_client,
            )
        )
    )
    portfolio_summary = PortfolioSummary(
        net_worth_krw=1_000_000,
        gross_assets_krw=1_000_000,
        debt_krw=0,
        monthly_income_krw=100_000,
    )
    progress = [
        GoalProgress(
            goal=Goal(
                id=1,
                name="월 소득 100만",
                type="monthly_income",
                target_amount_krw=1_000_000,
            ),
            current_amount_krw=100_000,
            percent=10,
            remaining_krw=900_000,
        )
    ]
    calls = []

    class FakeTossBrokerageProvider:
        def __init__(self, client_id, client_secret, *, auth_client=None):
            assert client_id == "toss-client"
            assert client_secret == "toss-secret"
            assert auth_client is fake_auth_client

    def fake_default_fx_rate_provider(received_settings, *, auth_client=None):
        assert received_settings is settings
        assert auth_client is fake_auth_client
        return object()

    async def fake_fetch_toss_summary(account_seq, provider, fx_provider=None):
        assert account_seq == "acct-1"
        assert isinstance(provider, FakeTossBrokerageProvider)
        assert fx_provider is not None
        return TossSummaryResult(
            summary=portfolio_summary,
            asset_mix={},
            asset_allocations=[],
        )

    def fake_list_goal_progress_for_summary(received_db, received_summary):
        calls.append((received_db, received_summary))
        return progress

    monkeypatch.setattr(summary_api, "TossBrokerageProvider", FakeTossBrokerageProvider)
    monkeypatch.setattr(summary_api, "default_fx_rate_provider", fake_default_fx_rate_provider)
    monkeypatch.setattr(summary_api, "fetch_toss_summary", fake_fetch_toss_summary)
    monkeypatch.setattr(
        summary_api.goal_service,
        "list_goal_progress_for_summary",
        fake_list_goal_progress_for_summary,
    )

    response = await summary_api.get_summary(request, db, account_seq="acct-1")

    assert response.goal_progress == progress
    assert calls == [(db, portfolio_summary)]


def test_build_goal_progress_uses_summary_amount_for_goal_type():
    from portfolio_app.services import goals as goal_service

    summary = PortfolioSummary(
        net_worth_krw=1_000_000,
        gross_assets_krw=1_000_000,
        debt_krw=0,
        monthly_income_krw=100_000,
    )
    goals = [
        Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000),
        Goal(id=2, name="월 소득 100만", type="monthly_income", target_amount_krw=1_000_000),
    ]

    progress = goal_service.build_goal_progress(summary, goals)

    assert [row.current_amount_krw for row in progress] == [1_000_000, 100_000]
    assert [row.percent for row in progress] == [1, 10]


def test_build_goal_progress_rejects_unknown_goal_type():
    from portfolio_app.services import goals as goal_service

    summary = PortfolioSummary(
        net_worth_krw=1_000_000,
        gross_assets_krw=1_000_000,
        debt_krw=0,
        monthly_income_krw=100_000,
    )
    goal = Goal.model_construct(
        id=3,
        name="지원 전 목표",
        type="cash_flow",
        target_amount_krw=1_000_000,
    )

    with pytest.raises(ValueError, match="지원하지 않는 목표 유형입니다"):
        goal_service.build_goal_progress(summary, [goal])

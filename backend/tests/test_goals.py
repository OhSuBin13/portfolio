from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.main import create_app
from portfolio_app.models import Goal, PortfolioSummary


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
    goal_schema = schema["components"]["schemas"]["Goal"]
    goal_progress_schema = schema["components"]["schemas"]["GoalProgress"]
    assert schema["paths"]["/api/goals"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/Goal"}
    assert schema["paths"]["/api/goals"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/Goal"}
    assert schema["paths"]["/api/goals/progress"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"] == {"$ref": "#/components/schemas/GoalProgress"}
    assert {"id", "name", "type", "target_amount_krw"} <= set(goal_schema["properties"])
    assert {"goal", "current_amount_krw", "percent", "remaining_krw"} <= set(
        goal_progress_schema["properties"]
    )


def test_goal_payload_validation_normalizes_input():
    from portfolio_app.api import goals

    payload = goals.GoalCreate(
        name="  순자산 1억  ",
        type=" net_worth ",
        target_amount_krw=100_000_000,
    )

    assert hasattr(goals, "validate_goal_payload")
    validated = goals.validate_goal_payload(payload)

    assert validated.name == "순자산 1억"
    assert validated.type == "net_worth"
    assert validated.target_amount_krw == 100_000_000


def test_goal_payload_validation_rejects_invalid_type():
    from fastapi import HTTPException

    from portfolio_app.api import goals

    payload = goals.GoalCreate(
        name="부자 되기",
        type="wealth",
        target_amount_krw=100_000_000,
    )

    assert hasattr(goals, "validate_goal_payload")
    try:
        goals.validate_goal_payload(payload)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "지원하지 않는 목표 유형입니다."
    else:
        raise AssertionError("validate_goal_payload should reject unsupported goal types")


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

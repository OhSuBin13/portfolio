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

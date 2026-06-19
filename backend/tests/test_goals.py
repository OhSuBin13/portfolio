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

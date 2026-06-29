from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.main import create_app


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        market_sync_enabled=False,
        backup_enabled=False,
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_growth_api_routes_are_not_registered(tmp_path):
    client = create_test_client(tmp_path)

    schema = client.get("/openapi.json").json()

    assert {
        "/api/growth",
        "/api/growth/history",
        "/api/growth/snapshots/today",
        "/api/growth/snapshots",
    }.isdisjoint(schema["paths"])
    assert client.post("/api/growth/snapshots/today").status_code == 404
    assert client.get("/api/growth/snapshots").status_code == 404
    assert client.get("/api/growth/history").status_code == 404

from portfolio_app.config import Settings
from portfolio_app.main import create_app


def test_app_routes_match_toss_portfolio_surface(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        toss_api_key="",
        toss_secret_key="",
        backup_enabled=False,
    )
    app = create_app(settings=settings)

    assert {route.path for route in app.routes} == {
        "/api/backups",
        "/api/goals",
        "/api/growth/annual-history",
        "/api/growth/month-history",
        "/api/growth/month-history/{year}/{month}",
        "/api/growth/sp500-proxy-prices",
        "/api/growth/sp500-proxy-prices/{year}",
        "/api/summary",
        "/api/toss/accounts",
        "/api/toss/buying-power",
        "/api/toss/candles",
        "/api/toss/chart-marker-memos",
        "/api/toss/holdings",
        "/api/toss/order-imports",
        "/api/toss/orders",
        "/docs",
        "/docs/oauth2-redirect",
        "/health",
        "/openapi.json",
        "/redoc",
    }

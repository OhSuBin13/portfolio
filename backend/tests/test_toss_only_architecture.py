import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
BACKEND_SRC = ROOT / "src/portfolio_app"
FRONTEND_SRC = ROOT.parents[0] / "frontend/src"
REMOVED_BACKEND_FILES = (
    "api/accounts.py",
    "api/assets.py",
    "api/transactions.py",
    "api/market_data.py",
    "services/transactions.py",
    "services/stock_metadata.py",
    "services/market_sync_scheduler.py",
)


def test_fresh_schema_no_longer_defines_local_ledger_tables():
    schema_sql = (BACKEND_SRC / "schema.sql").read_text(encoding="utf-8")

    removed_tables = (
        "accounts",
        "assets",
        "holdings",
        "transactions",
        "price_snapshots",
        "portfolio_snapshots",
    )
    for table_name in removed_tables:
        assert f"create table if not exists {table_name}" not in schema_sql


def test_main_registers_toss_portfolio_instead_of_local_ledger_routers():
    source = (BACKEND_SRC / "main.py").read_text(encoding="utf-8")

    assert "toss_portfolio" in source
    assert "app.include_router(toss_portfolio.router)" in source
    assert "growth_history" in source
    assert "app.include_router(growth_history.router)" in source
    assert "app.include_router(accounts.router)" not in source
    assert "app.include_router(assets.router)" not in source
    assert "app.include_router(transactions.router)" not in source
    assert "app.include_router(growth.router)" not in source
    assert "app.include_router(market_data.router)" not in source


def test_removed_local_ledger_backend_modules_are_gone():
    for relative_path in REMOVED_BACKEND_FILES:
        assert not (BACKEND_SRC / relative_path).exists()


def test_registered_api_surface_includes_toss_orders_not_transactions():
    source = (BACKEND_SRC / "api/toss_portfolio.py").read_text(encoding="utf-8")
    prefix_match = re.search(r'APIRouter\(prefix="([^"]+)"', source)
    assert prefix_match is not None
    prefix = prefix_match.group(1)
    registered_paths = {
        f"{prefix}{path}"
        for path in re.findall(r'@router\.(?:get|post|put|delete)\("([^"]*)"', source)
    }

    assert "/api/toss/orders" in registered_paths
    assert "/api/toss/buying-power" in registered_paths
    assert "/api/transactions" not in registered_paths


def test_frontend_no_longer_calls_local_ledger_endpoints():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FRONTEND_SRC.glob("**/*")
        if path.suffix in {".ts", ".tsx"}
    )

    for endpoint in (
        "/api/accounts",
        "/api/assets",
        "/api/transactions",
        "/api/market-data/status",
    ):
        assert endpoint not in combined
    assert "/api/toss/accounts" in combined
    assert "/api/toss/holdings" in combined

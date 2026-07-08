from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[1] / "src/portfolio_app"


def test_fetch_accounts_delegates_to_account_parser():
    source = (BACKEND_SRC / "services/toss_portfolio.py").read_text(encoding="utf-8")

    assert "def _parse_account" in source
    assert "return [_parse_account(item) for item in result]" in source


def test_fetch_orders_delegates_to_order_page_params_helper():
    source = (BACKEND_SRC / "services/toss_portfolio.py").read_text(encoding="utf-8")

    assert "def _order_page_params" in source
    assert "params=_order_page_params(" in source

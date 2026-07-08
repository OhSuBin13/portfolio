from pathlib import Path


def test_market_data_reuses_shared_toss_payload_helpers():
    source_path = Path(__file__).resolve().parents[1] / "src/portfolio_app/services/market_data.py"
    source = source_path.read_text()

    assert "from portfolio_app.services.toss_payloads import (" in source
    assert "def _positive_number(" not in source
    assert "def _required_text(" not in source
    assert "def _non_negative_number(" not in source

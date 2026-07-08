from pathlib import Path


def test_market_data_reuses_shared_toss_payload_helpers():
    services_dir = Path(__file__).resolve().parents[1] / "src/portfolio_app/services"
    market_data_source = (services_dir / "market_data.py").read_text()
    fx_rates_source = (services_dir / "fx_rates.py").read_text()
    market_candles_source = (services_dir / "market_candles.py").read_text()

    assert "from portfolio_app.services.toss_payloads import" in fx_rates_source
    assert "from portfolio_app.services.toss_payloads import" in market_candles_source
    for source in [market_data_source, fx_rates_source, market_candles_source]:
        assert "def _positive_number(" not in source
        assert "def _required_text(" not in source
        assert "def _non_negative_number(" not in source

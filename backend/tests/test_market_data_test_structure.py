from pathlib import Path


def test_market_data_api_tests_do_not_import_provider_implementations():
    api_test_source = (Path(__file__).parent / "test_market_data.py").read_text()
    service_test_path = Path(__file__).parent / "test_market_data_service.py"

    assert service_test_path.exists()
    for name in (
        "AlphaVantageProvider",
        "FallbackFxRateProvider",
        "FrankfurterProvider",
        "NaverFinanceProvider",
        "MarketQuote",
        "keep_last_good_quote",
    ):
        assert name not in api_test_source

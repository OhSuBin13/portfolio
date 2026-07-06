import pytest

from portfolio_app.config import Settings
from portfolio_app.services.canslim import (
    FmpCanslimProvider,
    FmpProviderError,
    normalize_symbol,
)


def test_settings_include_fmp_api_key(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_FMP_API_KEY", raising=False)

    assert Settings(_env_file=None).fmp_api_key == ""


def test_settings_reads_fmp_api_key_from_env(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_FMP_API_KEY", "env-fmp-key")

    assert Settings(_env_file=None).fmp_api_key == "env-fmp-key"


@pytest.mark.asyncio
async def test_fmp_provider_requires_api_key():
    provider = FmpCanslimProvider("")

    with pytest.raises(ValueError, match="FMP API 키를 설정해 주세요."):
        await provider.fetch_bundle("NVDA", market_range="6m")


def test_normalize_symbol_trims_and_uppercases():
    assert normalize_symbol(" nvda ") == "NVDA"


@pytest.mark.parametrize("symbol", ["", "   "])
def test_normalize_symbol_rejects_blank(symbol):
    with pytest.raises(ValueError, match="종목 심볼을 입력해 주세요."):
        normalize_symbol(symbol)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peers_payload",
    [
        [{"symbol": "AMD"}, {"symbol": "AVGO"}],
        ["AMD", "AVGO"],
    ],
)
async def test_fmp_provider_fetches_and_normalizes_bundle(httpx_mock, peers_payload):
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "exchangeShortName": "NASDAQ",
                "sector": "Technology",
                "industry": "Semiconductors",
                "description": "NVIDIA designs accelerated computing products.",
                "currency": "USD",
                "isEtf": False,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=quarter&limit=8&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-04-30", "period": "Q1", "epsdiluted": 1.20},
            {"date": "2025-04-30", "period": "Q1", "epsdiluted": 0.60},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=annual&limit=5&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-01-31", "calendarYear": "2026", "epsdiluted": 4.00},
            {"date": "2025-01-31", "calendarYear": "2025", "epsdiluted": 2.50},
            {"date": "2024-01-31", "calendarYear": "2024", "epsdiluted": 1.50},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=NVDA&from=2025-07-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "date": "2026-07-02",
                "open": 150,
                "high": 156,
                "low": 149,
                "close": 155,
                "volume": 150_000_000,
                "vwap": 153.5,
            },
            {
                "symbol": "NVDA",
                "date": "2026-07-01",
                "open": 148,
                "high": 151,
                "low": 147,
                "close": 150,
                "volume": 100_000_000,
                "vwap": 149.5,
            },
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=SPY&from=2026-01-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "SPY",
                "date": "2026-07-02",
                "open": 620,
                "high": 625,
                "low": 618,
                "close": 624,
                "volume": 60_000_000,
                "vwap": 622.5,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/shares-float?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "floatShares": 22_000_000_000,
                "outstandingShares": 24_000_000_000,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/stock-peers?symbol=NVDA&apikey=fmp-key",
        json=peers_payload,
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "symbol-positions-summary?symbol=NVDA&year=2026&quarter=1&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "year": 2026,
                "quarter": 1,
                "investorsHolding": 4100,
                "investorsHoldingChange": 120,
                "numberOfShares": 14_000_000_000,
                "numberOfSharesChange": 0.08,
                "ownershipPercent": 0.57,
                "marketValueChange": 0.11,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/api/v4/institutional-ownership/"
            "institutional-holders/symbol-ownership"
            "?page=0&date=2026-03-31&symbol=NVDA&apikey=fmp-key"
        ),
        json=[
            {
                "holder": "High Quality Capital",
                "cik": "0000000001",
                "shares": 10_000_000,
                "marketValue": 1_550_000_000,
                "change": 0.2,
                "weight": 0.04,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "holder-performance-summary?cik=0000000001&page=0&apikey=fmp-key"
        ),
        json=[
            {
                "cik": "0000000001",
                "holder": "High Quality Capital",
                "performance1year": 0.32,
                "performance3year": 0.85,
                "performance5year": 1.6,
                "performanceRelativeToSP500": 0.21,
            }
        ],
    )

    provider = FmpCanslimProvider(
        "fmp-key",
        today=lambda: "2026-07-06",
    )

    bundle = await provider.fetch_bundle(" nvda ", market_range="6m")

    assert bundle.profile.symbol == "NVDA"
    assert bundle.profile.company_name == "NVIDIA Corporation"
    assert bundle.profile.exchange == "NASDAQ"
    assert bundle.profile.currency == "USD"
    assert bundle.quarterly_income[0].eps_diluted == 1.20
    assert bundle.annual_income[0].calendar_year == 2026
    assert bundle.prices[0].date == "2026-07-02"
    assert bundle.spy_prices[0].traded_value_usd == 37_350_000_000.0
    assert bundle.float_data.float_shares == 22_000_000_000
    assert bundle.peers == ["AMD", "AVGO"]
    assert bundle.positions_summary is not None
    assert bundle.positions_summary.year == 2026
    assert bundle.positions_summary.quarter == 1
    assert bundle.positions_summary.holders_count_change == 120
    assert bundle.top_holders[0].performance_1y_percent == 32.0


@pytest.mark.asyncio
async def test_fmp_provider_tolerates_positions_summary_failure(httpx_mock):
    _add_required_fmp_bundle_responses(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "symbol-positions-summary?symbol=NVDA&year=2026&quarter=1&apikey=fmp-key"
        ),
        status_code=403,
        json={"Error Message": "institutional data is plan gated"},
    )
    provider = FmpCanslimProvider(
        "fmp-key",
        today=lambda: "2026-07-06",
    )

    bundle = await provider.fetch_bundle("NVDA", market_range="6m")

    assert bundle.profile.symbol == "NVDA"
    assert bundle.quarterly_income[0].eps_diluted == 1.20
    assert bundle.prices[0].date == "2026-07-02"
    assert bundle.positions_summary is None
    assert bundle.top_holders == []


@pytest.mark.asyncio
async def test_fmp_provider_tolerates_holder_ownership_failure(httpx_mock):
    _add_required_fmp_bundle_responses(httpx_mock)
    _add_positions_summary_response(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/api/v4/institutional-ownership/"
            "institutional-holders/symbol-ownership"
            "?page=0&date=2026-03-31&symbol=NVDA&apikey=fmp-key"
        ),
        status_code=403,
        json={"Error Message": "institutional holders are plan gated"},
    )
    provider = FmpCanslimProvider(
        "fmp-key",
        today=lambda: "2026-07-06",
    )

    bundle = await provider.fetch_bundle("NVDA", market_range="6m")

    assert bundle.positions_summary is not None
    assert bundle.positions_summary.holders_count_change == 120
    assert bundle.top_holders == []


@pytest.mark.asyncio
async def test_fmp_provider_tolerates_holder_performance_failure(httpx_mock):
    _add_required_fmp_bundle_responses(httpx_mock)
    _add_positions_summary_response(httpx_mock)
    _add_holder_ownership_response(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "holder-performance-summary?cik=0000000001&page=0&apikey=fmp-key"
        ),
        status_code=403,
        json={"Error Message": "holder performance is plan gated"},
    )
    provider = FmpCanslimProvider(
        "fmp-key",
        today=lambda: "2026-07-06",
    )

    bundle = await provider.fetch_bundle("NVDA", market_range="6m")

    assert bundle.positions_summary is not None
    assert len(bundle.top_holders) == 1
    top_holder = bundle.top_holders[0]
    assert top_holder.holder == "High Quality Capital"
    assert top_holder.cik == "0000000001"
    assert top_holder.shares == 10_000_000
    assert top_holder.performance_1y_percent is None
    assert top_holder.performance_3y_percent is None
    assert top_holder.performance_5y_percent is None
    assert top_holder.performance_relative_to_sp500_percent is None


@pytest.mark.asyncio
async def test_fmp_provider_raises_safe_error_for_http_failure(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        status_code=403,
        json={"Error Message": "secret provider detail"},
    )
    provider = FmpCanslimProvider("fmp-key")

    with pytest.raises(FmpProviderError) as exc_info:
        await provider.fetch_bundle("NVDA", market_range="6m")

    assert str(exc_info.value) == "FMP 요청 실패: HTTP 403 Forbidden"
    assert "secret provider detail" not in str(exc_info.value)


def _add_required_fmp_bundle_responses(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "exchangeShortName": "NASDAQ",
                "sector": "Technology",
                "industry": "Semiconductors",
                "description": "NVIDIA designs accelerated computing products.",
                "currency": "USD",
                "isEtf": False,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=quarter&limit=8&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-04-30", "period": "Q1", "epsdiluted": 1.20},
            {"date": "2025-04-30", "period": "Q1", "epsdiluted": 0.60},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=annual&limit=5&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-01-31", "calendarYear": "2026", "epsdiluted": 4.00},
            {"date": "2025-01-31", "calendarYear": "2025", "epsdiluted": 2.50},
            {"date": "2024-01-31", "calendarYear": "2024", "epsdiluted": 1.50},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=NVDA&from=2025-07-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "date": "2026-07-02",
                "open": 150,
                "high": 156,
                "low": 149,
                "close": 155,
                "volume": 150_000_000,
                "vwap": 153.5,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=SPY&from=2026-01-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "SPY",
                "date": "2026-07-02",
                "open": 620,
                "high": 625,
                "low": 618,
                "close": 624,
                "volume": 60_000_000,
                "vwap": 622.5,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/shares-float?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "floatShares": 22_000_000_000,
                "outstandingShares": 24_000_000_000,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/stock-peers?symbol=NVDA&apikey=fmp-key",
        json=["AMD", "AVGO"],
    )


def _add_positions_summary_response(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "symbol-positions-summary?symbol=NVDA&year=2026&quarter=1&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "year": 2026,
                "quarter": 1,
                "investorsHolding": 4100,
                "investorsHoldingChange": 120,
                "numberOfShares": 14_000_000_000,
                "numberOfSharesChange": 0.08,
                "ownershipPercent": 0.57,
                "marketValueChange": 0.11,
            }
        ],
    )


def _add_holder_ownership_response(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/api/v4/institutional-ownership/"
            "institutional-holders/symbol-ownership"
            "?page=0&date=2026-03-31&symbol=NVDA&apikey=fmp-key"
        ),
        json=[
            {
                "holder": "High Quality Capital",
                "cik": "0000000001",
                "shares": 10_000_000,
                "marketValue": 1_550_000_000,
                "change": 0.2,
                "weight": 0.04,
            }
        ],
    )

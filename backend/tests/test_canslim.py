import pytest

from portfolio_app.config import Settings
from portfolio_app.services import canslim as canslim_service
from portfolio_app.services.canslim import (
    FmpCanslimBundle,
    FmpCanslimProvider,
    FmpCompanyProfile,
    FmpFloatData,
    FmpIncomeRow,
    FmpPositionsSummary,
    FmpPriceRow,
    FmpProviderError,
    FmpTopHolder,
    normalize_symbol,
)

_DEFAULT_POSITIONS_SUMMARY = object()
_COMMON_LETTER_KEYS = {"status", "headline", "details", "metrics", "source", "as_of"}


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


def test_build_canslim_analysis_classifies_strong_stock():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(),
        market_range="6m",
        cached=False,
    )

    assert analysis["symbol"] == "NVDA"
    assert analysis["company_name"] == "NVIDIA Corporation"
    assert analysis["exchange"] == "NASDAQ"
    assert analysis["sector"] == "Technology"
    assert analysis["industry"] == "Semiconductors"
    assert analysis["description"] == "NVIDIA designs accelerated computing products."
    assert analysis["currency"] == "USD"
    assert analysis["provider"] == "fmp"
    assert analysis["cached"] is False
    assert analysis["generated_at"]

    letters = analysis["letters"]
    assert letters["c"]["status"] == "pass"
    assert letters["c"]["metrics"]["quarterly_eps_growth_percent"] == 150.0
    assert letters["a"]["status"] == "pass"
    assert letters["a"]["metrics"]["annual_eps_values"] == [4.0, 2.5, 1.25]
    assert letters["a"]["metrics"]["annual_eps_cagr_percent"] >= 25.0
    assert letters["n"]["status"] == "info"
    assert letters["n"]["metrics"] == {
        "company_name": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Semiconductors",
        "description": "NVIDIA designs accelerated computing products.",
    }
    assert letters["s"]["status"] == "pass"
    assert letters["s"]["metrics"]["latest_close"] == 155.0
    assert letters["s"]["metrics"]["latest_volume"] == 180_000_000.0
    assert letters["s"]["metrics"]["average_volume_50d"] == 100_000_000.0
    assert letters["s"]["metrics"]["volume_ratio"] == 1.8
    assert letters["s"]["metrics"]["float_shares"] == 22_000_000_000.0
    assert letters["s"]["metrics"]["outstanding_shares"] == 24_000_000_000.0
    assert letters["l"]["status"] == "watch"
    assert letters["l"]["metrics"]["peer_count"] == 2
    assert letters["l"]["metrics"]["peer_rank_percentile"] is None
    assert letters["i"]["status"] == "pass"
    assert letters["i"]["institutional_flow"] == {
        "holders_count_change": 100.0,
        "shares_change_percent": 0.08,
        "ownership_percent": 0.57,
        "market_value_change_percent": 0.11,
    }
    assert letters["i"]["top_performing_holders"] == [
        {
            "holder_name": "High Quality Capital",
            "cik": "0000000001",
            "shares": 10_000_000.0,
            "market_value": 1_550_000_000.0,
            "position_change_percent": 0.2,
            "portfolio_weight_percent": 0.04,
            "performance_1y_percent": 32.0,
            "performance_3y_percent": 85.0,
            "performance_5y_percent": 160.0,
            "excess_vs_sp500_percent": 21.0,
        }
    ]
    assert letters["m"]["status"] == "info"
    assert letters["m"]["symbol"] == "SPY"
    assert letters["m"]["range"] == "6m"
    assert letters["m"]["source"] == "fmp"
    assert letters["m"]["candles"][0]["traded_value_usd"] == 252_000_000_000.0
    assert "recommendation" not in letters["m"]
    assert "verdict" not in letters["m"]


def test_build_canslim_analysis_returns_common_letter_envelopes():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(),
        market_range="6m",
        cached=False,
    )

    letters = analysis["letters"]
    for key in ["c", "a", "n", "s", "l"]:
        assert set(letters[key]) >= _COMMON_LETTER_KEYS

    assert set(letters["i"]) >= _COMMON_LETTER_KEYS | {
        "institutional_flow",
        "top_performing_holders",
    }


@pytest.mark.parametrize(
    ("stock_latest", "stock_oldest", "spy_latest", "spy_oldest", "expected_status"),
    [
        (130.0, 100.0, 105.0, 100.0, "watch"),
        (110.0, 100.0, 105.0, 100.0, "watch"),
        (103.0, 100.0, 105.0, 100.0, "fail"),
        (None, 100.0, 105.0, 100.0, "unknown"),
    ],
)
def test_build_canslim_analysis_classifies_leader_statuses(
    stock_latest,
    stock_oldest,
    spy_latest,
    spy_oldest,
    expected_status,
):
    bundle = _canslim_bundle(
        prices=_price_rows(latest_close=stock_latest, oldest_close=stock_oldest),
        spy_prices=_spy_price_rows(latest_close=spy_latest, oldest_close=spy_oldest),
    )

    analysis = canslim_service.build_canslim_analysis(
        bundle,
        market_range="1y",
        cached=True,
    )

    assert analysis["letters"]["l"]["status"] == expected_status
    assert analysis["letters"]["l"]["metrics"]["peer_count"] == 2


def test_build_canslim_analysis_marks_missing_eps_unknown():
    bundle = _canslim_bundle(quarterly_income=[], annual_income=[])

    analysis = canslim_service.build_canslim_analysis(
        bundle,
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["c"]["status"] == "unknown"
    assert analysis["letters"]["a"]["status"] == "unknown"


def test_build_canslim_analysis_normalizes_top_level_currency_to_usd():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(profile=_profile(currency="usd")),
        market_range="6m",
        cached=False,
    )

    assert analysis["currency"] == "USD"


def test_build_canslim_analysis_calculates_supply_without_float_data():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(
            float_data=FmpFloatData(
                symbol="NVDA",
                float_shares=None,
                outstanding_shares=None,
            )
        ),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["s"]["status"] == "pass"
    assert analysis["letters"]["s"]["metrics"]["float_shares"] is None
    assert analysis["letters"]["s"]["metrics"]["outstanding_shares"] is None


def test_build_canslim_analysis_compares_quarterly_eps_to_same_prior_year_period():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(
            quarterly_income=[
                FmpIncomeRow(
                    date="2026-04-30",
                    period="Q1",
                    calendar_year=2026,
                    eps_diluted=1.25,
                ),
                FmpIncomeRow(
                    date="2025-12-31",
                    period="Q4",
                    calendar_year=2025,
                    eps_diluted=1.00,
                ),
                FmpIncomeRow(
                    date="2025-09-30",
                    period="Q3",
                    calendar_year=2025,
                    eps_diluted=0.90,
                ),
                FmpIncomeRow(
                    date="2025-06-30",
                    period="Q2",
                    calendar_year=2025,
                    eps_diluted=0.80,
                ),
                FmpIncomeRow(
                    date="2025-04-30",
                    period="Q1",
                    calendar_year=2025,
                    eps_diluted=0.50,
                ),
            ]
        ),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["c"]["metrics"]["quarterly_eps_growth_percent"] == 150.0


def test_build_canslim_analysis_defaults_top_holder_non_nullable_fields():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(
            top_holders=[
                FmpTopHolder(
                    holder=None,
                    cik=None,
                    shares=None,
                    market_value=None,
                    change=None,
                    weight=None,
                    performance_1y_percent=None,
                    performance_3y_percent=None,
                    performance_5y_percent=None,
                    performance_relative_to_sp500_percent=None,
                )
            ]
        ),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["i"]["top_performing_holders"] == [
        {
            "holder_name": "",
            "cik": "",
            "shares": 0.0,
            "market_value": 0.0,
            "position_change_percent": None,
            "portfolio_weight_percent": None,
            "performance_1y_percent": None,
            "performance_3y_percent": None,
            "performance_5y_percent": None,
            "excess_vs_sp500_percent": None,
        }
    ]


def test_build_canslim_analysis_filters_invalid_market_candles():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(
            spy_prices=[
                FmpPriceRow(
                    symbol="SPY",
                    date="2026-07-02",
                    open=418,
                    high=422,
                    low=417,
                    close=420,
                    volume=600_000_000,
                    vwap=420,
                    traded_value_usd=252_000_000_000,
                ),
                FmpPriceRow(
                    symbol="SPY",
                    date=None,
                    open=418,
                    high=422,
                    low=417,
                    close=420,
                    volume=600_000_000,
                    vwap=420,
                    traded_value_usd=252_000_000_000,
                ),
                FmpPriceRow(
                    symbol="SPY",
                    date="2026-06-30",
                    open=0,
                    high=422,
                    low=417,
                    close=420,
                    volume=600_000_000,
                    vwap=420,
                    traded_value_usd=252_000_000_000,
                ),
                FmpPriceRow(
                    symbol="SPY",
                    date="2026-06-29",
                    open=418,
                    high=422,
                    low=417,
                    close=420,
                    volume=None,
                    vwap=420,
                    traded_value_usd=252_000_000_000,
                ),
                FmpPriceRow(
                    symbol="SPY",
                    date="2026-06-28",
                    open=418,
                    high=422,
                    low=417,
                    close=420,
                    volume=600_000_000,
                    vwap=420,
                    traded_value_usd=None,
                ),
            ]
        ),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["m"]["candles"] == [
        {
            "date": "2026-07-02",
            "open": 418,
            "high": 422,
            "low": 417,
            "close": 420,
            "volume": 600_000_000,
            "traded_value_usd": 252_000_000_000,
        }
    ]


def test_build_canslim_analysis_rejects_invalid_market_range():
    with pytest.raises(ValueError, match="시장 컨텍스트 기간은 3m, 6m, 1y 중 하나여야 합니다."):
        canslim_service.build_canslim_analysis(
            _canslim_bundle(),
            market_range="2y",
            cached=False,
        )


@pytest.mark.parametrize(
    "profile",
    [
        FmpCompanyProfile(
            symbol="005930",
            company_name="Samsung Electronics",
            exchange="KRX",
            sector="Technology",
            industry="Consumer Electronics",
            description="Korean common stock.",
            currency="KRW",
            is_etf=False,
        ),
        FmpCompanyProfile(
            symbol="SPY",
            company_name="SPDR S&P 500 ETF Trust",
            exchange="ARCA",
            sector=None,
            industry=None,
            description="ETF.",
            currency="USD",
            is_etf=True,
        ),
    ],
)
def test_build_canslim_analysis_rejects_non_us_or_etf_targets(profile):
    with pytest.raises(ValueError, match="CAN SLIM v1은 미국 상장 보통주만 지원합니다."):
        canslim_service.build_canslim_analysis(
            _canslim_bundle(profile=profile),
            market_range="6m",
            cached=False,
        )


def test_build_canslim_analysis_marks_missing_13f_data_unknown():
    analysis = canslim_service.build_canslim_analysis(
        _canslim_bundle(positions_summary=None, top_holders=[]),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["i"]["status"] == "unknown"
    assert set(analysis["letters"]["i"]) >= _COMMON_LETTER_KEYS | {
        "institutional_flow",
        "top_performing_holders",
    }
    assert analysis["letters"]["i"]["institutional_flow"] == {
        "holders_count_change": None,
        "shares_change_percent": None,
        "ownership_percent": None,
        "market_value_change_percent": None,
    }
    assert analysis["letters"]["i"]["top_performing_holders"] == []


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


def _canslim_bundle(
    *,
    profile: FmpCompanyProfile | None = None,
    quarterly_income: list[FmpIncomeRow] | None = None,
    annual_income: list[FmpIncomeRow] | None = None,
    prices: list[FmpPriceRow] | None = None,
    spy_prices: list[FmpPriceRow] | None = None,
    float_data: FmpFloatData | None = None,
    positions_summary: FmpPositionsSummary | None | object = _DEFAULT_POSITIONS_SUMMARY,
    top_holders: list[FmpTopHolder] | None = None,
) -> FmpCanslimBundle:
    if positions_summary is _DEFAULT_POSITIONS_SUMMARY:
        positions_summary = FmpPositionsSummary(
            symbol="NVDA",
            year=2026,
            quarter=1,
            holders_count=4100,
            holders_count_change=100,
            shares_count=14_000_000_000,
            shares_count_change=0.08,
            ownership_percent=0.57,
            market_value_change=0.11,
        )
    if top_holders is None:
        top_holders = [
            FmpTopHolder(
                holder="High Quality Capital",
                cik="0000000001",
                shares=10_000_000,
                market_value=1_550_000_000,
                change=0.20,
                weight=0.04,
                performance_1y_percent=32,
                performance_3y_percent=85,
                performance_5y_percent=160,
                performance_relative_to_sp500_percent=21,
            )
        ]

    return FmpCanslimBundle(
        symbol="NVDA",
        profile=profile or _profile(),
        quarterly_income=quarterly_income
        if quarterly_income is not None
        else [
            FmpIncomeRow(date="2026-04-30", period="Q1", calendar_year=2026, eps_diluted=1.25),
            FmpIncomeRow(date="2025-04-30", period="Q1", calendar_year=2025, eps_diluted=0.50),
        ],
        annual_income=annual_income
        if annual_income is not None
        else [
            FmpIncomeRow(date="2026-01-31", period="FY", calendar_year=2026, eps_diluted=4.00),
            FmpIncomeRow(date="2025-01-31", period="FY", calendar_year=2025, eps_diluted=2.50),
            FmpIncomeRow(date="2024-01-31", period="FY", calendar_year=2024, eps_diluted=1.25),
        ],
        prices=prices or _price_rows(),
        spy_prices=spy_prices or _spy_price_rows(),
        float_data=float_data
        or FmpFloatData(
            symbol="NVDA",
            float_shares=22_000_000_000,
            outstanding_shares=24_000_000_000,
        ),
        peers=["AMD", "AVGO"],
        positions_summary=(
            positions_summary if isinstance(positions_summary, FmpPositionsSummary) else None
        ),
        top_holders=top_holders,
    )


def _profile(*, currency: str = "USD") -> FmpCompanyProfile:
    return FmpCompanyProfile(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        sector="Technology",
        industry="Semiconductors",
        description="NVIDIA designs accelerated computing products.",
        currency=currency,
        is_etf=False,
    )


def _price_rows(
    *,
    latest_close: float | None = 155.0,
    oldest_close: float | None = 100.0,
) -> list[FmpPriceRow]:
    rows = [
        FmpPriceRow(
            symbol="NVDA",
            date="2026-07-02",
            open=150,
            high=156,
            low=149,
            close=latest_close,
            volume=180_000_000,
            vwap=153.5,
            traded_value_usd=27_630_000_000,
        ),
        FmpPriceRow(
            symbol="NVDA",
            date="2026-07-01",
            open=148,
            high=151,
            low=147,
            close=150,
            volume=100_000_000,
            vwap=149.5,
            traded_value_usd=14_950_000_000,
        ),
    ]
    rows.extend(
        FmpPriceRow(
            symbol="NVDA",
            date=f"2026-05-{day:02d}",
            open=99,
            high=101,
            low=98,
            close=oldest_close if day == 1 else 100,
            volume=100_000_000,
            vwap=100,
            traded_value_usd=10_000_000_000,
        )
        for day in range(1, 50)
    )
    return rows


def _spy_price_rows(
    *,
    latest_close: float | None = 420.0,
    oldest_close: float | None = 400.0,
) -> list[FmpPriceRow]:
    return [
        FmpPriceRow(
            symbol="SPY",
            date="2026-07-02",
            open=418,
            high=422,
            low=417,
            close=latest_close,
            volume=600_000_000,
            vwap=420,
            traded_value_usd=252_000_000_000,
        ),
        FmpPriceRow(
            symbol="SPY",
            date="2026-01-06",
            open=398,
            high=401,
            low=397,
            close=oldest_close,
            volume=500_000_000,
            vwap=400,
            traded_value_usd=200_000_000_000,
        ),
    ]

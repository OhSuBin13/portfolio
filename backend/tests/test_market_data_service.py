from pathlib import Path

import pytest

from portfolio_app.services import market_data as market_data_service
from portfolio_app.services.market_data import (
    MarketQuote,
    TossFxRateProvider,
    TossMarketDataProvider,
    keep_last_good_quote,
)


def test_keep_last_good_quote_uses_previous_value_on_error():
    previous = MarketQuote(symbol="VOO", price=500.0, currency="USD", source="toss")

    result = keep_last_good_quote(previous=previous, error_message="rate limit")

    assert result.price == 500.0
    assert result.status == "stale"
    assert result.error_message == "rate limit"


def test_legacy_fx_provider_code_is_removed():
    source = (
        Path(__file__).parents[1] / "src/portfolio_app/services/market_data.py"
    ).read_text()

    for legacy_name in (
        "NaverFinanceProvider",
        "FrankfurterProvider",
        "FallbackFxRateProvider",
        "NAVER_USD_KRW_URL",
        "finance.naver.com",
        "api.frankfurter.dev",
        "naver_finance",
        "frankfurter",
    ):
        assert legacy_name not in source


def test_market_data_provider_resolver_selects_toss_for_us_stock():
    toss_provider = TossMarketDataProvider(client_id="toss-client", client_secret="toss-secret")
    asset = {"type": "stock_etf", "market": "US", "currency": "USD"}

    provider = market_data_service.market_data_provider_for_asset(
        asset,
        toss_provider=toss_provider,
    )

    assert provider is toss_provider


def test_market_data_provider_resolver_selects_toss_for_kr_stock():
    toss_provider = TossMarketDataProvider(client_id="toss-client", client_secret="toss-secret")
    asset = {"type": "stock_etf", "market": "KR", "currency": "KRW"}

    provider = market_data_service.market_data_provider_for_asset(
        asset,
        toss_provider=toss_provider,
    )

    assert provider is toss_provider


@pytest.mark.asyncio
async def test_market_data_provider_resolver_rejects_non_stock_etf_market():
    toss_provider = TossMarketDataProvider(client_id="toss-client", client_secret="toss-secret")
    asset = {"type": "stock_etf", "market": "JP", "currency": "JPY"}

    provider = market_data_service.market_data_provider_for_asset(
        asset,
        toss_provider=toss_provider,
    )

    with pytest.raises(ValueError, match="JP/JPY 시세 동기화는 아직 지원하지 않습니다."):
        await provider.fetch_equity_quote("7203")


@pytest.mark.asyncio
async def test_toss_market_data_provider_fetches_token_and_parses_price(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/prices?symbols=005930",
        json={
            "result": [
                {
                    "symbol": "005930",
                    "timestamp": "2026-06-27T10:00:00+09:00",
                    "lastPrice": "75000",
                    "currency": "KRW",
                }
            ]
        },
    )
    provider = TossMarketDataProvider(client_id="toss-client", client_secret="toss-secret")

    quote = await provider.fetch_equity_quote("005930")

    assert quote == MarketQuote(symbol="005930", price=75_000, currency="KRW", source="toss")
    requests = httpx_mock.get_requests()
    token_request = requests[0]
    assert token_request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert token_request.content == (
        b"grant_type=client_credentials&client_id=toss-client&client_secret=toss-secret"
    )
    price_request = requests[1]
    assert price_request.headers["authorization"] == "Bearer token-123"


@pytest.mark.asyncio
async def test_toss_market_data_provider_batches_symbols_in_chunks_of_200(httpx_mock):
    symbols = [f"SYM{i:03d}" for i in range(201)] + ["sym000", " "]
    first_chunk = [f"SYM{i:03d}" for i in range(200)]
    second_chunk = ["SYM200"]
    httpx_mock.add_response(
        method="POST",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        json={
            "result": [
                {"symbol": symbol, "lastPrice": "100.00", "currency": "USD"}
                for symbol in first_chunk
            ]
        },
    )
    httpx_mock.add_response(
        method="GET",
        json={
            "result": [
                {"symbol": symbol, "lastPrice": "200.00", "currency": "USD"}
                for symbol in second_chunk
            ]
        },
    )
    provider = TossMarketDataProvider(client_id="toss-client", client_secret="toss-secret")

    quotes = await provider.fetch_equity_quotes(symbols)

    assert [quote.symbol for quote in quotes] == first_chunk + second_chunk
    assert quotes[-1].price == 200
    price_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/prices"
    ]
    assert [request.url.params["symbols"] for request in price_requests] == [
        ",".join(first_chunk),
        ",".join(second_chunk),
    ]


@pytest.mark.asyncio
async def test_toss_market_data_provider_requires_credentials():
    provider = TossMarketDataProvider(client_id=" ", client_secret="toss-secret")

    with pytest.raises(ValueError, match="Toss API 인증 정보가 필요합니다."):
        await provider.fetch_equity_quote("005930")


@pytest.mark.asyncio
async def test_toss_fx_rate_provider_fetches_token_and_parses_exchange_rate(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://openapi.tossinvest.com/api/v1/exchange-rate"
            "?baseCurrency=USD&quoteCurrency=KRW"
        ),
        json={
            "result": {
                "baseCurrency": "USD",
                "quoteCurrency": "KRW",
                "rate": "1380.5",
                "midRate": "1375",
                "basisPoint": "40",
                "rateChangeType": "UP",
                "validFrom": "2026-03-25T09:30:00+09:00",
                "validUntil": "2026-03-25T09:31:00+09:00",
            }
        },
    )
    provider = TossFxRateProvider(client_id="toss-client", client_secret="toss-secret")

    rate = await provider.fetch_rate("usd", "krw")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1380.5
    assert rate.source == "toss"
    assert rate.change_percent is None
    exchange_rate_request = httpx_mock.get_requests()[1]
    assert exchange_rate_request.headers["authorization"] == "Bearer token-123"


def test_default_fx_rate_provider_uses_toss_when_credentials_are_configured(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_TOSS_API_KEY", "toss-client")
    monkeypatch.setenv("PORTFOLIO_TOSS_SECRET_KEY", "toss-secret")

    provider = market_data_service.default_fx_rate_provider()

    assert isinstance(provider, TossFxRateProvider)


@pytest.mark.asyncio
async def test_toss_fx_rate_provider_requires_credentials():
    provider = TossFxRateProvider(client_id="toss-client", client_secret=" ")

    with pytest.raises(ValueError, match="Toss API 인증 정보가 필요합니다."):
        await provider.fetch_rate("USD", "KRW")

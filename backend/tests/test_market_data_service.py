import pytest

from portfolio_app.services import market_data as market_data_service
from portfolio_app.services.market_data import (
    FallbackFxRateProvider,
    FrankfurterProvider,
    MarketQuote,
    NaverFinanceProvider,
    TossMarketDataProvider,
    keep_last_good_quote,
)


def test_keep_last_good_quote_uses_previous_value_on_error():
    previous = MarketQuote(symbol="VOO", price=500.0, currency="USD", source="toss")

    result = keep_last_good_quote(previous=previous, error_message="rate limit")

    assert result.price == 500.0
    assert result.status == "stale"
    assert result.error_message == "rate limit"


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
async def test_frankfurter_provider_parses_pair_rate(httpx_mock):
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FrankfurterProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1375.5


@pytest.mark.asyncio
async def test_naver_finance_provider_parses_usd_krw_rate_and_change_percent(httpx_mock):
    httpx_mock.add_response(
        text="""
        <div class="spot">
          <div class="today">
            <p class="no_today">
              <em class="no_down"><em class="no_down">
                <span class="no1">1</span><span class="shim">,</span><span class="no5">5</span>
                <span class="no1">1</span><span class="no3">3</span><span class="jum">.</span>
                <span class="no2">2</span><span class="no0">0</span>
              </em></em>
            </p>
            <p class="no_exday">
              <span class="txt_comparison">전일대비</span>
              <em class="no_down"><span class="ico down"></span><span class="no2">2</span></em>
              <em class="no_down">
                <span class="parenthesis1">(</span>
                <span class="ico minus">-</span><span class="no0">0</span><span class="jum">.</span>
                <span class="no1">1</span><span class="no5">5</span><span class="per">%</span>
                <span class="parenthesis2">)</span>
              </em>
            </p>
          </div>
        </div>
        """,
        headers={"content-type": "text/html;charset=EUC-KR"},
    )
    provider = NaverFinanceProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1513.2
    assert rate.change_percent == -0.15
    assert rate.source == "naver_finance"


@pytest.mark.asyncio
async def test_fallback_fx_rate_provider_uses_frankfurter_when_naver_fails(httpx_mock):
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FallbackFxRateProvider(NaverFinanceProvider(), FrankfurterProvider())

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.rate == 1375.5
    assert rate.change_percent is None
    assert rate.source == "frankfurter"

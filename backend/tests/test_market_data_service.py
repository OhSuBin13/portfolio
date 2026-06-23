import logging

import pytest

from portfolio_app.services import market_data as market_data_service
from portfolio_app.services.market_data import (
    AlphaVantageProvider,
    FallbackFxRateProvider,
    FrankfurterProvider,
    MarketQuote,
    NaverFinanceProvider,
    keep_last_good_quote,
)


def test_keep_last_good_quote_uses_previous_value_on_error():
    previous = MarketQuote(symbol="VOO", price=500.0, currency="USD", source="alpha_vantage")

    result = keep_last_good_quote(previous=previous, error_message="rate limit")

    assert result.price == 500.0
    assert result.status == "stale"
    assert result.error_message == "rate limit"


def test_market_data_provider_resolver_selects_alpha_for_us_stock():
    alpha_provider = AlphaVantageProvider("demo-key")
    asset = {"type": "stock_etf", "market": "US", "currency": "USD"}

    provider = market_data_service.market_data_provider_for_asset(
        asset,
        alpha_provider=alpha_provider,
    )

    assert provider is alpha_provider


@pytest.mark.asyncio
async def test_market_data_provider_resolver_rejects_kr_stock():
    alpha_provider = AlphaVantageProvider("demo-key")
    asset = {"type": "stock_etf", "market": "KR", "currency": "KRW"}

    provider = market_data_service.market_data_provider_for_asset(
        asset,
        alpha_provider=alpha_provider,
    )

    with pytest.raises(ValueError, match="KR 시장 시세 동기화는 아직 지원하지 않습니다."):
        await provider.fetch_equity_quote("005930")


@pytest.mark.asyncio
async def test_alpha_vantage_logs_unexpected_payload_without_api_key(httpx_mock, caplog):
    secret_key = "secret-alpha-key-123"
    httpx_mock.add_response(json={"Information": "rate limit reached"})
    provider = AlphaVantageProvider(secret_key)

    with (
        caplog.at_level(logging.WARNING, logger="portfolio_app.services.market_data"),
        pytest.raises(ValueError, match="시세 정보를 찾을 수 없습니다"),
    ):
        await provider.fetch_equity_quote("mu")

    records = [
        record
        for record in caplog.records
        if record.message.startswith("Alpha Vantage quote response missing Global Quote")
    ]
    assert len(records) == 1
    assert records[0].symbol == "MU"
    assert records[0].payload_summary == {
        "keys": ["Information"],
        "messages": {"Information": "rate limit reached"},
    }
    assert "symbol=MU" in records[0].message
    assert "rate limit reached" in records[0].message
    logged = "\n".join(str(record.__dict__) for record in caplog.records)
    assert secret_key not in logged
    assert "apikey" not in logged.lower()


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

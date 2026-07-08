import pytest

from portfolio_app.services.fx_rates import TossFxRateProvider
from portfolio_app.services.toss_http import TossAuthClient


@pytest.mark.asyncio
async def test_toss_fx_rate_provider_is_exposed_from_fx_rates_module(httpx_mock):
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
                "rate": "1400",
                "validFrom": "2026-06-29T09:00:00+09:00",
            }
        },
    )
    provider = TossFxRateProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    rate = await provider.fetch_rate(" usd ", " krw ")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1400
    assert rate.source == "toss"
    assert rate.fetched_at == "2026-06-29T09:00:00+09:00"

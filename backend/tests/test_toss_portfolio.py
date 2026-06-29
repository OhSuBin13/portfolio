import asyncio

import httpx
import pytest

from portfolio_app.services.market_data import (
    TOSS_DEFAULT_RETRY_AFTER_SECONDS,
    FxRate,
    TossAuthClient,
    TossFxRateProvider,
    _retry_after_seconds,
    request_with_toss_retry,
)
from portfolio_app.services.toss_portfolio import (
    TossBrokerageProvider,
    TossHolding,
    build_toss_summary,
    fetch_toss_summary,
)


@pytest.mark.asyncio
async def test_toss_auth_client_posts_client_credentials_form(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    auth_client = TossAuthClient(" toss-client ", " toss-secret ")

    token = await auth_client.token()
    cached_token = await auth_client.token()

    assert token == "token-123"
    assert cached_token == "token-123"
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].content.decode() == (
        "grant_type=client_credentials&client_id=toss-client&client_secret=toss-secret"
    )


@pytest.mark.asyncio
async def test_toss_auth_client_serializes_concurrent_token_fetches(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    auth_client = TossAuthClient("toss-client", "toss-secret")

    tokens = await asyncio.gather(auth_client.token(), auth_client.token())

    assert tokens == ["token-123", "token-123"]
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].method == "POST"


@pytest.mark.asyncio
async def test_toss_auth_client_retries_token_once_after_429_retry_after(httpx_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        status_code=429,
        headers={"Retry-After": "0.25", "X-RateLimit-Remaining": "0"},
        json={"error": "rate-limit-exceeded"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    auth_client = TossAuthClient("toss-client", "toss-secret", sleep=fake_sleep)

    token = await auth_client.token()

    assert token == "token-123"
    assert sleeps == [0.25]
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_toss_auth_client_reuses_token_before_expiry_and_refreshes_after_expiry(
    httpx_mock,
):
    now = [1000.0]

    def fake_now() -> float:
        return now[0]

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 120},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-456", "token_type": "Bearer", "expires_in": 120},
    )
    auth_client = TossAuthClient("toss-client", "toss-secret", now=fake_now)

    first_token = await auth_client.token()
    now[0] = 1059.0
    cached_token = await auth_client.token()
    now[0] = 1060.1
    refreshed_token = await auth_client.token()

    assert [first_token, cached_token, refreshed_token] == [
        "token-123",
        "token-123",
        "token-456",
    ]
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize(
    ("headers", "expected_delay"),
    [
        ({"X-RateLimit-Reset": "0.75"}, 0.75),
        ({"Retry-After": "soon"}, TOSS_DEFAULT_RETRY_AFTER_SECONDS),
        ({"Retry-After": "-1.25"}, 0.0),
    ],
)
def test_retry_after_seconds_parses_rate_limit_headers(headers, expected_delay):
    response = httpx.Response(429, headers=headers)

    assert _retry_after_seconds(response) == expected_delay


@pytest.mark.asyncio
async def test_request_with_toss_retry_returns_second_429_without_internal_raise():
    sleeps: list[float] = []
    request_count = 0

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "0.5"},
            json={"attempt": request_count},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await request_with_toss_retry(
            client,
            "GET",
            "https://openapi.tossinvest.com/api/v1/accounts",
            sleep=fake_sleep,
        )

    assert response.status_code == 429
    assert response.json() == {"attempt": 2}
    assert sleeps == [0.5]
    assert request_count == 2


@pytest.mark.asyncio
async def test_toss_fx_rate_provider_sends_authorization_header(httpx_mock):
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
    auth_client = TossAuthClient("toss-client", "toss-secret")
    provider = TossFxRateProvider("toss-client", "toss-secret", auth_client=auth_client)

    rate = await provider.fetch_rate(" usd ", " krw ")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1400
    assert rate.source == "toss"
    assert rate.fetched_at == "2026-06-29T09:00:00+09:00"
    fx_request = httpx_mock.get_requests()[1]
    assert fx_request.headers["authorization"] == "Bearer token-123"


@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_accounts(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": 12345,
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    accounts = await provider.fetch_accounts()

    assert accounts[0].account_seq == "12345"
    assert accounts[0].account_no == "123-45-67890"
    assert accounts[0].account_type == "BROKERAGE"
    assert accounts[0].display_name == "토스증권 123-45-67890"


@pytest.mark.asyncio
async def test_toss_brokerage_provider_rejects_malformed_account_item(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={"result": ["not-an-account"]},
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    with pytest.raises(ValueError, match="계좌 항목"):
        await provider.fetch_accounts()


@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_holdings(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "marketCountry": "KR",
                        "currency": "KRW",
                        "quantity": "10",
                        "lastPrice": "75000",
                        "averagePurchasePrice": "70000",
                        "marketValue": {
                            "purchaseAmount": "700000",
                            "amount": "750000",
                            "amountAfterCost": "749000",
                        },
                    },
                    {
                        "symbol": "VOO",
                        "name": "Vanguard S&P 500 ETF",
                        "marketCountry": "US",
                        "currency": "USD",
                        "quantity": "3",
                        "lastPrice": "500",
                        "averagePurchasePrice": "450",
                        "marketValue": {
                            "purchaseAmount": "1350",
                            "amount": "1500",
                            "amountAfterCost": "1499",
                        },
                    },
                ]
            }
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    holdings = await provider.fetch_holdings("12345")

    assert [holding.symbol for holding in holdings] == ["005930", "VOO"]
    assert holdings[0].market == "KR"
    assert holdings[0].market_value == 750000
    assert holdings[1].currency == "USD"
    assert holdings[1].market_value == 1500
    request = httpx_mock.get_requests()[1]
    assert request.headers["x-tossinvest-account"] == "12345"


@pytest.mark.asyncio
async def test_toss_brokerage_provider_rejects_malformed_holding_item(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={"result": {"items": ["not-a-holding"]}},
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    with pytest.raises(ValueError, match="보유자산 항목"):
        await provider.fetch_holdings("12345")


class StubFxProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        self.calls.append((base_currency, quote_currency))
        assert base_currency == "USD"
        assert quote_currency == "KRW"
        return FxRate(
            base_currency="USD",
            quote_currency="KRW",
            rate=1400,
            source="toss",
            fetched_at="2026-06-29T00:00:00+00:00",
        )


def test_build_toss_summary_uses_toss_holdings_and_fx_rate():
    holdings = [
        TossHolding(
            symbol="005930",
            name="삼성전자",
            market="KR",
            currency="KRW",
            quantity=10,
            average_purchase_price=70000,
            last_price=75000,
            market_value=750000,
        ),
        TossHolding(
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            market="US",
            currency="USD",
            quantity=3,
            average_purchase_price=450,
            last_price=500,
            market_value=1500,
        ),
    ]

    result = build_toss_summary(holdings, usd_krw_rate=1400)

    assert result.summary.net_worth_krw == 2_850_000
    assert result.summary.gross_assets_krw == 2_850_000
    assert result.summary.debt_krw == 0
    assert result.summary.monthly_income_krw == 0
    assert result.summary.usd_krw_rate == 1400
    assert result.asset_mix == {"stock_etf": 100}
    assert [row["asset_key"] for row in result.asset_allocations] == [
        "KR:005930",
        "US:VOO",
    ]


class StubTossBrokerageProvider:
    def __init__(self, holdings: list[TossHolding]) -> None:
        self.holdings = holdings
        self.requested_accounts: list[str] = []

    async def fetch_holdings(self, account_seq: str) -> list[TossHolding]:
        self.requested_accounts.append(account_seq)
        return self.holdings


def test_toss_accounts_cache_returns_entry_until_ttl_expires():
    now = 100.0

    def fake_now() -> float:
        return now

    from portfolio_app.services.toss_portfolio import TossAccount, TossAccountsCache

    cache = TossAccountsCache(ttl_seconds=10, now=fake_now)
    account = TossAccount(
        account_seq="acct-1",
        account_no="123-45-67890",
        account_type="BROKERAGE",
        display_name="토스증권 123-45-67890",
    )

    cache.set([account])
    assert cache.get() == [account]

    now = 111.0
    assert cache.get() is None


@pytest.mark.asyncio
async def test_toss_accounts_cache_collapses_concurrent_fetches():
    from portfolio_app.services.toss_portfolio import TossAccount, TossAccountsCache

    cache = TossAccountsCache(ttl_seconds=60)
    account = TossAccount(
        account_seq="acct-1",
        account_no="123-45-67890",
        account_type="BROKERAGE",
        display_name="토스증권 123-45-67890",
    )
    calls = 0

    async def fetch_accounts() -> list[TossAccount]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [account]

    results = await asyncio.gather(
        cache.get_or_fetch(fetch_accounts),
        cache.get_or_fetch(fetch_accounts),
    )

    assert results == [[account], [account]]
    assert calls == 1


@pytest.mark.asyncio
async def test_fetch_toss_summary_fetches_fx_once_for_usd_holdings():
    provider = StubTossBrokerageProvider(
        [
            TossHolding(
                symbol="VOO",
                name="Vanguard S&P 500 ETF",
                market="US",
                currency="USD",
                quantity=3,
                average_purchase_price=450,
                last_price=500,
                market_value=1500,
            )
        ]
    )
    fx_provider = StubFxProvider()

    result = await fetch_toss_summary(
        "12345",
        provider,
        fx_provider=fx_provider,
    )

    assert provider.requested_accounts == ["12345"]
    assert fx_provider.calls == [("USD", "KRW")]
    assert result.summary.net_worth_krw == 2_100_000


@pytest.mark.asyncio
async def test_fetch_toss_summary_does_not_fetch_fx_for_krw_only_holdings():
    provider = StubTossBrokerageProvider(
        [
            TossHolding(
                symbol="005930",
                name="삼성전자",
                market="KR",
                currency="KRW",
                quantity=10,
                average_purchase_price=70000,
                last_price=75000,
                market_value=750000,
            )
        ]
    )
    fx_provider = StubFxProvider()

    result = await fetch_toss_summary(
        "12345",
        provider,
        fx_provider=fx_provider,
    )

    assert provider.requested_accounts == ["12345"]
    assert fx_provider.calls == []
    assert result.summary.net_worth_krw == 750000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("market", "currency"),
    [
        ("KR", "USD"),
        ("US", "KRW"),
    ],
)
async def test_toss_brokerage_provider_rejects_market_currency_mismatch(
    httpx_mock,
    market,
    currency,
):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "VOO",
                        "name": "Vanguard S&P 500 ETF",
                        "marketCountry": market,
                        "currency": currency,
                        "quantity": "3",
                        "lastPrice": "500",
                        "averagePurchasePrice": "450",
                        "marketValue": {"amount": "1500"},
                    }
                ]
            }
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    with pytest.raises(ValueError, match="시장과 통화 조합"):
        await provider.fetch_holdings("12345")

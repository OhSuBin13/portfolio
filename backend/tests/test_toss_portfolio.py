import pytest

from portfolio_app.services.market_data import FxRate, TossAuthClient
from portfolio_app.services.toss_portfolio import (
    TossBrokerageProvider,
    TossHolding,
    build_toss_summary,
    fetch_toss_summary,
)


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

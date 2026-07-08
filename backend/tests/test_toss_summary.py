from portfolio_app.services.toss_portfolio import TossBuyingPower, TossHolding
from portfolio_app.services.toss_summary import build_toss_summary


def test_build_toss_summary_module_converts_holdings_and_cash_to_krw():
    result = build_toss_summary(
        [
            TossHolding(
                symbol="VOO",
                name="Vanguard S&P 500 ETF",
                market="US",
                currency="USD",
                quantity=2,
                average_purchase_price=450,
                last_price=500,
                market_value=1000,
            )
        ],
        buying_power=[TossBuyingPower(currency="KRW", cash_buying_power=50_000)],
        usd_krw_rate=1400,
    )

    assert result.summary.net_worth_krw == 1_450_000
    assert result.summary.buying_power_total_krw == 50_000
    assert result.asset_mix == {
        "cash": 3.4482758620689653,
        "stock_etf": 96.55172413793103,
    }
    assert result.asset_allocations[0]["asset_key"] == "US:VOO"

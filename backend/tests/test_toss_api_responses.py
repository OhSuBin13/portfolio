from portfolio_app.api.toss_responses import (
    account_response,
    buying_power_response,
    candle_response,
    holding_response,
)
from portfolio_app.services.market_data import MarketCandle
from portfolio_app.services.toss_portfolio import TossAccount, TossBuyingPower, TossHolding


def test_toss_api_response_mappers_preserve_service_values():
    account = account_response(
        TossAccount(
            account_seq="seq-1",
            account_no="123-456",
            account_type="위탁",
            display_name="내 계좌",
        )
    )
    holding = holding_response(
        TossHolding(
            symbol="AAPL",
            name="Apple",
            market="US",
            currency="USD",
            quantity=2,
            average_purchase_price=150,
            last_price=180,
            market_value=360,
        )
    )
    buying_power = buying_power_response(TossBuyingPower(currency="KRW", cash_buying_power=1000))
    candle = candle_response(
        MarketCandle(
            symbol="AAPL",
            timestamp="2026-01-01T00:00:00Z",
            open=170,
            high=181,
            low=169,
            close=180,
            volume=1234,
        )
    )

    assert account.model_dump() == {
        "account_seq": "seq-1",
        "account_no": "123-456",
        "account_type": "위탁",
        "display_name": "내 계좌",
    }
    assert holding.model_dump() == {
        "symbol": "AAPL",
        "name": "Apple",
        "market": "US",
        "currency": "USD",
        "quantity": 2,
        "average_purchase_price": 150,
        "last_price": 180,
        "market_value": 360,
    }
    assert buying_power.model_dump() == {
        "currency": "KRW",
        "cash_buying_power": 1000,
    }
    assert candle.model_dump() == {
        "symbol": "AAPL",
        "timestamp": "2026-01-01T00:00:00Z",
        "open": 170,
        "high": 181,
        "low": 169,
        "close": 180,
        "volume": 1234,
    }

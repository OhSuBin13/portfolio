from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.models import Currency, TossMarket
from portfolio_app.services.market_data import MarketCandle
from portfolio_app.services.toss_portfolio import TossAccount, TossBuyingPower, TossHolding


class TossAccountResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    account_seq: str
    account_no: str
    account_type: str
    display_name: str


class TossHoldingResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    symbol: str
    name: str
    market: TossMarket
    currency: Currency
    quantity: float = Field(ge=0, allow_inf_nan=False)
    average_purchase_price: float = Field(ge=0, allow_inf_nan=False)
    last_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    market_value: float = Field(ge=0, allow_inf_nan=False)


class TossBuyingPowerResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    currency: Currency
    cash_buying_power: float = Field(ge=0, allow_inf_nan=False)


class TossCandleResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    symbol: str
    timestamp: str = Field(min_length=1)
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0, allow_inf_nan=False)


class ChartMarkerMemoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    account_seq: str
    symbol: str
    marker_key: str
    memo: str
    created_at: str
    updated_at: str


def account_response(account: TossAccount) -> TossAccountResponse:
    return TossAccountResponse(
        account_seq=account.account_seq,
        account_no=account.account_no,
        account_type=account.account_type,
        display_name=account.display_name,
    )


def holding_response(holding: TossHolding) -> TossHoldingResponse:
    return TossHoldingResponse(
        symbol=holding.symbol,
        name=holding.name,
        market=holding.market,
        currency=holding.currency,
        quantity=holding.quantity,
        average_purchase_price=holding.average_purchase_price,
        last_price=holding.last_price,
        market_value=holding.market_value,
    )


def buying_power_response(row: TossBuyingPower) -> TossBuyingPowerResponse:
    return TossBuyingPowerResponse(
        currency=row.currency,
        cash_buying_power=row.cash_buying_power,
    )


def candle_response(candle: MarketCandle) -> TossCandleResponse:
    return TossCandleResponse(
        symbol=candle.symbol,
        timestamp=candle.timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )

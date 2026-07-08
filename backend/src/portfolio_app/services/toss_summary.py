import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_app.models import (
    BuyingPower,
    Currency,
    PortfolioSummary,
    TossAssetAllocation,
    TossMarket,
)


class SummaryHolding(Protocol):
    symbol: str
    name: str
    market: TossMarket
    currency: Currency
    market_value: float


class SummaryBuyingPower(Protocol):
    currency: Currency
    cash_buying_power: float


@dataclass(frozen=True)
class TossSummaryResult:
    summary: PortfolioSummary
    asset_mix: dict[str, float]
    asset_allocations: list[dict[str, Any]]


def build_toss_summary(
    holdings: Sequence[SummaryHolding],
    *,
    buying_power: Sequence[SummaryBuyingPower] | None = None,
    usd_krw_rate: float | None,
) -> TossSummaryResult:
    buying_power_rows = buying_power or []
    needs_usd_rate = any(
        holding.currency == "USD" and holding.market_value > 0 for holding in holdings
    ) or any(
        row.currency == "USD" and row.cash_buying_power > 0 for row in buying_power_rows
    )
    if needs_usd_rate:
        rate = _positive_number(usd_krw_rate, "USD 보유자산에는 USD/KRW 환율이 필요합니다.")
    else:
        rate = usd_krw_rate

    allocation_values: list[tuple[SummaryHolding, float]] = []
    for holding in holdings:
        value_krw = holding.market_value
        if holding.currency == "USD" and holding.market_value > 0:
            value_krw = holding.market_value * float(rate)
        allocation_values.append((holding, value_krw))

    buying_power_values: list[BuyingPower] = []
    for row in buying_power_rows:
        value_krw = row.cash_buying_power
        if row.currency == "USD":
            value_krw = row.cash_buying_power * float(rate) if row.cash_buying_power > 0 else 0
        buying_power_values.append(
            BuyingPower(
                currency=row.currency,
                cash_buying_power=row.cash_buying_power,
                value_krw=value_krw,
            )
        )

    holdings_total_krw = sum(value_krw for _, value_krw in allocation_values)
    buying_power_total_krw = sum(row.value_krw for row in buying_power_values)
    total_krw = holdings_total_krw + buying_power_total_krw
    asset_mix = {}
    if buying_power_total_krw > 0 and total_krw > 0:
        asset_mix["cash"] = buying_power_total_krw / total_krw * 100
    if holdings_total_krw > 0 and total_krw > 0:
        asset_mix["stock_etf"] = holdings_total_krw / total_krw * 100
    asset_allocations = [
        TossAssetAllocation(
            asset_key=f"{holding.market}:{holding.symbol}",
            asset_type="stock_etf",
            symbol=holding.symbol,
            name=holding.name,
            label=holding.symbol,
            market=holding.market,
            currency=holding.currency,
            value_krw=value_krw,
            percent=(value_krw / total_krw * 100) if total_krw > 0 else 0,
        ).model_dump()
        for holding, value_krw in allocation_values
    ]

    return TossSummaryResult(
        summary=PortfolioSummary(
            net_worth_krw=total_krw,
            gross_assets_krw=total_krw,
            debt_krw=0,
            monthly_income_krw=0,
            buying_power=buying_power_values,
            buying_power_total_krw=buying_power_total_krw,
            usd_krw_rate=rate,
        ),
        asset_mix=asset_mix,
        asset_allocations=asset_allocations,
    )


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number

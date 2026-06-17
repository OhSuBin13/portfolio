import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from portfolio_app.finance import calculate_asset_mix, calculate_net_worth
from portfolio_app.models import AssetAllocation, HoldingValue, PortfolioSummary
from portfolio_app.repositories import (
    SummaryHoldingRow,
    SummaryIncomeRow,
    fetch_latest_transaction_fx_rate_to_krw,
    fetch_summary_holding_rows,
    fetch_summary_income_rows,
)
from portfolio_app.services.fx_rates import latest_fx_rate


@dataclass(frozen=True)
class SummaryResult:
    summary: PortfolioSummary
    asset_mix: dict[str, float]
    asset_allocations: list[dict[str, object]]


def _best_fx_rate(row: SummaryHoldingRow) -> float | None:
    rate = row.latest_fx_rate_to_krw or row.transaction_fx_rate_to_krw
    if rate is None or float(rate) <= 0:
        return None
    return float(rate)


def _native_value_to_krw(value: float, row: SummaryHoldingRow) -> float:
    currency = row.asset_currency.upper()
    if currency == "KRW" or value == 0:
        return value

    rate = _best_fx_rate(row)
    if rate is None:
        raise ValueError(f"{currency} 자산 평가에 필요한 환율 정보가 없습니다.")
    return value * rate


def _holding_value_krw(row: SummaryHoldingRow) -> float:
    asset_type = row.asset_type
    quantity = row.quantity

    if asset_type in {"cash", "savings", "debt"}:
        value_krw = _native_value_to_krw(quantity, row)
    elif row.latest_price_krw is not None:
        value_krw = quantity * row.latest_price_krw
    elif row.manual_price_krw is not None:
        value_krw = quantity * row.manual_price_krw
    elif row.average_cost is not None:
        value_krw = _native_value_to_krw(quantity * row.average_cost, row)
    else:
        value_krw = 0

    return max(0.0, value_krw)


def _holding_value(row: SummaryHoldingRow) -> HoldingValue:
    return HoldingValue(asset_type=row.asset_type, value_krw=_holding_value_krw(row))


def _asset_allocation_label(row: SummaryHoldingRow) -> str:
    return row.asset_symbol or row.asset_name


def _asset_allocations(
    rows_with_values: Sequence[tuple[SummaryHoldingRow, HoldingValue]],
) -> list[dict[str, object]]:
    grouped: dict[int, dict[str, object]] = {}

    for row, value in rows_with_values:
        if value.asset_type == "debt" or value.value_krw <= 0:
            continue

        asset_id = row.asset_id
        if asset_id not in grouped:
            grouped[asset_id] = {
                "asset_id": asset_id,
                "asset_type": value.asset_type,
                "label": _asset_allocation_label(row),
                "name": row.asset_name,
                "symbol": row.asset_symbol,
                "value_krw": 0.0,
            }
        grouped[asset_id]["value_krw"] = float(grouped[asset_id]["value_krw"]) + value.value_krw

    denominator = sum(float(row["value_krw"]) for row in grouped.values())
    if denominator <= 0:
        return []

    allocations = []
    for row in grouped.values():
        value_krw = float(row["value_krw"])
        allocation = AssetAllocation(
            asset_id=int(row["asset_id"]),
            asset_type=row["asset_type"],
            symbol=row["symbol"],
            name=str(row["name"]),
            label=str(row["label"]),
            value_krw=value_krw,
            percent=round((value_krw / denominator) * 100, 2),
        )
        allocations.append(allocation.model_dump())

    return allocations


def _income_amount_to_krw(row: SummaryIncomeRow) -> float:
    amount = row.amount
    currency = row.currency.upper()
    if currency == "KRW" or amount == 0:
        return amount

    rate = row.fx_rate_to_krw
    if rate is None or float(rate) <= 0:
        raise ValueError(f"{currency} 소득 거래에 필요한 환율 정보가 없습니다.")
    return amount * float(rate)


def _current_month_bounds(today: date | None = None) -> tuple[str, str]:
    current_day = today or date.today()
    start = current_day.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start.isoformat(), next_month.isoformat()


def _monthly_income_krw(income_rows: Sequence[SummaryIncomeRow]) -> float:
    return sum(_income_amount_to_krw(row) for row in income_rows)


def _usd_krw_snapshot(
    latest_fx: sqlite3.Row | None,
    latest_transaction_fx_rate: float | None,
) -> tuple[float | None, float | None]:
    if latest_fx is not None and float(latest_fx["rate"]) > 0:
        change_percent = latest_fx["change_percent"]
        return (
            float(latest_fx["rate"]),
            float(change_percent) if change_percent is not None else None,
        )

    if latest_transaction_fx_rate is None:
        return None, None
    return latest_transaction_fx_rate, None


def build_summary_from_rows(
    *,
    holding_rows: Sequence[SummaryHoldingRow],
    income_rows: Sequence[SummaryIncomeRow],
    usd_krw_rate: float | None,
    usd_krw_change_percent: float | None,
) -> SummaryResult:
    rows_with_values = [(row, _holding_value(row)) for row in holding_rows]
    values = [value for _row, value in rows_with_values]
    summary = calculate_net_worth(values).model_copy(
        update={
            "monthly_income_krw": _monthly_income_krw(income_rows),
            "usd_krw_rate": usd_krw_rate,
            "usd_krw_change_percent": usd_krw_change_percent,
        }
    )
    return SummaryResult(
        summary=summary,
        asset_mix=calculate_asset_mix(values),
        asset_allocations=_asset_allocations(rows_with_values),
    )


def build_summary(
    db: sqlite3.Connection,
    *,
    today: date | None = None,
) -> SummaryResult:
    month_start, next_month_start = _current_month_bounds(today)
    usd_krw_rate, usd_krw_change_percent = _usd_krw_snapshot(
        latest_fx_rate(db, base_currency="USD", quote_currency="KRW"),
        fetch_latest_transaction_fx_rate_to_krw(db, currency="USD"),
    )
    return build_summary_from_rows(
        holding_rows=fetch_summary_holding_rows(db),
        income_rows=fetch_summary_income_rows(
            db,
            month_start=month_start,
            next_month_start=next_month_start,
        ),
        usd_krw_rate=usd_krw_rate,
        usd_krw_change_percent=usd_krw_change_percent,
    )

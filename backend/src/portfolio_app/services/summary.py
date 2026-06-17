import sqlite3
from dataclasses import dataclass
from datetime import date

from portfolio_app.finance import calculate_asset_mix, calculate_net_worth
from portfolio_app.models import AssetAllocation, HoldingValue, PortfolioSummary
from portfolio_app.services.fx_rates import latest_fx_rate


@dataclass(frozen=True)
class SummaryResult:
    summary: PortfolioSummary
    asset_mix: dict[str, float]
    asset_allocations: list[dict[str, object]]


def _best_fx_rate(row: sqlite3.Row) -> float | None:
    rate = row["latest_fx_rate_to_krw"] or row["transaction_fx_rate_to_krw"]
    if rate is None or float(rate) <= 0:
        return None
    return float(rate)


def _native_value_to_krw(value: float, row: sqlite3.Row) -> float:
    currency = str(row["asset_currency"]).upper()
    if currency == "KRW" or value == 0:
        return value

    rate = _best_fx_rate(row)
    if rate is None:
        raise ValueError(f"{currency} 자산 평가에 필요한 환율 정보가 없습니다.")
    return value * rate


def _holding_value_krw(row: sqlite3.Row) -> float:
    asset_type = row["asset_type"]
    quantity = float(row["quantity"] or 0)

    if asset_type in {"cash", "savings", "debt"}:
        value_krw = _native_value_to_krw(quantity, row)
    elif row["latest_price_krw"] is not None:
        value_krw = quantity * float(row["latest_price_krw"])
    elif row["manual_price_krw"] is not None:
        value_krw = quantity * float(row["manual_price_krw"])
    elif row["average_cost"] is not None:
        value_krw = _native_value_to_krw(quantity * float(row["average_cost"]), row)
    else:
        value_krw = 0

    return max(0.0, value_krw)


def _holding_value(row: sqlite3.Row) -> HoldingValue:
    return HoldingValue(asset_type=row["asset_type"], value_krw=_holding_value_krw(row))


def _asset_allocation_label(row: sqlite3.Row) -> str:
    symbol = row["asset_symbol"]
    if symbol:
        return str(symbol)
    return str(row["asset_name"])


def _asset_allocations(
    rows_with_values: list[tuple[sqlite3.Row, HoldingValue]],
) -> list[dict[str, object]]:
    grouped: dict[int, dict[str, object]] = {}

    for row, value in rows_with_values:
        if value.asset_type == "debt" or value.value_krw <= 0:
            continue

        asset_id = int(row["asset_id"])
        if asset_id not in grouped:
            grouped[asset_id] = {
                "asset_id": asset_id,
                "asset_type": value.asset_type,
                "label": _asset_allocation_label(row),
                "name": str(row["asset_name"]),
                "symbol": str(row["asset_symbol"]) if row["asset_symbol"] else None,
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


def _income_amount_to_krw(row: sqlite3.Row) -> float:
    amount = float(row["amount"] or 0)
    currency = str(row["currency"]).upper()
    if currency == "KRW" or amount == 0:
        return amount

    rate = row["fx_rate_to_krw"]
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


def _monthly_income_krw(db: sqlite3.Connection, *, today: date | None = None) -> float:
    month_start, next_month_start = _current_month_bounds(today)
    rows = db.execute(
        """
        select amount, currency, fx_rate_to_krw
        from transactions
        where type in ('dividend', 'interest')
          and occurred_on >= ?
          and occurred_on < ?
        order by id
        """,
        (month_start, next_month_start),
    ).fetchall()
    return sum(_income_amount_to_krw(row) for row in rows)


def _latest_usd_krw_snapshot(db: sqlite3.Connection) -> tuple[float | None, float | None]:
    latest_fx = latest_fx_rate(db, base_currency="USD", quote_currency="KRW")
    if latest_fx is not None and float(latest_fx["rate"]) > 0:
        change_percent = latest_fx["change_percent"]
        return (
            float(latest_fx["rate"]),
            float(change_percent) if change_percent is not None else None,
        )

    latest_transaction_fx = db.execute(
        """
        select fx_rate_to_krw
        from transactions
        where currency = 'USD'
          and fx_rate_to_krw is not null
          and fx_rate_to_krw > 0
        order by occurred_on desc, id desc
        limit 1
        """
    ).fetchone()
    if latest_transaction_fx is None:
        return None, None
    return float(latest_transaction_fx["fx_rate_to_krw"]), None


def build_summary(
    db: sqlite3.Connection,
    *,
    today: date | None = None,
) -> SummaryResult:
    rows = db.execute(
        """
        select h.quantity,
               h.average_cost,
               h.account_id,
               a.id as asset_id,
               a.symbol as asset_symbol,
               a.name as asset_name,
               a.type as asset_type,
               a.currency as asset_currency,
               a.manual_price_krw,
               (
                 select t.fx_rate_to_krw
                 from transactions t
                 where t.account_id = h.account_id
                   and t.asset_id = h.asset_id
                   and t.fx_rate_to_krw is not null
                 order by t.occurred_on desc, t.id desc
                 limit 1
               ) as transaction_fx_rate_to_krw,
               (
                 select fx.rate
                 from fx_rates fx
                 where fx.base_currency = a.currency
                   and fx.quote_currency = 'KRW'
                 order by fx.fetched_at desc, fx.id desc
                 limit 1
               ) as latest_fx_rate_to_krw,
               (
                 select ps.price_krw
                 from price_snapshots ps
                 where ps.asset_id = a.id
                   and ps.status in ('ok', 'manual', 'stale')
                 order by ps.fetched_at desc, ps.id desc
                 limit 1
               ) as latest_price_krw
        from holdings h
        join assets a on a.id = h.asset_id
        order by h.id
        """
    ).fetchall()
    rows_with_values = [(row, _holding_value(row)) for row in rows]
    values = [value for _row, value in rows_with_values]
    usd_krw_rate, usd_krw_change_percent = _latest_usd_krw_snapshot(db)
    summary = calculate_net_worth(values).model_copy(
        update={
            "monthly_income_krw": _monthly_income_krw(db, today=today),
            "usd_krw_rate": usd_krw_rate,
            "usd_krw_change_percent": usd_krw_change_percent,
        }
    )
    return SummaryResult(
        summary=summary,
        asset_mix=calculate_asset_mix(values),
        asset_allocations=_asset_allocations(rows_with_values),
    )

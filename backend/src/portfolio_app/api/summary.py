import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from portfolio_app.api import get_db
from portfolio_app.finance import calculate_asset_mix, calculate_net_worth
from portfolio_app.models import HoldingValue

router = APIRouter(prefix="/api/summary", tags=["summary"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{currency} 자산 평가에 필요한 환율 정보가 없습니다.",
        )
    return value * rate


def _holding_value(row: sqlite3.Row) -> HoldingValue:
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

    return HoldingValue(asset_type=asset_type, value_krw=max(0.0, value_krw))


@router.get("")
def get_summary(db: Db) -> dict[str, object]:
    rows = db.execute(
        """
        select h.quantity,
               h.average_cost,
               h.account_id,
               h.asset_id,
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
    values = [_holding_value(row) for row in rows]
    summary = calculate_net_worth(values)
    return {
        **summary.model_dump(),
        "asset_mix": calculate_asset_mix(values),
    }

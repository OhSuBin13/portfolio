import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from portfolio_app.api import get_db
from portfolio_app.finance import calculate_asset_mix, calculate_net_worth
from portfolio_app.models import HoldingValue

router = APIRouter(prefix="/api/summary", tags=["summary"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _holding_value(row: sqlite3.Row) -> HoldingValue:
    asset_type = row["asset_type"]
    quantity = float(row["quantity"] or 0)

    if asset_type in {"cash", "savings", "debt"}:
        value_krw = quantity
    else:
        unit_price = row["latest_price_krw"] or row["manual_price_krw"] or row["average_cost"] or 0
        value_krw = quantity * float(unit_price)

    return HoldingValue(asset_type=asset_type, value_krw=max(0.0, value_krw))


@router.get("")
def get_summary(db: Db) -> dict[str, object]:
    rows = db.execute(
        """
        select h.quantity,
               h.average_cost,
               a.type as asset_type,
               a.manual_price_krw,
               (
                 select ps.price_krw
                 from price_snapshots ps
                 where ps.asset_id = a.id
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

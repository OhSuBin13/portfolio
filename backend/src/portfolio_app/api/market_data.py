import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from portfolio_app.api import get_db
from portfolio_app.models import MarketDataStatus

router = APIRouter(prefix="/api/market-data", tags=["market-data"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _snapshot_response(row: sqlite3.Row) -> dict[str, object]:
    return {
        "asset_id": row["asset_id"],
        "source": row["source"],
        "price_krw": row["price_krw"],
        "status": row["status"],
        "error_message": row["error_message"],
        "fetched_at": row["fetched_at"],
    }


@router.get("/status", response_model=list[MarketDataStatus])
def list_market_data_status(db: Db) -> list[dict[str, object]]:
    rows = db.execute(
        """
        select ps.asset_id, ps.source, ps.price_krw, ps.status, ps.error_message, ps.fetched_at
        from price_snapshots ps
        where ps.id = (
            select latest.id
            from price_snapshots latest
            where latest.asset_id = ps.asset_id
            order by latest.fetched_at desc, latest.id desc
            limit 1
        )
        order by ps.asset_id
        """
    ).fetchall()
    return [_snapshot_response(row) for row in rows]

import asyncio
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import get_db, require_non_empty, require_positive_number, row_to_dict
from portfolio_app.services.market_data import (
    insert_price_snapshot,
    sync_market_data_for_settings,
)

router = APIRouter(prefix="/api/market-data", tags=["market-data"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class ManualPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int
    price_krw: float
    source: str = "manual"
    error_message: str = ""


def _snapshot_response(row: sqlite3.Row) -> dict[str, object]:
    return {
        "asset_id": row["asset_id"],
        "source": row["source"],
        "price_krw": row["price_krw"],
        "status": row["status"],
        "error_message": row["error_message"],
        "fetched_at": row["fetched_at"],
    }


@router.post("/manual-price", status_code=status.HTTP_201_CREATED)
def create_manual_price(payload: ManualPriceCreate, db: Db) -> dict[str, object]:
    price_krw = require_positive_number(payload.price_krw, "가격은 0보다 커야 합니다.")
    source = require_non_empty(payload.source, "시세 출처를 입력해 주세요.")
    asset = db.execute("select * from assets where id = ?", (payload.asset_id,)).fetchone()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="자산을 찾을 수 없습니다.",
        )

    with db:
        db.execute(
            "update assets set manual_price_krw = ?, updated_at = current_timestamp where id = ?",
            (price_krw, payload.asset_id),
        )
        row = insert_price_snapshot(
            db,
            asset_id=payload.asset_id,
            source=source,
            price=price_krw,
            currency="KRW",
            price_krw=price_krw,
            status="manual",
            error_message=payload.error_message,
        )

    return row_to_dict(row)


@router.get("/status")
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


@router.post("/sync")
def sync_market_data(request: Request, db: Db) -> dict[str, object]:
    return asyncio.run(sync_market_data_for_settings(request.app.state.settings, db))

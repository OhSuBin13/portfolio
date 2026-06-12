import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import created_row, get_db, require_allowed, require_non_empty, row_to_dict
from portfolio_app.repositories import create_asset

ASSET_TYPES = {"cash", "savings", "stock_etf", "crypto", "debt"}

router = APIRouter(prefix="/api/assets", tags=["assets"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = None
    name: str
    type: str
    currency: str
    market: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_asset_endpoint(payload: AssetCreate, db: Db) -> dict[str, object]:
    symbol = payload.symbol.strip().upper() if payload.symbol else None
    name = require_non_empty(payload.name, "자산 이름을 입력해 주세요.")
    asset_type = require_allowed(payload.type, ASSET_TYPES, "지원하지 않는 자산 유형입니다.")
    currency = require_non_empty(payload.currency, "통화를 입력해 주세요.").upper()
    market = require_non_empty(payload.market, "시장을 입력해 주세요.").upper()

    try:
        asset_id = create_asset(
            db,
            symbol=symbol,
            name=name,
            type=asset_type,
            currency=currency,
            market=market,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자산 정보를 저장할 수 없습니다.",
        ) from exc

    return created_row(db, "assets", asset_id)


@router.get("")
def list_assets(db: Db) -> list[dict[str, object]]:
    rows = db.execute("select * from assets order by id").fetchall()
    return [row_to_dict(row) for row in rows]

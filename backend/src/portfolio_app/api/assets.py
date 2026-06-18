import sqlite3
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app import repositories
from portfolio_app.api import get_db, require_allowed, require_non_empty, row_to_dict

ASSET_TYPES = {"cash", "savings", "stock_etf", "debt"}

router = APIRouter(prefix="/api/assets", tags=["assets"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = None
    name: str
    type: str
    currency: str
    market: str | None = None


@dataclass(frozen=True)
class ValidatedAssetPayload:
    symbol: str | None
    name: str
    type: str
    currency: str
    market: str | None


def validate_asset_payload(payload: AssetCreate) -> ValidatedAssetPayload:
    symbol = payload.symbol.strip().upper() if payload.symbol else None
    name = require_non_empty(payload.name, "자산 이름을 입력해 주세요.")
    asset_type = require_allowed(payload.type, ASSET_TYPES, "지원하지 않는 자산 유형입니다.")
    currency = require_non_empty(payload.currency, "통화를 입력해 주세요.").upper()
    market_value = payload.market.strip().upper() if payload.market else ""
    market = market_value or None

    if asset_type == "stock_etf":
        market = require_non_empty(payload.market or "", "시장을 입력해 주세요.").upper()
    elif asset_type in {"cash", "savings", "debt"}:
        symbol = None
        market = None

    return ValidatedAssetPayload(
        symbol=symbol,
        name=name,
        type=asset_type,
        currency=currency,
        market=market,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_asset_endpoint(payload: AssetCreate, db: Db) -> dict[str, object]:
    asset = validate_asset_payload(payload)

    try:
        row = repositories.create_asset_record(
            db,
            symbol=asset.symbol,
            name=asset.name,
            type=asset.type,
            currency=asset.currency,
            market=asset.market,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자산 정보를 저장할 수 없습니다.",
        ) from exc

    return row_to_dict(row)


@router.get("")
def list_assets(db: Db) -> list[dict[str, object]]:
    return [row_to_dict(row) for row in repositories.fetch_assets(db)]

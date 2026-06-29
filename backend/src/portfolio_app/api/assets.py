import sqlite3
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from portfolio_app import repositories
from portfolio_app.api import get_db, require_allowed, require_non_empty, row_to_dict
from portfolio_app.services.stock_metadata import (
    TossStockMetadataProvider,
    safe_stock_metadata_error_message,
)

ASSET_TYPES = {"cash", "savings", "stock_etf", "debt"}
METADATA_SOURCES = {"manual", "toss"}

router = APIRouter(prefix="/api/assets", tags=["assets"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = None
    name: str
    type: str
    currency: str
    market: str | None = None
    is_listed: bool | None = None
    instrument_type: str | None = None
    metadata_source: str = "manual"


class StockMetadataResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    is_listed: bool
    instrument_type: str | None
    metadata_source: str


@dataclass(frozen=True)
class ValidatedAssetPayload:
    symbol: str | None
    name: str
    type: str
    currency: str
    market: str | None
    is_listed: bool | None
    instrument_type: str | None
    metadata_source: str


def validate_asset_payload(payload: AssetCreate) -> ValidatedAssetPayload:
    symbol = payload.symbol.strip().upper() if payload.symbol else None
    name = require_non_empty(payload.name, "자산 이름을 입력해 주세요.")
    asset_type = require_allowed(payload.type, ASSET_TYPES, "지원하지 않는 자산 유형입니다.")
    currency = require_non_empty(payload.currency, "통화를 입력해 주세요.").upper()
    market_value = payload.market.strip().upper() if payload.market else ""
    market = market_value or None
    metadata_source = require_allowed(
        payload.metadata_source,
        METADATA_SOURCES,
        "지원하지 않는 메타데이터 출처입니다.",
    )
    instrument_type_value = payload.instrument_type.strip() if payload.instrument_type else ""
    instrument_type = instrument_type_value.upper() if instrument_type_value else None
    is_listed = payload.is_listed

    if asset_type == "stock_etf":
        market = require_non_empty(payload.market or "", "시장을 입력해 주세요.").upper()
        if is_listed is None:
            is_listed = True
    elif asset_type in {"cash", "savings", "debt"}:
        symbol = None
        market = None
        is_listed = None
        instrument_type = None
        metadata_source = "manual"

    return ValidatedAssetPayload(
        symbol=symbol,
        name=name,
        type=asset_type,
        currency=currency,
        market=market,
        is_listed=is_listed,
        instrument_type=instrument_type,
        metadata_source=metadata_source,
    )


@router.get("/stock-metadata", response_model=StockMetadataResponse)
async def lookup_stock_metadata(symbol: str, request: Request) -> StockMetadataResponse:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="종목 심볼을 입력해 주세요.",
        )

    settings = request.app.state.settings
    provider = TossStockMetadataProvider(settings.toss_api_key, settings.toss_secret_key)
    try:
        metadata = await provider.fetch_stock_metadata(normalized_symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=safe_stock_metadata_error_message(exc),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=safe_stock_metadata_error_message(exc),
        ) from exc

    return StockMetadataResponse(
        symbol=metadata.symbol,
        name=metadata.name,
        market=metadata.market,
        currency=metadata.currency,
        is_listed=metadata.is_listed,
        instrument_type=metadata.instrument_type,
        metadata_source=metadata.metadata_source,
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
            is_listed=asset.is_listed,
            instrument_type=asset.instrument_type,
            metadata_source=asset.metadata_source,
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

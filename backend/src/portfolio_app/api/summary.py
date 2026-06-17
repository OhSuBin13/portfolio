import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from portfolio_app.api import get_db
from portfolio_app.services.fx_rates import FX_REFRESH_TTL_SECONDS, refresh_fx_rate_if_stale
from portfolio_app.services.summary import build_summary

router = APIRouter(prefix="/api/summary", tags=["summary"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("")
async def get_summary(
    db: Db,
    refresh: bool = True,
    fx_ttl_seconds: int = Query(default=FX_REFRESH_TTL_SECONDS, ge=0, le=86_400),
) -> dict[str, object]:
    if refresh:
        await refresh_fx_rate_if_stale(db, ttl_seconds=fx_ttl_seconds)

    try:
        summary, asset_mix, asset_allocations = build_summary(db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        **summary.model_dump(),
        "asset_mix": asset_mix,
        "asset_allocations": asset_allocations,
    }

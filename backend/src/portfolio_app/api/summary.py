import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from portfolio_app.api import get_db
from portfolio_app.models import SummaryResponse
from portfolio_app.services import goals as goal_service
from portfolio_app.services.fx_rates import FX_REFRESH_TTL_SECONDS, refresh_fx_rate_if_stale
from portfolio_app.services.market_data import default_fx_rate_provider
from portfolio_app.services.summary import build_summary

router = APIRouter(prefix="/api/summary", tags=["summary"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("", response_model=SummaryResponse)
async def get_summary(
    request: Request,
    db: Db,
    refresh: bool = True,
    fx_ttl_seconds: int = Query(default=FX_REFRESH_TTL_SECONDS, ge=0, le=86_400),
) -> SummaryResponse:
    if refresh:
        await refresh_fx_rate_if_stale(
            db,
            ttl_seconds=fx_ttl_seconds,
            provider=default_fx_rate_provider(request.app.state.settings),
        )

    try:
        result = build_summary(db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return SummaryResponse(
        **result.summary.model_dump(),
        asset_mix=result.asset_mix,
        asset_allocations=result.asset_allocations,
        goal_progress=goal_service.list_goal_progress_for_summary(db, result.summary),
    )

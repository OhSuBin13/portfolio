import sqlite3
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from portfolio_app.api import get_db
from portfolio_app.models import CanslimAnalysisResponse
from portfolio_app.services.canslim import (
    INVALID_MARKET_RANGE_MESSAGE,
    FmpCanslimProvider,
    FmpProviderError,
    build_canslim_analysis,
    normalize_symbol,
)

router = APIRouter(prefix="/api/canslim", tags=["canslim"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]
SymbolQuery = Annotated[str, Query(min_length=1)]
SUPPORTED_MARKET_RANGES = {"3m", "6m", "1y"}


@router.get("/analysis", response_model=CanslimAnalysisResponse)
async def get_canslim_analysis(
    request: Request,
    db: Db,
    symbol: SymbolQuery,
    market_range: str = "6m",
    refresh: bool = False,
) -> CanslimAnalysisResponse:
    del db, refresh
    normalized_range = market_range.strip().lower()
    if normalized_range not in SUPPORTED_MARKET_RANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_MARKET_RANGE_MESSAGE,
        )

    try:
        normalized_symbol = normalize_symbol(symbol)
        settings = request.app.state.settings
        today = getattr(request.app.state, "canslim_today", None)
        provider = (
            FmpCanslimProvider(settings.fmp_api_key, today=today)
            if today is not None
            else FmpCanslimProvider(settings.fmp_api_key)
        )
        bundle = await provider.fetch_bundle(normalized_symbol, market_range=normalized_range)
        analysis = build_canslim_analysis(
            bundle,
            market_range=normalized_range,
            cached=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (FmpProviderError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return CanslimAnalysisResponse.model_validate(analysis)

import sqlite3
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError

from portfolio_app import repositories
from portfolio_app.api import get_db
from portfolio_app.models import CanslimAnalysisResponse
from portfolio_app.services.canslim import (
    INVALID_MARKET_RANGE_MESSAGE,
    FmpCanslimProvider,
    FmpProviderError,
    build_canslim_analysis,
    cache_expiry_iso,
    cached_payload_is_fresh,
    canslim_analysis_cache_key,
    dumps_analysis_payload,
    loads_analysis_payload,
    normalize_symbol,
    now_iso,
)

router = APIRouter(prefix="/api/canslim", tags=["canslim"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]
SymbolQuery = Annotated[str, Query(min_length=1)]
SUPPORTED_MARKET_RANGES = {"3m", "6m", "1y"}


def _safe_http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"FMP 요청 실패: HTTP {response.status_code} {reason}"
    return f"FMP 요청 실패: {exc.__class__.__name__}"


@router.get("/analysis", response_model=CanslimAnalysisResponse)
async def get_canslim_analysis(
    request: Request,
    db: Db,
    symbol: SymbolQuery,
    market_range: str = "6m",
    refresh: bool = False,
) -> CanslimAnalysisResponse:
    normalized_range = market_range.strip().lower()
    if normalized_range not in SUPPORTED_MARKET_RANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_MARKET_RANGE_MESSAGE,
        )

    try:
        normalized_symbol = normalize_symbol(symbol)
        cache_key = canslim_analysis_cache_key(normalized_symbol, normalized_range)
        cached_row = repositories.fetch_canslim_cache_entry(db, cache_key=cache_key)
        if not refresh and cached_row is not None:
            try:
                if cached_payload_is_fresh(cached_row):
                    return CanslimAnalysisResponse.model_validate(
                        loads_analysis_payload(
                            cached_row["payload_json"],
                            market_range=normalized_range,
                            symbol=normalized_symbol,
                        )
                    )
            except (KeyError, TypeError, ValueError, ValidationError):
                pass

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
        response = CanslimAnalysisResponse.model_validate(analysis)
        repositories.upsert_canslim_cache_entry(
            db,
            cache_key=cache_key,
            provider="fmp",
            payload_json=dumps_analysis_payload(response.model_dump(by_alias=True)),
            fetched_at=now_iso(),
            expires_at=cache_expiry_iso(1),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FmpProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_safe_http_error_detail(exc),
        ) from exc

    return response

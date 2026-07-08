import sqlite3
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from portfolio_app.api import get_db
from portfolio_app.api.errors import toss_http_error_detail
from portfolio_app.api.validation import normalize_account_seq
from portfolio_app.models import SummaryResponse
from portfolio_app.services import goals as goal_service
from portfolio_app.services.fx_rates import CachedFxRateProvider
from portfolio_app.services.market_data import default_fx_rate_provider
from portfolio_app.services.toss_portfolio import TossBrokerageProvider, fetch_toss_summary

router = APIRouter(prefix="/api/summary", tags=["summary"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]
AccountSeq = Annotated[str, Query(min_length=1)]


@router.get("", response_model=SummaryResponse)
async def get_summary(
    request: Request,
    db: Db,
    account_seq: AccountSeq,
) -> SummaryResponse:
    normalized_account_seq = normalize_account_seq(account_seq)
    settings = request.app.state.settings
    auth_client = request.app.state.toss_auth_client
    provider = TossBrokerageProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=auth_client,
    )
    try:
        result = await fetch_toss_summary(
            normalized_account_seq,
            provider,
            fx_provider=CachedFxRateProvider(
                db,
                provider=default_fx_rate_provider(settings, auth_client=auth_client),
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=toss_http_error_detail(exc),
        ) from exc

    return SummaryResponse(
        **result.summary.model_dump(),
        asset_mix=result.asset_mix,
        asset_allocations=result.asset_allocations,
        goal_progress=goal_service.list_goal_progress_for_summary(db, result.summary),
    )

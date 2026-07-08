from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.api import row_to_dict
from portfolio_app.api.dependencies import Db
from portfolio_app.api.errors import toss_http_error_detail
from portfolio_app.api.toss_responses import (
    ChartMarkerMemoResponse,
    TossAccountResponse,
    TossBuyingPowerResponse,
    TossCandleResponse,
    TossHoldingResponse,
    account_response,
    buying_power_response,
    candle_response,
    holding_response,
)
from portfolio_app.api.validation import normalize_account_seq
from portfolio_app.models import (
    TossOrderImportCreate,
    TossOrderImportRunResponse,
    TossOrderResponse,
)
from portfolio_app.repositories import (
    delete_chart_marker_memo,
    fetch_chart_marker_memos,
    fetch_toss_order_import_run,
    fetch_toss_order_import_runs,
    fetch_toss_orders,
    upsert_chart_marker_memo,
)
from portfolio_app.services.market_data import TossMarketDataProvider
from portfolio_app.services.toss_order_imports import import_toss_orders
from portfolio_app.services.toss_portfolio import (
    TossAccountsCache,
    TossBrokerageProvider,
)

router = APIRouter(prefix="/api/toss", tags=["toss"])
AccountSeq = Annotated[str, Query(min_length=1)]
CANDLE_SYMBOL_REQUIRED_MESSAGE = "Toss 캔들 조회 종목 심볼을 입력해 주세요."
CHART_MARKER_REQUIRED_MESSAGE = "차트 마커 식별자를 입력해 주세요."
DATE_RANGE_MESSAGE = "조회 시작일은 종료일보다 늦을 수 없습니다."


class ChartMarkerMemoUpsert(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    account_seq: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    marker_key: str = Field(min_length=1, max_length=200)
    memo: str = Field(max_length=2000)


def _provider(request: Request) -> TossBrokerageProvider:
    settings = request.app.state.settings
    return TossBrokerageProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=request.app.state.toss_auth_client,
    )


def _market_data_provider(request: Request) -> TossMarketDataProvider:
    settings = request.app.state.settings
    return TossMarketDataProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=request.app.state.toss_auth_client,
    )


def _accounts_cache(request: Request) -> TossAccountsCache:
    return request.app.state.toss_accounts_cache


def _normalize_optional_uppercase(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_marker_key(marker_key: str) -> str:
    normalized = marker_key.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CHART_MARKER_REQUIRED_MESSAGE,
        )
    return normalized


def _validate_date_range(from_date: date | None, to_date: date | None) -> None:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=DATE_RANGE_MESSAGE,
        )


@router.post(
    "/order-imports",
    response_model=TossOrderImportRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_toss_order_import(
    payload: TossOrderImportCreate,
    request: Request,
    db: Db,
) -> dict[str, object]:
    account_seq = normalize_account_seq(payload.account_seq)
    symbol = _normalize_optional_uppercase(payload.symbol)
    _validate_date_range(payload.from_date, payload.to_date)
    try:
        result = await import_toss_orders(
            db,
            provider=_provider(request),
            account_seq=account_seq,
            status=payload.status,
            symbol=symbol,
            from_date=payload.from_date.isoformat() if payload.from_date else None,
            to_date=payload.to_date.isoformat() if payload.to_date else None,
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

    row = fetch_toss_order_import_run(db, run_id=result.run_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="생성된 Toss 주문 가져오기 실행 이력을 찾을 수 없습니다.",
        )
    return row_to_dict(row)


@router.get("/order-imports", response_model=list[TossOrderImportRunResponse])
def list_toss_order_imports(
    db: Db,
    account_seq: Annotated[str | None, Query(min_length=1)] = None,
) -> list[dict[str, object]]:
    normalized_account_seq = (
        normalize_account_seq(account_seq) if account_seq is not None else None
    )
    rows = fetch_toss_order_import_runs(db, account_seq=normalized_account_seq)
    return [row_to_dict(row) for row in rows]


@router.get("/orders", response_model=list[TossOrderResponse])
def list_toss_orders(
    db: Db,
    account_seq: AccountSeq,
    symbol: str | None = None,
    order_status: str | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[dict[str, object]]:
    _validate_date_range(from_date, to_date)
    rows = fetch_toss_orders(
        db,
        account_seq=normalize_account_seq(account_seq),
        symbol=_normalize_optional_uppercase(symbol),
        order_status=_normalize_optional_uppercase(order_status),
        from_date=from_date.isoformat() if from_date else None,
        to_date=to_date.isoformat() if to_date else None,
    )
    return [row_to_dict(row) for row in rows]


@router.get("/accounts", response_model=list[TossAccountResponse])
async def list_toss_accounts(request: Request) -> list[TossAccountResponse]:
    try:
        provider = _provider(request)
        accounts = await _accounts_cache(request).get_or_fetch(provider.fetch_accounts)
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

    return [account_response(account) for account in accounts]


@router.get("/holdings", response_model=list[TossHoldingResponse])
async def list_toss_holdings(
    request: Request,
    account_seq: AccountSeq,
) -> list[TossHoldingResponse]:
    normalized_account_seq = normalize_account_seq(account_seq)
    try:
        holdings = await _provider(request).fetch_holdings(normalized_account_seq)
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

    return [holding_response(holding) for holding in holdings]


@router.get("/candles", response_model=list[TossCandleResponse])
async def list_toss_candles(
    request: Request,
    symbol: Annotated[str, Query(min_length=1)],
    interval: Annotated[str, Query(min_length=1)] = "1d",
    limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
) -> list[TossCandleResponse]:
    normalized_symbol = _normalize_optional_uppercase(symbol)
    if normalized_symbol is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CANDLE_SYMBOL_REQUIRED_MESSAGE,
        )

    try:
        candles = await _market_data_provider(request).fetch_candles(
            normalized_symbol,
            interval=interval,
            limit=limit,
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

    return [candle_response(candle) for candle in candles]


@router.get("/chart-marker-memos", response_model=list[ChartMarkerMemoResponse])
def list_chart_marker_memos(
    db: Db,
    account_seq: AccountSeq,
    symbol: Annotated[str, Query(min_length=1)],
) -> list[dict[str, object]]:
    normalized_symbol = _normalize_optional_uppercase(symbol)
    if normalized_symbol is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CANDLE_SYMBOL_REQUIRED_MESSAGE,
        )
    rows = fetch_chart_marker_memos(
        db,
        account_seq=normalize_account_seq(account_seq),
        symbol=normalized_symbol,
    )
    return [row_to_dict(row) for row in rows]


@router.post("/chart-marker-memos", response_model=ChartMarkerMemoResponse)
def upsert_chart_marker_memo_endpoint(
    payload: ChartMarkerMemoUpsert,
    db: Db,
) -> dict[str, object]:
    normalized_symbol = _normalize_optional_uppercase(payload.symbol)
    if normalized_symbol is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CANDLE_SYMBOL_REQUIRED_MESSAGE,
        )
    row = upsert_chart_marker_memo(
        db,
        account_seq=normalize_account_seq(payload.account_seq),
        symbol=normalized_symbol,
        marker_key=_normalize_marker_key(payload.marker_key),
        memo=payload.memo.strip(),
    )
    return row_to_dict(row)


@router.delete("/chart-marker-memos", status_code=status.HTTP_204_NO_CONTENT)
def delete_chart_marker_memo_endpoint(
    db: Db,
    account_seq: AccountSeq,
    symbol: Annotated[str, Query(min_length=1)],
    marker_key: Annotated[str, Query(min_length=1, max_length=200)],
) -> None:
    normalized_symbol = _normalize_optional_uppercase(symbol)
    if normalized_symbol is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CANDLE_SYMBOL_REQUIRED_MESSAGE,
        )
    delete_chart_marker_memo(
        db,
        account_seq=normalize_account_seq(account_seq),
        symbol=normalized_symbol,
        marker_key=_normalize_marker_key(marker_key),
    )


@router.get("/buying-power", response_model=list[TossBuyingPowerResponse])
async def list_toss_buying_power(
    request: Request,
    account_seq: AccountSeq,
) -> list[TossBuyingPowerResponse]:
    normalized_account_seq = normalize_account_seq(account_seq)
    provider = _provider(request)
    try:
        rows = [
            await provider.fetch_buying_power(normalized_account_seq, "KRW"),
            await provider.fetch_buying_power(normalized_account_seq, "USD"),
        ]
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

    return [buying_power_response(row) for row in rows]

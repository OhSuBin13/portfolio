import sqlite3
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.api import get_db, row_to_dict
from portfolio_app.models import (
    Currency,
    TossMarket,
    TossOrderImportCreate,
    TossOrderImportRunResponse,
    TossOrderResponse,
)
from portfolio_app.repositories import (
    fetch_toss_order_import_run,
    fetch_toss_order_import_runs,
    fetch_toss_orders,
)
from portfolio_app.services.toss_order_imports import import_toss_orders
from portfolio_app.services.toss_portfolio import (
    TossAccount,
    TossAccountsCache,
    TossBrokerageProvider,
    TossBuyingPower,
    TossHolding,
)

router = APIRouter(prefix="/api/toss", tags=["toss"])
AccountSeq = Annotated[str, Query(min_length=1)]
Db = Annotated[sqlite3.Connection, Depends(get_db)]
ACCOUNT_SEQ_REQUIRED_MESSAGE = "Toss 계좌 식별자를 입력해 주세요."


class TossAccountResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    account_seq: str
    account_no: str
    account_type: str
    display_name: str


class TossHoldingResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    symbol: str
    name: str
    market: TossMarket
    currency: Currency
    quantity: float = Field(ge=0, allow_inf_nan=False)
    average_purchase_price: float = Field(ge=0, allow_inf_nan=False)
    last_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    market_value: float = Field(ge=0, allow_inf_nan=False)


class TossBuyingPowerResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    currency: Currency
    cash_buying_power: float = Field(ge=0, allow_inf_nan=False)


def toss_http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Toss 요청 실패: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
    return f"Toss 요청 실패: {exc.__class__.__name__}"


def normalize_account_seq(account_seq: str) -> str:
    normalized = account_seq.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ACCOUNT_SEQ_REQUIRED_MESSAGE,
        )
    return normalized


def _provider(request: Request) -> TossBrokerageProvider:
    settings = request.app.state.settings
    return TossBrokerageProvider(
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


def _account_response(account: TossAccount) -> TossAccountResponse:
    return TossAccountResponse(
        account_seq=account.account_seq,
        account_no=account.account_no,
        account_type=account.account_type,
        display_name=account.display_name,
    )


def _holding_response(holding: TossHolding) -> TossHoldingResponse:
    return TossHoldingResponse(
        symbol=holding.symbol,
        name=holding.name,
        market=holding.market,
        currency=holding.currency,
        quantity=holding.quantity,
        average_purchase_price=holding.average_purchase_price,
        last_price=holding.last_price,
        market_value=holding.market_value,
    )


def _buying_power_response(row: TossBuyingPower) -> TossBuyingPowerResponse:
    return TossBuyingPowerResponse(
        currency=row.currency,
        cash_buying_power=row.cash_buying_power,
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

    return [_account_response(account) for account in accounts]


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

    return [_holding_response(holding) for holding in holdings]


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

    return [_buying_power_response(row) for row in rows]

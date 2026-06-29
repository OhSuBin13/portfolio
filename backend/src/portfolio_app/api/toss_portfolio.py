from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.models import Currency, TossMarket
from portfolio_app.services.toss_portfolio import (
    TossAccount,
    TossAccountsCache,
    TossBrokerageProvider,
    TossHolding,
)

router = APIRouter(prefix="/api/toss", tags=["toss"])
AccountSeq = Annotated[str, Query(min_length=1)]
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

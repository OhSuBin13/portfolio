import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app import repositories
from portfolio_app.api import created_row, get_db, require_allowed, require_non_empty, row_to_dict
from portfolio_app.models import TRANSACTION_TYPES, TransactionResponse
from portfolio_app.services.transactions import apply_transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_on: date
    type: str
    account_id: int
    asset_id: int
    quantity: float | None = None
    amount: float
    currency: str
    memo: str = ""
    fx_rate_to_krw: float | None = None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TransactionResponse)
def create_transaction_endpoint(payload: TransactionCreate, db: Db) -> dict[str, object]:
    transaction_type = require_allowed(
        payload.type,
        TRANSACTION_TYPES,
        "지원하지 않는 거래 유형입니다.",
    )
    currency = require_non_empty(payload.currency, "통화를 입력해 주세요.").upper()

    try:
        transaction_id = apply_transaction(
            db,
            occurred_on=payload.occurred_on.isoformat(),
            type=transaction_type,
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            quantity=payload.quantity,
            amount=payload.amount,
            currency=currency,
            memo=payload.memo,
            fx_rate_to_krw=payload.fx_rate_to_krw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="거래 정보를 저장할 수 없습니다.",
        ) from exc

    return created_row(db, "transactions", transaction_id)


@router.get("", response_model=list[TransactionResponse])
def list_transactions(db: Db) -> list[dict[str, object]]:
    return [row_to_dict(row) for row in repositories.fetch_transactions(db)]

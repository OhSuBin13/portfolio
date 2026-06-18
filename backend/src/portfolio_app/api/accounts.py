import sqlite3
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import (
    created_row,
    get_db,
    require_allowed,
    require_non_empty,
    row_to_dict,
)
from portfolio_app.repositories import (
    create_account,
    fetch_account,
    fetch_accounts,
)
from portfolio_app.repositories import (
    update_account as update_account_record,
)

ACCOUNT_TYPES = {"cash", "savings", "brokerage", "debt"}

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str


@dataclass(frozen=True)
class ValidatedAccountPayload:
    name: str
    type: str


def validate_account_payload(payload: AccountCreate) -> ValidatedAccountPayload:
    name = require_non_empty(payload.name, "계좌 이름을 입력해 주세요.")
    account_type = require_allowed(payload.type, ACCOUNT_TYPES, "지원하지 않는 계좌 유형입니다.")
    return ValidatedAccountPayload(name=name, type=account_type)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account_endpoint(payload: AccountCreate, db: Db) -> dict[str, object]:
    account = validate_account_payload(payload)

    try:
        account_id = create_account(db, name=account.name, type=account.type)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="계좌 정보를 저장할 수 없습니다.",
        ) from exc

    return created_row(db, "accounts", account_id)


@router.get("")
def list_accounts(db: Db) -> list[dict[str, object]]:
    return [row_to_dict(row) for row in fetch_accounts(db)]


@router.get("/{account_id}")
def get_account(account_id: int, db: Db) -> dict[str, object]:
    row = fetch_account(db, account_id=account_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다."
        )
    return row_to_dict(row)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Db) -> None:
    cursor = db.execute("delete from accounts where id = ?", (account_id,))
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다."
        )
    db.commit()


@router.put("/{account_id}")
def update_account(account_id: int, payload: AccountCreate, db: Db) -> dict[str, object]:
    account = validate_account_payload(payload)

    updated = update_account_record(
        db,
        account_id=account_id,
        name=account.name,
        type=account.type,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다."
        )
    return created_row(db, "accounts", account_id)

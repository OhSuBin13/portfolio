import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import created_row, get_db, require_allowed, require_non_empty, row_to_dict
from portfolio_app.repositories import create_account

ACCOUNT_TYPES = {"cash", "savings", "brokerage", "debt"}

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account_endpoint(payload: AccountCreate, db: Db) -> dict[str, object]:
    name = require_non_empty(payload.name, "계좌 이름을 입력해 주세요.")
    account_type = require_allowed(payload.type, ACCOUNT_TYPES, "지원하지 않는 계좌 유형입니다.")

    try:
        account_id = create_account(db, name=name, type=account_type)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="계좌 정보를 저장할 수 없습니다.",
        ) from exc

    return created_row(db, "accounts", account_id)


@router.get("")
def list_accounts(db: Db) -> list[dict[str, object]]:
    rows = db.execute("select * from accounts order by id").fetchall()
    return [row_to_dict(row) for row in rows]


@router.get("/{account_id}")
def get_account(account_id: int, db: Db) -> dict[str, object]:
    row = db.execute("select * from accounts where id = ?", (account_id,)).fetchone()
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
    name = require_non_empty(payload.name, "계좌 이름을 입력해 주세요.")
    account_type = require_allowed(payload.type, ACCOUNT_TYPES, "지원하지 않는 계좌 유형입니다.")

    cursor = db.execute(
        """update accounts set name = ?, type = ?,
        updated_at = current_timestamp where id = ?""",
        (name, account_type, account_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다."
        )
    db.commit()
    return created_row(db, "accounts", account_id)

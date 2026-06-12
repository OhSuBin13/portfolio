import math
import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.api import get_db
from portfolio_app.repositories import create_account, create_asset, get_holding
from portfolio_app.services.backups import create_recorded_backup
from portfolio_app.services.imports import ASSET_TYPE_MAP, ImportPreview, parse_portfolio_csv
from portfolio_app.services.transactions import apply_transaction

router = APIRouter(prefix="/api/imports", tags=["imports"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]

ASSET_TYPES = set(ASSET_TYPE_MAP.values())
ACCOUNT_TYPE_BY_ASSET_TYPE = {
    "cash": "cash",
    "savings": "savings",
    "stock_etf": "brokerage",
    "crypto": "crypto_wallet",
    "debt": "debt",
}


class ImportRowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int
    asset_type: str
    name: str
    quantity: float
    price: float | None = None
    average_cost: float | None = None
    fx_rate_to_krw: float | None = None
    value_krw: float
    message: str = ""


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapped_rows: list[ImportRowPayload] = Field(min_length=1)
    occurred_on: date


def _is_finite_non_negative(value: float) -> bool:
    return math.isfinite(value) and value >= 0


def _row_currency(row: ImportRowPayload) -> str:
    if row.fx_rate_to_krw is not None and row.fx_rate_to_krw != 1:
        return "USD"
    return "KRW"


def _initial_quantity(row: ImportRowPayload, currency: str) -> float:
    if row.asset_type in {"cash", "savings", "debt"}:
        if currency == "KRW":
            return row.value_krw
        if row.price is not None:
            return row.price
        if row.fx_rate_to_krw:
            return row.value_krw / row.fx_rate_to_krw
        return row.value_krw
    return row.quantity


def _initial_average_cost(row: ImportRowPayload) -> float | None:
    if row.asset_type not in {"stock_etf", "crypto"}:
        return None
    if row.average_cost is not None:
        return row.average_cost
    return row.price


def _market_for(currency: str) -> str:
    if currency == "KRW":
        return "KR"
    return currency


def _reject_existing_or_duplicate_rows(
    db: sqlite3.Connection,
    rows: list[ImportRowPayload],
) -> None:
    seen_names: set[str] = set()
    for row in rows:
        name = row.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{row.row_number}행의 이름을 입력해 주세요.",
            )
        if row.asset_type not in ASSET_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{row.row_number}행의 자산 종류를 지원하지 않습니다.",
            )
        if name in seen_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"중복된 가져오기 행입니다: {name}",
            )
        seen_names.add(name)
        if not _is_finite_non_negative(row.quantity) or not _is_finite_non_negative(row.value_krw):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{row.row_number}행의 숫자 값이 올바르지 않습니다.",
            )
        if row.fx_rate_to_krw is not None and row.fx_rate_to_krw <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{row.row_number}행의 환율이 올바르지 않습니다.",
            )
        account = db.execute("select id from accounts where name = ?", (name,)).fetchone()
        if account is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"이미 존재하는 계좌입니다: {name}",
            )
        asset = db.execute("select id from assets where name = ?", (name,)).fetchone()
        if asset is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"이미 존재하는 자산입니다: {name}",
            )


def _update_average_cost(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    average_cost: float | None,
) -> None:
    if average_cost is None:
        return
    db.execute(
        """
        update holdings
        set average_cost = ?, updated_at = current_timestamp
        where account_id = ? and asset_id = ?
        """,
        (average_cost, account_id, asset_id),
    )
    db.commit()


@router.post("/preview")
async def preview_import(file: Annotated[UploadFile, File()]) -> ImportPreview:
    try:
        content = await file.read()
        csv_text = content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV 파일을 읽을 수 없습니다.",
        ) from exc

    return parse_portfolio_csv(csv_text)


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
def confirm_import(
    payload: ImportConfirmRequest,
    request: Request,
    db: Db,
) -> dict[str, object]:
    _reject_existing_or_duplicate_rows(db, payload.mapped_rows)
    settings = request.app.state.settings

    try:
        backup = create_recorded_backup(
            db,
            db_path=settings.database_path,
            backup_dir=settings.backup_dir,
            reason="pre-import",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"가져오기 전 백업을 생성할 수 없습니다. {exc}",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="가져오기 전 백업 정보를 저장할 수 없습니다.",
        ) from exc

    created_accounts = 0
    created_assets = 0
    created_holdings = 0
    created_transactions = 0

    try:
        for row in payload.mapped_rows:
            name = row.name.strip()
            currency = _row_currency(row)
            account_id = create_account(
                db,
                name=name,
                type=ACCOUNT_TYPE_BY_ASSET_TYPE[row.asset_type],
                currency=currency,
            )
            created_accounts += 1

            asset_id = create_asset(
                db,
                symbol=None,
                name=name,
                type=row.asset_type,
                currency=currency,
                market=_market_for(currency),
            )
            created_assets += 1

            try:
                get_holding(db, account_id=account_id, asset_id=asset_id)
            except ValueError:
                pass
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"이미 존재하는 보유자산입니다: {name}",
                )

            quantity = _initial_quantity(row, currency)
            transaction_id = apply_transaction(
                db,
                occurred_on=payload.occurred_on.isoformat(),
                type="adjustment",
                account_id=account_id,
                asset_id=asset_id,
                quantity=None,
                amount=quantity,
                currency=currency,
                fx_rate_to_krw=row.fx_rate_to_krw,
                memo=f"CSV 가져오기: {name}",
            )
            created_transactions += 1
            if transaction_id:
                created_holdings += 1
            _update_average_cost(
                db,
                account_id=account_id,
                asset_id=asset_id,
                average_cost=_initial_average_cost(row),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="가져오기 데이터를 저장할 수 없습니다.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "created_accounts": created_accounts,
        "created_assets": created_assets,
        "created_holdings": created_holdings,
        "created_transactions": created_transactions,
        "backup_path": backup["path"],
    }

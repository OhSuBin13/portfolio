import math
import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.api import get_db
from portfolio_app.services.backups import create_recorded_backup
from portfolio_app.services.imports import ASSET_TYPE_MAP, ImportPreview, parse_portfolio_csv

router = APIRouter(prefix="/api/imports", tags=["imports"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]

ASSET_TYPES = set(ASSET_TYPE_MAP.values())
MARKET_ASSET_TYPES = {"stock_etf", "crypto"}
ACCOUNT_TYPE_BY_ASSET_TYPE = {
    "cash": "cash",
    "savings": "savings",
    "stock_etf": "brokerage",
    "crypto": "crypto_wallet",
    "debt": "debt",
}


class ImportRowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1)
    asset_type: str
    name: str
    symbol: str | None = None
    quantity: float = Field(allow_inf_nan=False)
    price: float | None = Field(default=None, allow_inf_nan=False)
    average_cost: float | None = Field(default=None, allow_inf_nan=False)
    fx_rate_to_krw: float | None = Field(default=None, allow_inf_nan=False)
    value_krw: float = Field(allow_inf_nan=False)
    message: str = ""


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapped_rows: list[ImportRowPayload] = Field(min_length=1)
    occurred_on: date


def _is_finite_non_negative(value: float) -> bool:
    return math.isfinite(value) and value >= 0


def _is_finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip().upper()
    return normalized or None


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
    if row.asset_type not in MARKET_ASSET_TYPES:
        return None
    if row.average_cost is not None:
        return row.average_cost
    return row.price


def _manual_price_krw(row: ImportRowPayload) -> float | None:
    if row.asset_type not in MARKET_ASSET_TYPES:
        return None
    if row.quantity > 0:
        return row.value_krw / row.quantity
    if row.price is not None and row.fx_rate_to_krw is not None:
        return row.price * row.fx_rate_to_krw
    return row.price


def _market_for(asset_type: str, currency: str) -> str:
    if asset_type == "crypto":
        return "CRYPTO"
    if currency == "KRW":
        return "KR"
    if currency == "USD":
        return "US"
    return currency


def _raise_bad_row(row: ImportRowPayload, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{row.row_number}행의 {message}",
    )


def _validate_rows(
    db: sqlite3.Connection,
    rows: list[ImportRowPayload],
) -> None:
    seen_names: set[str] = set()
    for row in rows:
        name = row.name.strip()
        if not name:
            _raise_bad_row(row, "이름을 입력해 주세요.")
        if row.asset_type not in ASSET_TYPES:
            _raise_bad_row(row, "자산 종류를 지원하지 않습니다.")
        if name in seen_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"중복된 가져오기 행입니다: {name}",
            )
        seen_names.add(name)
        if not _is_finite_non_negative(row.quantity) or not _is_finite_non_negative(row.value_krw):
            _raise_bad_row(row, "숫자 값이 올바르지 않습니다.")
        if row.price is not None and not _is_finite_non_negative(row.price):
            _raise_bad_row(row, "숫자 값이 올바르지 않습니다.")
        if row.average_cost is not None and not _is_finite_non_negative(row.average_cost):
            _raise_bad_row(row, "숫자 값이 올바르지 않습니다.")
        if row.fx_rate_to_krw is not None and not _is_finite_positive(row.fx_rate_to_krw):
            _raise_bad_row(row, "환율이 올바르지 않습니다.")
        if row.asset_type in MARKET_ASSET_TYPES and row.value_krw > 0 and row.quantity <= 0:
            _raise_bad_row(row, "수량이 0보다 커야 합니다.")

        quantity = _initial_quantity(row, _row_currency(row))
        if not _is_finite_non_negative(quantity):
            _raise_bad_row(row, "조정 수량이 올바르지 않습니다.")
        manual_price_krw = _manual_price_krw(row)
        if manual_price_krw is not None and not _is_finite_non_negative(manual_price_krw):
            _raise_bad_row(row, "평가 가격이 올바르지 않습니다.")

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


def _insert_account(
    db: sqlite3.Connection,
    *,
    name: str,
    account_type: str,
    currency: str,
) -> int:
    cursor = db.execute(
        """
        insert into accounts(name, type, currency)
        values (?, ?, ?)
        """,
        (name, account_type, currency),
    )
    return int(cursor.lastrowid)


def _insert_asset(
    db: sqlite3.Connection,
    *,
    symbol: str | None,
    name: str,
    asset_type: str,
    currency: str,
    market: str,
    manual_price_krw: float | None,
) -> int:
    cursor = db.execute(
        """
        insert into assets(symbol, name, type, currency, market, manual_price_krw)
        values (?, ?, ?, ?, ?, ?)
        """,
        (symbol, name, asset_type, currency, market, manual_price_krw),
    )
    return int(cursor.lastrowid)


def _upsert_import_holding(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    average_cost: float | None,
) -> None:
    db.execute(
        """
        insert into holdings(account_id, asset_id, quantity, average_cost)
        values (?, ?, ?, ?)
        on conflict(account_id, asset_id)
        do update set quantity = excluded.quantity,
                      average_cost = excluded.average_cost,
                      updated_at = current_timestamp
        """,
        (account_id, asset_id, quantity, average_cost),
    )


def _insert_adjustment_transaction(
    db: sqlite3.Connection,
    *,
    occurred_on: str,
    account_id: int,
    asset_id: int,
    amount: float,
    currency: str,
    fx_rate_to_krw: float | None,
    memo: str,
) -> int:
    cursor = db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, quantity, amount, currency,
          fx_rate_to_krw, memo
        )
        values (?, 'adjustment', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            occurred_on,
            account_id,
            asset_id,
            None,
            amount,
            currency,
            fx_rate_to_krw,
            memo,
        ),
    )
    return int(cursor.lastrowid)


@router.post("/preview")
async def preview_import(file: Annotated[UploadFile, File()]) -> ImportPreview:
    try:
        content = await file.read()
        csv_text = content.decode("utf-8-sig")
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
    _validate_rows(db, payload.mapped_rows)
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
        with db:
            for row in payload.mapped_rows:
                name = row.name.strip()
                currency = _row_currency(row)
                account_id = _insert_account(
                    db,
                    name=name,
                    account_type=ACCOUNT_TYPE_BY_ASSET_TYPE[row.asset_type],
                    currency=currency,
                )
                created_accounts += 1

                asset_id = _insert_asset(
                    db,
                    symbol=_normalize_symbol(row.symbol),
                    name=name,
                    asset_type=row.asset_type,
                    currency=currency,
                    market=_market_for(row.asset_type, currency),
                    manual_price_krw=_manual_price_krw(row),
                )
                created_assets += 1

                quantity = _initial_quantity(row, currency)
                _upsert_import_holding(
                    db,
                    account_id=account_id,
                    asset_id=asset_id,
                    quantity=quantity,
                    average_cost=_initial_average_cost(row),
                )
                created_holdings += 1

                _insert_adjustment_transaction(
                    db,
                    occurred_on=payload.occurred_on.isoformat(),
                    account_id=account_id,
                    asset_id=asset_id,
                    amount=quantity,
                    currency=currency,
                    fx_rate_to_krw=row.fx_rate_to_krw,
                    memo=f"CSV 가져오기: {name}",
                )
                created_transactions += 1
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

import math
import sqlite3
from datetime import date

from portfolio_app.repositories import upsert_holding

INCREASE_TYPES = {"deposit", "interest", "dividend"}
DECREASE_TYPES = {"withdrawal", "fee", "debt_payment"}
NORMAL_TYPES = {"buy", "sell"} | INCREASE_TYPES | DECREASE_TYPES
SUPPORTED_TYPES = NORMAL_TYPES | {"adjustment"}


def _current_holding(
    db: sqlite3.Connection,
    account_id: int,
    asset_id: int,
) -> tuple[float, float | None]:
    row = db.execute(
        "select quantity, average_cost from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        return 0.0, None
    return float(row["quantity"]), row["average_cost"]


def _asset_currency(db: sqlite3.Connection, asset_id: int) -> str:
    row = db.execute("select currency from assets where id = ?", (asset_id,)).fetchone()
    if row is None:
        return "KRW"
    return str(row["currency"])


def _is_finite_number(value: float | None) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(value)
    except TypeError:
        return False


def _validate_positive_amount(amount: float) -> None:
    if not _is_finite_number(amount) or amount <= 0:
        raise ValueError("거래 금액은 0보다 커야 합니다.")


def _validate_adjustment_amount(amount: float) -> None:
    if not _is_finite_number(amount) or amount < 0:
        raise ValueError("조정 수량은 0 이상이어야 합니다.")


def apply_transaction(
    db: sqlite3.Connection,
    *,
    occurred_on: str,
    type: str,
    account_id: int,
    asset_id: int,
    quantity: float | None,
    amount: float,
    currency: str,
    memo: str,
    fx_rate_to_krw: float | None = None,
) -> int:
    if type not in SUPPORTED_TYPES:
        raise ValueError("지원하지 않는 거래 유형입니다.")

    if type == "adjustment":
        _validate_adjustment_amount(amount)
    else:
        _validate_positive_amount(amount)

    with db:
        current_quantity, current_average = _current_holding(db, account_id, asset_id)

        if type == "buy":
            if not _is_finite_number(quantity) or quantity <= 0:
                raise ValueError("매수 수량은 0보다 커야 합니다.")
            new_quantity = current_quantity + quantity
            existing_cost = current_quantity * (current_average or 0)
            new_average = (existing_cost + amount) / new_quantity
            upsert_holding(
                db,
                account_id=account_id,
                asset_id=asset_id,
                quantity=new_quantity,
                average_cost=new_average,
                commit=False,
            )
        elif type == "sell":
            if not _is_finite_number(quantity) or quantity <= 0:
                raise ValueError("매도 수량은 0보다 커야 합니다.")
            if quantity > current_quantity:
                raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
            upsert_holding(
                db,
                account_id=account_id,
                asset_id=asset_id,
                quantity=current_quantity - quantity,
                average_cost=current_average,
                commit=False,
            )
        elif type in INCREASE_TYPES:
            upsert_holding(
                db,
                account_id=account_id,
                asset_id=asset_id,
                quantity=current_quantity + amount,
                average_cost=current_average,
                commit=False,
            )
        elif type in DECREASE_TYPES:
            if type == "debt_payment" and amount > current_quantity:
                raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
            next_quantity = current_quantity - amount
            if next_quantity < 0 and type != "debt_payment":
                raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
            upsert_holding(
                db,
                account_id=account_id,
                asset_id=asset_id,
                quantity=next_quantity,
                average_cost=current_average,
                commit=False,
            )
        else:
            upsert_holding(
                db,
                account_id=account_id,
                asset_id=asset_id,
                quantity=amount,
                average_cost=current_average,
                commit=False,
            )

        cursor = db.execute(
            """
            insert into transactions(
              occurred_on, type, account_id, asset_id, quantity, amount, currency,
              fx_rate_to_krw, memo
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_on,
                type,
                account_id,
                asset_id,
                quantity,
                amount,
                currency,
                fx_rate_to_krw,
                memo,
            ),
        )

    return int(cursor.lastrowid)


def edit_holding_balance(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    memo: str,
    occurred_on: str | None = None,
    currency: str | None = None,
) -> int:
    return apply_transaction(
        db,
        occurred_on=occurred_on or date.today().isoformat(),
        type="adjustment",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=quantity,
        currency=currency if currency is not None else _asset_currency(db, asset_id),
        memo=memo,
    )

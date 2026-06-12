import sqlite3

from portfolio_app.repositories import upsert_holding


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
    current_quantity, current_average = _current_holding(db, account_id, asset_id)

    if type == "buy":
        if quantity is None or quantity <= 0:
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
        )
    elif type == "sell":
        if quantity is None or quantity <= 0:
            raise ValueError("매도 수량은 0보다 커야 합니다.")
        if quantity > current_quantity:
            raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=current_quantity - quantity,
            average_cost=current_average,
        )
    elif type in {"deposit", "interest", "dividend"}:
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=current_quantity + amount,
            average_cost=current_average,
        )
    elif type in {"withdrawal", "fee", "debt_payment"}:
        next_quantity = current_quantity - amount
        if next_quantity < 0 and type != "debt_payment":
            raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=next_quantity,
            average_cost=current_average,
        )
    elif type == "adjustment":
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=amount,
            average_cost=current_average,
        )
    else:
        raise ValueError("지원하지 않는 거래 유형입니다.")

    cursor = db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, quantity, amount, currency, fx_rate_to_krw, memo
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (occurred_on, type, account_id, asset_id, quantity, amount, currency, fx_rate_to_krw, memo),
    )
    db.commit()
    return int(cursor.lastrowid)


def edit_holding_balance(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    memo: str,
) -> int:
    return apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="adjustment",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=quantity,
        currency="KRW",
        memo=memo,
    )

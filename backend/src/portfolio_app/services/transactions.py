import math
import sqlite3
from dataclasses import dataclass
from datetime import date

from portfolio_app.models import TRANSACTION_TYPES
from portfolio_app.repositories import (
    get_asset_currency,
    get_asset_type,
    get_current_holding,
    insert_transaction,
    upsert_holding,
)

INCREASE_TYPES = {"deposit", "interest", "dividend"}
DECREASE_TYPES = {"withdrawal", "fee", "debt_payment"}
CASHFLOW_TYPES = {"deposit", "withdrawal", "dividend", "interest", "fee"}
CASH_LIKE_ASSET_TYPES = {"cash", "savings"}
MARKET_ASSET_TYPES = {"stock_etf"}
QUANTITY_TYPES = {"buy", "sell"}


@dataclass(frozen=True)
class TransactionCommand:
    occurred_on: str
    type: str
    account_id: int
    asset_id: int
    quantity: float | None
    amount: float
    currency: str
    memo: str
    fx_rate_to_krw: float | None = None


@dataclass(frozen=True)
class HoldingEffect:
    quantity: float
    average_cost: float | None


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


def _validate_fx_rate(fx_rate_to_krw: float | None) -> None:
    if fx_rate_to_krw is not None and (
        not _is_finite_number(fx_rate_to_krw) or fx_rate_to_krw <= 0
    ):
        raise ValueError("환율은 0보다 커야 합니다.")


def _validate_foreign_asset_fx_rate(
    command: TransactionCommand,
    *,
    asset_currency: str,
) -> None:
    normalized_asset_currency = asset_currency.strip().upper()
    if command.currency.strip().upper() != normalized_asset_currency:
        raise ValueError("거래 통화는 자산 통화와 같아야 합니다.")
    if normalized_asset_currency != "KRW" and command.fx_rate_to_krw is None:
        raise ValueError("외화 거래에는 환율을 입력해 주세요.")


def _positive_quantity(quantity: float | None, message: str) -> float:
    if not _is_finite_number(quantity) or quantity <= 0:
        raise ValueError(message)
    return float(quantity)


def _validate_transaction_command(command: TransactionCommand) -> None:
    if command.type not in TRANSACTION_TYPES:
        raise ValueError("지원하지 않는 거래 유형입니다.")

    _validate_fx_rate(command.fx_rate_to_krw)

    if command.type not in QUANTITY_TYPES and command.quantity is not None:
        raise ValueError("매수와 매도 외 거래에는 수량을 입력할 수 없습니다.")

    if command.type == "adjustment":
        _validate_adjustment_amount(command.amount)
    else:
        _validate_positive_amount(command.amount)


def _validate_asset_type_for_transaction(
    db: sqlite3.Connection,
    *,
    transaction_type: str,
    asset_id: int,
) -> None:
    asset_type = get_asset_type(db, asset_id=asset_id)
    if transaction_type in CASHFLOW_TYPES and asset_type not in CASH_LIKE_ASSET_TYPES:
        raise ValueError("입출금, 배당, 이자, 수수료는 현금성 자산에만 기록할 수 있습니다.")
    if transaction_type == "debt_payment" and asset_type != "debt":
        raise ValueError("부채 상환은 부채 자산에만 기록할 수 있습니다.")
    if transaction_type in {"buy", "sell"} and asset_type not in MARKET_ASSET_TYPES:
        raise ValueError("매수와 매도는 시장성 자산에만 기록할 수 있습니다.")


def calculate_holding_effect(
    command: TransactionCommand,
    *,
    current_quantity: float,
    current_average: float | None,
) -> HoldingEffect:
    _validate_transaction_command(command)

    if command.type == "buy":
        quantity = _positive_quantity(command.quantity, "매수 수량은 0보다 커야 합니다.")
        new_quantity = current_quantity + quantity
        existing_cost = current_quantity * (current_average or 0)
        return HoldingEffect(
            quantity=new_quantity,
            average_cost=(existing_cost + command.amount) / new_quantity,
        )

    if command.type == "sell":
        quantity = _positive_quantity(command.quantity, "매도 수량은 0보다 커야 합니다.")
        if quantity > current_quantity:
            raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
        return HoldingEffect(
            quantity=current_quantity - quantity,
            average_cost=current_average,
        )

    if command.type in INCREASE_TYPES:
        return HoldingEffect(
            quantity=current_quantity + command.amount,
            average_cost=current_average,
        )

    if command.type in DECREASE_TYPES:
        if command.type == "debt_payment" and command.amount > current_quantity:
            raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
        next_quantity = current_quantity - command.amount
        if next_quantity < 0 and command.type != "debt_payment":
            raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
        return HoldingEffect(quantity=next_quantity, average_cost=current_average)

    return HoldingEffect(quantity=command.amount, average_cost=current_average)


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
    command = TransactionCommand(
        occurred_on=occurred_on,
        type=type,
        account_id=account_id,
        asset_id=asset_id,
        quantity=quantity,
        amount=amount,
        currency=currency.strip().upper(),
        memo=memo,
        fx_rate_to_krw=fx_rate_to_krw,
    )

    _validate_transaction_command(command)
    _validate_asset_type_for_transaction(
        db,
        transaction_type=command.type,
        asset_id=command.asset_id,
    )
    _validate_foreign_asset_fx_rate(
        command,
        asset_currency=get_asset_currency(db, asset_id=command.asset_id),
    )

    with db:
        current_quantity, current_average = get_current_holding(
            db,
            account_id=command.account_id,
            asset_id=command.asset_id,
        )
        effect = calculate_holding_effect(
            command,
            current_quantity=current_quantity,
            current_average=current_average,
        )
        upsert_holding(
            db,
            account_id=command.account_id,
            asset_id=command.asset_id,
            quantity=effect.quantity,
            average_cost=effect.average_cost,
            commit=False,
        )
        transaction_id = insert_transaction(
            db,
            occurred_on=command.occurred_on,
            type=command.type,
            account_id=command.account_id,
            asset_id=command.asset_id,
            quantity=command.quantity,
            amount=command.amount,
            currency=command.currency,
            fx_rate_to_krw=command.fx_rate_to_krw,
            memo=command.memo,
            commit=False,
        )

    return transaction_id


def edit_holding_balance(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    memo: str,
    occurred_on: str | None = None,
    currency: str | None = None,
    fx_rate_to_krw: float | None = None,
) -> int:
    return apply_transaction(
        db,
        occurred_on=occurred_on or date.today().isoformat(),
        type="adjustment",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=quantity,
        currency=currency if currency is not None else get_asset_currency(db, asset_id=asset_id),
        memo=memo,
        fx_rate_to_krw=fx_rate_to_krw,
    )

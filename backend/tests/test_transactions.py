import sqlite3

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, create_asset, get_holding
from portfolio_app.services.transactions import apply_transaction, edit_holding_balance


def setup_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def count_transactions(db, transaction_type):
    row = db.execute(
        "select count(*) from transactions where type = ?",
        (transaction_type,),
    ).fetchone()
    return row[0]


def test_buy_transaction_increases_holding_quantity(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(
        db,
        symbol="005930.KS",
        name="삼성전자",
        type="stock_etf",
        currency="KRW",
        market="KR",
    )

    tx_id = apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="buy",
        account_id=account_id,
        asset_id=asset_id,
        quantity=10,
        amount=700_000,
        currency="KRW",
        memo="첫 매수",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert tx_id > 0
    assert holding["quantity"] == 10
    assert holding["average_cost"] == 70_000


def test_sell_more_than_holding_is_rejected(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(
        db,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        type="stock_etf",
        currency="USD",
        market="US",
    )

    try:
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="sell",
            account_id=account_id,
            asset_id=asset_id,
            quantity=1,
            amount=500,
            currency="USD",
            memo="보유량 초과",
        )
    except ValueError as exc:
        assert "보유 수량" in str(exc)
    else:
        raise AssertionError("expected ValueError")


@pytest.mark.parametrize(
    "transaction_type",
    ["deposit", "withdrawal", "dividend", "interest", "fee"],
)
def test_cashflow_transaction_on_stock_asset_is_rejected_without_changes(
    tmp_path,
    transaction_type,
):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(
        db,
        symbol="005930.KS",
        name="삼성전자",
        type="stock_etf",
        currency="KRW",
        market="KR",
    )
    apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="buy",
        account_id=account_id,
        asset_id=asset_id,
        quantity=10,
        amount=700_000,
        currency="KRW",
        memo="초기 매수",
    )

    with pytest.raises(ValueError, match="현금성 자산"):
        apply_transaction(
            db,
            occurred_on="2026-06-13",
            type=transaction_type,
            account_id=account_id,
            asset_id=asset_id,
            quantity=None,
            amount=1,
            currency="KRW",
            memo="잘못된 현금흐름",
        )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert holding["quantity"] == 10
    assert holding["average_cost"] == 70_000
    assert count_transactions(db, transaction_type) == 0


@pytest.mark.parametrize("transaction_type", ["dividend", "interest"])
def test_cash_income_transactions_increase_cash_asset(tmp_path, transaction_type):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    tx_id = apply_transaction(
        db,
        occurred_on="2026-06-12",
        type=transaction_type,
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=50_000,
        currency="KRW",
        memo="현금 소득",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert tx_id > 0
    assert holding["quantity"] == 50_000
    assert count_transactions(db, transaction_type) == 1


def test_fee_transaction_decreases_cash_asset(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")
    apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="deposit",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=100_000,
        currency="KRW",
        memo="초기 입금",
    )

    tx_id = apply_transaction(
        db,
        occurred_on="2026-06-13",
        type="fee",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=1_000,
        currency="KRW",
        memo="수수료",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert tx_id > 0
    assert holding["quantity"] == 99_000
    assert count_transactions(db, "fee") == 1


def test_debt_payment_on_cash_asset_is_rejected_without_changes(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")
    apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="deposit",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=100_000,
        currency="KRW",
        memo="초기 입금",
    )

    with pytest.raises(ValueError, match="부채 자산"):
        apply_transaction(
            db,
            occurred_on="2026-06-13",
            type="debt_payment",
            account_id=account_id,
            asset_id=asset_id,
            quantity=None,
            amount=1_000,
            currency="KRW",
            memo="잘못된 부채 상환",
        )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert holding["quantity"] == 100_000
    assert count_transactions(db, "debt_payment") == 0


def test_buy_transaction_on_cash_asset_is_rejected_without_changes(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    with pytest.raises(ValueError, match="시장성 자산"):
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="buy",
            account_id=account_id,
            asset_id=asset_id,
            quantity=1,
            amount=1_000,
            currency="KRW",
            memo="잘못된 매수",
        )

    assert count_transactions(db, "buy") == 0
    with pytest.raises(ValueError):
        get_holding(db, account_id=account_id, asset_id=asset_id)


def test_direct_holding_edit_creates_adjustment_transaction(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    tx_id = edit_holding_balance(
        db,
        account_id=account_id,
        asset_id=asset_id,
        quantity=1_500_000,
        memo="초기 현금 입력",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    tx = db.execute("select type, amount, memo from transactions where id = ?", (tx_id,)).fetchone()
    assert holding["quantity"] == 1_500_000
    assert tx["type"] == "adjustment"
    assert tx["amount"] == 1_500_000
    assert tx["memo"] == "초기 현금 입력"


def test_failed_transaction_insert_rolls_back_holding_update(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(
        db,
        symbol="TSLA",
        name="Tesla",
        type="stock_etf",
        currency="USD",
        market="US",
    )

    with pytest.raises(sqlite3.IntegrityError):
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="buy",
            account_id=account_id,
            asset_id=asset_id,
            quantity=1,
            amount=200,
            currency="USD",
            memo=None,
        )

    assert count_transactions(db, "buy") == 0
    with pytest.raises(ValueError):
        get_holding(db, account_id=account_id, asset_id=asset_id)


@pytest.mark.parametrize(
    ("transaction_type", "amount"),
    [
        ("deposit", -100),
        ("deposit", 0),
        ("withdrawal", -100),
        ("withdrawal", 0),
    ],
)
def test_non_positive_cash_amount_is_rejected_without_changes(
    tmp_path,
    transaction_type,
    amount,
):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    with pytest.raises(ValueError):
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type=transaction_type,
            account_id=account_id,
            asset_id=asset_id,
            quantity=None,
            amount=amount,
            currency="KRW",
            memo="잘못된 금액",
        )

    assert count_transactions(db, transaction_type) == 0
    with pytest.raises(ValueError):
        get_holding(db, account_id=account_id, asset_id=asset_id)


@pytest.mark.parametrize("fx_rate_to_krw", [-1, 0])
def test_invalid_fx_rate_is_rejected_without_changes(tmp_path, fx_rate_to_krw):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    with pytest.raises(ValueError, match="환율"):
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="deposit",
            account_id=account_id,
            asset_id=asset_id,
            quantity=None,
            amount=1_000_000,
            currency="KRW",
            memo="잘못된 환율",
            fx_rate_to_krw=fx_rate_to_krw,
        )

    assert count_transactions(db, "deposit") == 0
    with pytest.raises(ValueError):
        get_holding(db, account_id=account_id, asset_id=asset_id)


def test_debt_payment_more_than_holding_is_rejected_without_changes(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="대출", type="debt", currency="KRW")
    asset_id = create_asset(
        db,
        symbol=None,
        name="신용대출",
        type="debt",
        currency="KRW",
        market="KR",
    )
    edit_holding_balance(
        db,
        account_id=account_id,
        asset_id=asset_id,
        quantity=1_000,
        memo="초기 대출 입력",
    )

    with pytest.raises(ValueError):
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="debt_payment",
            account_id=account_id,
            asset_id=asset_id,
            quantity=None,
            amount=2_000,
            currency="KRW",
            memo="초과 상환",
        )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert holding["quantity"] == 1_000
    assert count_transactions(db, "debt_payment") == 0


def test_direct_holding_edit_defaults_to_asset_currency(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="해외 증권", type="brokerage", currency="USD")
    asset_id = create_asset(
        db,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        type="stock_etf",
        currency="USD",
        market="US",
    )

    tx_id = edit_holding_balance(
        db,
        account_id=account_id,
        asset_id=asset_id,
        quantity=3,
        memo="해외 ETF 입력",
    )

    tx = db.execute("select currency from transactions where id = ?", (tx_id,)).fetchone()
    assert tx["currency"] == "USD"

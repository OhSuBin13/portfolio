from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, create_asset, get_holding
from portfolio_app.services.transactions import apply_transaction, edit_holding_balance


def setup_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


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

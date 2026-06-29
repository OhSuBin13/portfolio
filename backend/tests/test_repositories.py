from portfolio_app import repositories
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account


def test_fetch_accounts_returns_accounts_ordered_by_id(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    first_id = create_account(db, name="원화 현금", type="cash")
    second_id = create_account(db, name="해외 증권", type="brokerage")

    assert hasattr(repositories, "fetch_accounts")
    rows = repositories.fetch_accounts(db)

    assert [row["id"] for row in rows] == [first_id, second_id]
    assert [row["name"] for row in rows] == ["원화 현금", "해외 증권"]
    assert "currency" not in set(rows[0].keys())


def test_fetch_account_returns_matching_account(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    account_id = create_account(db, name="해외 증권", type="brokerage")

    assert hasattr(repositories, "fetch_account")
    row = repositories.fetch_account(db, account_id=account_id)

    assert row is not None
    assert row["id"] == account_id
    assert row["name"] == "해외 증권"
    assert row["type"] == "brokerage"
    assert "currency" not in set(row.keys())


def test_fetch_account_returns_none_when_missing(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert hasattr(repositories, "fetch_account")
    row = repositories.fetch_account(db, account_id=999)

    assert row is None


def test_create_account_record_returns_created_account_row(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert hasattr(repositories, "create_account_record")
    row = repositories.create_account_record(db, name="원화 현금", type="cash")

    assert row["id"] > 0
    assert row["name"] == "원화 현금"
    assert row["type"] == "cash"
    assert "currency" not in set(row.keys())


def test_create_goal_record_returns_created_goal_row(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert hasattr(repositories, "create_goal_record")
    row = repositories.create_goal_record(
        db,
        name="순자산 1억",
        type="net_worth",
        target_amount_krw=100_000_000,
    )

    assert row["id"] > 0
    assert row["name"] == "순자산 1억"
    assert row["type"] == "net_worth"
    assert row["target_amount_krw"] == 100_000_000


def test_fetch_goals_returns_goals_ordered_by_id(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    first = repositories.create_goal(
        db,
        name="순자산 1억",
        type="net_worth",
        target_amount_krw=100_000_000,
    )
    second = repositories.create_goal(
        db,
        name="월 소득 100만",
        type="monthly_income",
        target_amount_krw=1_000_000,
    )

    assert hasattr(repositories, "fetch_goals")
    rows = repositories.fetch_goals(db)

    assert [row["id"] for row in rows] == [first, second]
    assert [row["name"] for row in rows] == ["순자산 1억", "월 소득 100만"]


def test_create_asset_record_persists_stock_metadata(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    row = repositories.create_asset_record(
        db,
        symbol="005930",
        name="삼성전자",
        type="stock_etf",
        currency="KRW",
        market="KR",
        is_listed=True,
        instrument_type="STOCK",
        metadata_source="manual",
    )

    assert row["symbol"] == "005930"
    assert row["is_listed"] == 1
    assert row["instrument_type"] == "STOCK"
    assert row["metadata_source"] == "manual"


def test_update_account_repository_updates_existing_account(tmp_path):
    from portfolio_app import repositories

    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")

    assert hasattr(repositories, "update_account")
    updated = repositories.update_account(
        db,
        account_id=account_id,
        name="해외 증권",
        type="brokerage",
    )

    account = repositories.fetch_account(db, account_id=account_id)
    assert updated is True
    assert account is not None
    assert account["name"] == "해외 증권"
    assert account["type"] == "brokerage"


def test_update_account_record_returns_updated_account_row(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")

    assert hasattr(repositories, "update_account_record")
    row = repositories.update_account_record(
        db,
        account_id=account_id,
        name="해외 증권",
        type="brokerage",
    )

    assert row is not None
    assert row["id"] == account_id
    assert row["name"] == "해외 증권"
    assert row["type"] == "brokerage"


def test_update_account_record_returns_none_when_missing(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert hasattr(repositories, "update_account_record")
    row = repositories.update_account_record(
        db,
        account_id=999,
        name="해외 증권",
        type="brokerage",
    )

    assert row is None


def test_delete_account_repository_deletes_existing_account(tmp_path):
    from portfolio_app import repositories

    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")

    deleted = repositories.delete_account(db, account_id=account_id)
    missing_deleted = repositories.delete_account(db, account_id=account_id)

    assert deleted is True
    assert repositories.fetch_account(db, account_id=account_id) is None
    assert missing_deleted is False


def test_insert_transaction_can_defer_commit(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")
    asset_id = repositories.create_asset(
        db,
        symbol=None,
        name="KRW",
        type="cash",
        currency="KRW",
        market="KR",
    )

    transaction_id = repositories.insert_transaction(
        db,
        occurred_on="2026-06-12",
        type="deposit",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=100_000,
        currency="KRW",
        fx_rate_to_krw=None,
        memo="초기 입금",
        commit=False,
    )

    row = db.execute("select * from transactions where id = ?", (transaction_id,)).fetchone()
    observer = connect(db_path)
    observer_count_before_commit = observer.execute(
        "select count(*) from transactions"
    ).fetchone()[0]
    observer.close()
    db.commit()
    observer = connect(db_path)
    observer_count_after_commit = observer.execute(
        "select count(*) from transactions"
    ).fetchone()[0]
    observer.close()

    assert row is not None
    assert row["type"] == "deposit"
    assert row["account_id"] == account_id
    assert row["asset_id"] == asset_id
    assert row["amount"] == 100_000
    assert row["memo"] == "초기 입금"
    assert observer_count_before_commit == 0
    assert observer_count_after_commit == 1


def test_fetch_transactions_returns_transactions_ordered_by_id(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    account_id = repositories.create_account(db, name="원화 현금", type="cash")
    asset_id = repositories.create_asset(
        db,
        symbol=None,
        name="KRW",
        type="cash",
        currency="KRW",
        market="KR",
    )
    first_id = repositories.insert_transaction(
        db,
        occurred_on="2026-06-13",
        type="deposit",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=200_000,
        currency="KRW",
        fx_rate_to_krw=None,
        memo="두 번째 날짜",
    )
    second_id = repositories.insert_transaction(
        db,
        occurred_on="2026-06-12",
        type="deposit",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=100_000,
        currency="KRW",
        fx_rate_to_krw=None,
        memo="첫 번째 날짜",
    )

    rows = repositories.fetch_transactions(db)

    assert [row["id"] for row in rows] == [first_id, second_id]
    assert [row["memo"] for row in rows] == ["두 번째 날짜", "첫 번째 날짜"]


def test_get_current_holding_returns_zero_state_when_missing(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    quantity, average_cost = repositories.get_current_holding(
        db,
        account_id=999,
        asset_id=999,
    )

    assert quantity == 0
    assert average_cost is None


def test_get_current_holding_returns_quantity_and_average_cost(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    account_id = repositories.create_account(db, name="해외 증권", type="brokerage")
    asset_id = repositories.create_asset(
        db,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        type="stock_etf",
        currency="USD",
        market="US",
    )
    repositories.upsert_holding(
        db,
        account_id=account_id,
        asset_id=asset_id,
        quantity=3,
        average_cost=500,
    )

    quantity, average_cost = repositories.get_current_holding(
        db,
        account_id=account_id,
        asset_id=asset_id,
    )

    assert quantity == 3
    assert average_cost == 500


def test_get_asset_type_returns_type_and_raises_when_missing(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    asset_id = repositories.create_asset(
        db,
        symbol=None,
        name="원화 현금",
        type="cash",
        currency="KRW",
        market="KR",
    )

    asset_type = repositories.get_asset_type(db, asset_id=asset_id)

    assert asset_type == "cash"
    try:
        repositories.get_asset_type(db, asset_id=999)
    except ValueError as exc:
        assert "자산을 찾을 수 없습니다." in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_get_asset_currency_returns_currency_and_krw_default_when_missing(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    asset_id = repositories.create_asset(
        db,
        symbol="VOO",
        name="Vanguard S&P 500 ETF",
        type="stock_etf",
        currency="USD",
        market="US",
    )

    assert repositories.get_asset_currency(db, asset_id=asset_id) == "USD"
    assert repositories.get_asset_currency(db, asset_id=999) == "KRW"

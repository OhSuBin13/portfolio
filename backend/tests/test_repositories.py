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

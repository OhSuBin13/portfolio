from portfolio_app import repositories
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def create_repository_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def test_create_goal_record_returns_created_goal_row(tmp_path):
    db = create_repository_db(tmp_path)

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
    db = create_repository_db(tmp_path)
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

    rows = repositories.fetch_goals(db)

    assert [row["id"] for row in rows] == [first, second]
    assert [row["name"] for row in rows] == ["순자산 1억", "월 소득 100만"]

from portfolio_app import repositories
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.toss_portfolio import TossOrder, TossOrderExecution


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


def toss_order(
    *,
    order_id: str,
    account_seq: str = "acct-1",
    symbol: str = "VOO",
    status: str = "FILLED",
    ordered_at: str = "2026-06-29T09:00:00+09:00",
) -> tuple[str, TossOrder]:
    return account_seq, TossOrder(
        order_id=order_id,
        symbol=symbol,
        side="BUY",
        order_type="LIMIT",
        time_in_force="DAY",
        status=status,
        price="500",
        quantity="1",
        order_amount=None,
        currency="USD",
        ordered_at=ordered_at,
        canceled_at=None,
        execution=TossOrderExecution(
            filled_quantity="1",
            average_filled_price="500",
            filled_amount="500",
            commission="1",
            tax="0",
            filled_at="2026-06-29T09:01:00+09:00",
            settlement_date="2026-07-01",
        ),
        raw={"orderId": order_id},
    )


def test_fetch_toss_order_import_runs_filters_by_account_and_orders_desc(tmp_path):
    db = create_repository_db(tmp_path)
    first = repositories.create_toss_order_import_run(
        db,
        account_seq="acct-1",
        status_filter="OPEN",
        symbol_filter=None,
        from_date=None,
        to_date=None,
    )
    other = repositories.create_toss_order_import_run(
        db,
        account_seq="acct-2",
        status_filter="OPEN",
        symbol_filter=None,
        from_date=None,
        to_date=None,
    )
    latest = repositories.create_toss_order_import_run(
        db,
        account_seq="acct-1",
        status_filter="CLOSED",
        symbol_filter="VOO",
        from_date="2026-06-01",
        to_date="2026-06-30",
    )

    all_rows = repositories.fetch_toss_order_import_runs(db)
    account_rows = repositories.fetch_toss_order_import_runs(db, account_seq="acct-1")

    assert [row["id"] for row in all_rows] == [latest, other, first]
    assert [row["id"] for row in account_rows] == [latest, first]
    assert [row["account_seq"] for row in account_rows] == ["acct-1", "acct-1"]


def test_fetch_toss_orders_applies_symbol_status_and_date_filters(tmp_path):
    db = create_repository_db(tmp_path)
    import_run_id = repositories.create_toss_order_import_run(
        db,
        account_seq="acct-1",
        status_filter="CLOSED",
        symbol_filter=None,
        from_date=None,
        to_date=None,
    )

    for account_seq, order in [
        toss_order(order_id="matching-order"),
        toss_order(order_id="wrong-symbol", symbol="AAPL"),
        toss_order(order_id="wrong-status", status="CANCELED"),
        toss_order(order_id="wrong-date", ordered_at="2026-06-28T09:00:00+09:00"),
        toss_order(order_id="wrong-account", account_seq="acct-2"),
    ]:
        repositories.upsert_toss_order(
            db,
            account_seq=account_seq,
            order=order,
            raw_json="{}",
            import_run_id=import_run_id,
        )
    db.commit()

    rows = repositories.fetch_toss_orders(
        db,
        account_seq="acct-1",
        symbol="voo",
        order_status="FILLED",
        from_date="2026-06-29",
        to_date="2026-06-29",
    )

    assert [row["order_id"] for row in rows] == ["matching-order"]

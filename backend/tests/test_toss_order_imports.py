import json
import sqlite3
from dataclasses import dataclass, field

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import fetch_toss_orders
from portfolio_app.services.toss_order_imports import import_toss_orders
from portfolio_app.services.toss_portfolio import TossOrder, TossOrderExecution, TossOrderPage


@dataclass
class RecordingOrderProvider:
    pages: list[TossOrderPage]
    calls: list[dict[str, object]] = field(default_factory=list)

    async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
        self.calls.append({"account_seq": account_seq, **kwargs})
        return self.pages.pop(0)


@dataclass
class FailingOrderProvider:
    error: Exception

    async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
        raise self.error


@dataclass
class FailingSecondPageProvider:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
        self.calls.append({"account_seq": account_seq, **kwargs})
        if len(self.calls) == 1:
            return TossOrderPage(
                orders=[_order(order_id="order-1")],
                next_cursor="cursor-2",
                has_next=True,
            )
        raise RuntimeError("second page unavailable")


def _db(tmp_path) -> sqlite3.Connection:
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def _execution(
    *,
    filled_quantity: str = "1",
    average_filled_price: str | None = "70100",
    filled_amount: str | None = "70100",
) -> TossOrderExecution:
    return TossOrderExecution(
        filled_quantity=filled_quantity,
        average_filled_price=average_filled_price,
        filled_amount=filled_amount,
        commission="100",
        tax="0",
        filled_at="2026-06-29T09:31:15+09:00",
        settlement_date="2026-07-01",
    )


def _order(
    *,
    order_id: str = "order-1",
    symbol: str = "005930",
    status: str = "FILLED",
    ordered_at: str = "2026-06-29T09:30:00+09:00",
    raw: dict[str, object] | None = None,
    execution: TossOrderExecution | None = None,
) -> TossOrder:
    return TossOrder(
        order_id=order_id,
        symbol=symbol,
        side="BUY",
        order_type="LIMIT",
        time_in_force="DAY",
        status=status,
        price="70000",
        quantity="1",
        order_amount=None,
        currency="KRW",
        ordered_at=ordered_at,
        canceled_at=None,
        execution=execution or _execution(),
        raw=raw or {"orderId": order_id, "status": status},
    )


def _import_run(db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("select * from toss_order_import_runs").fetchone()
    assert row is not None
    return row


@pytest.mark.asyncio
async def test_import_toss_orders_fetches_pages_with_cursor_values(tmp_path):
    db = _db(tmp_path)
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[_order(order_id="order-1")],
                next_cursor="cursor-2",
                has_next=True,
            ),
            TossOrderPage(orders=[_order(order_id="order-2")], next_cursor=None, has_next=False),
        ]
    )

    result = await import_toss_orders(
        db,
        provider=provider,
        account_seq="account-1",
        status="CLOSED",
        symbol="005930",
        from_date="2026-06-01",
        to_date="2026-06-29",
        limit=50,
    )

    assert [call["cursor"] for call in provider.calls] == [None, "cursor-2"]
    assert all(call["account_seq"] == "account-1" for call in provider.calls)
    assert all(call["status"] == "CLOSED" for call in provider.calls)
    assert all(call["symbol"] == "005930" for call in provider.calls)
    assert all(call["from_date"] == "2026-06-01" for call in provider.calls)
    assert all(call["to_date"] == "2026-06-29" for call in provider.calls)
    assert all(call["limit"] == 50 for call in provider.calls)
    assert result.imported_count == 2


@pytest.mark.asyncio
async def test_import_toss_orders_upserts_duplicate_orders_by_account_and_order_id(tmp_path):
    db = _db(tmp_path)
    updated_raw = {"label": "삼성전자", "orderId": "order-1", "status": "CANCELED"}
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[
                    _order(order_id="order-1", status="FILLED", raw={"status": "FILLED"}),
                    _order(
                        order_id="order-1",
                        status="CANCELED",
                        raw=updated_raw,
                        execution=_execution(
                            filled_quantity="0",
                            average_filled_price=None,
                            filled_amount=None,
                        ),
                    ),
                ],
                next_cursor=None,
                has_next=False,
            )
        ]
    )

    result = await import_toss_orders(
        db,
        provider=provider,
        account_seq="account-1",
        status="CLOSED",
    )

    rows = db.execute("select * from toss_orders").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["account_seq"] == "account-1"
    assert row["order_id"] == "order-1"
    assert row["order_status"] == "CANCELED"
    assert row["filled_quantity"] == "0"
    assert row["average_filled_price"] is None
    assert row["raw_json"] == json.dumps(updated_raw, ensure_ascii=False, sort_keys=True)
    assert row["import_run_id"] == result.run_id


@pytest.mark.asyncio
async def test_import_toss_orders_records_successful_run_with_processed_order_count(tmp_path):
    db = _db(tmp_path)
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[
                    _order(order_id="order-1"),
                    _order(order_id="order-1", status="CANCELED"),
                    _order(order_id="order-2"),
                ],
                next_cursor=None,
                has_next=False,
            )
        ]
    )

    result = await import_toss_orders(
        db,
        provider=provider,
        account_seq="account-1",
        status="CLOSED",
    )

    run = _import_run(db)
    assert run["id"] == result.run_id
    assert run["account_seq"] == "account-1"
    assert run["status_filter"] == "CLOSED"
    assert run["run_status"] == "success"
    assert run["imported_count"] == 3
    assert run["error_message"] == ""
    assert run["completed_at"] is not None
    assert result.imported_count == 3


@pytest.mark.asyncio
async def test_import_toss_orders_marks_run_failed_and_reraises_provider_error(tmp_path):
    db = _db(tmp_path)
    error = RuntimeError("provider unavailable")
    provider = FailingOrderProvider(error=error)

    with pytest.raises(RuntimeError) as exc_info:
        await import_toss_orders(db, provider=provider, account_seq="account-1", status="CLOSED")

    assert exc_info.value is error
    run = _import_run(db)
    assert run["run_status"] == "failed"
    assert run["imported_count"] == 0
    assert run["error_message"] == "provider unavailable"
    assert run["completed_at"] is not None


@pytest.mark.asyncio
async def test_import_toss_orders_failed_later_page_reports_only_committed_rows(
    tmp_path,
):
    db = _db(tmp_path)
    provider = FailingSecondPageProvider()

    with pytest.raises(RuntimeError, match="second page"):
        await import_toss_orders(db, provider=provider, account_seq="account-1", status="OPEN")

    assert [call["cursor"] for call in provider.calls] == [None, "cursor-2"]
    assert db.execute("select count(*) from toss_orders").fetchone()[0] == 0
    run = _import_run(db)
    assert run["run_status"] == "failed"
    assert run["imported_count"] == 0
    assert run["error_message"] == "second page unavailable"


@pytest.mark.asyncio
async def test_import_toss_orders_rejects_has_next_without_cursor(tmp_path):
    db = _db(tmp_path)
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[_order(order_id="order-1")],
                next_cursor=None,
                has_next=True,
            )
        ]
    )

    with pytest.raises(ValueError, match="nextCursor"):
        await import_toss_orders(db, provider=provider, account_seq="account-1", status="OPEN")

    assert db.execute("select count(*) from toss_orders").fetchone()[0] == 0
    run = _import_run(db)
    assert run["run_status"] == "failed"
    assert run["imported_count"] == 0
    assert "nextCursor" in run["error_message"]


@pytest.mark.asyncio
async def test_import_toss_orders_rejects_repeated_next_cursor(tmp_path):
    db = _db(tmp_path)
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[_order(order_id="order-1")],
                next_cursor="cursor-2",
                has_next=True,
            ),
            TossOrderPage(
                orders=[_order(order_id="order-2")],
                next_cursor="cursor-2",
                has_next=True,
            ),
        ]
    )

    with pytest.raises(ValueError, match="반복"):
        await import_toss_orders(db, provider=provider, account_seq="account-1", status="OPEN")

    assert [call["cursor"] for call in provider.calls] == [None, "cursor-2"]
    assert db.execute("select count(*) from toss_orders").fetchone()[0] == 0
    run = _import_run(db)
    assert run["run_status"] == "failed"
    assert run["imported_count"] == 0
    assert "반복" in run["error_message"]


@pytest.mark.asyncio
async def test_fetch_toss_orders_filters_by_original_ordered_at_calendar_date(tmp_path):
    db = _db(tmp_path)
    provider = RecordingOrderProvider(
        pages=[
            TossOrderPage(
                orders=[
                    _order(
                        order_id="early-kst",
                        ordered_at="2026-06-29T00:30:00+09:00",
                    ),
                    _order(
                        order_id="previous-day",
                        ordered_at="2026-06-28T23:30:00+09:00",
                    ),
                ],
                next_cursor=None,
                has_next=False,
            )
        ]
    )
    await import_toss_orders(db, provider=provider, account_seq="account-1", status="OPEN")

    rows = fetch_toss_orders(db, account_seq="account-1", from_date="2026-06-29")

    assert [row["order_id"] for row in rows] == ["early-kst"]

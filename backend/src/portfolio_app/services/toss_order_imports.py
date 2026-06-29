import json
import sqlite3
from dataclasses import dataclass
from typing import Protocol

from portfolio_app.repositories import (
    create_toss_order_import_run,
    finish_toss_order_import_run,
    upsert_toss_order,
)
from portfolio_app.services.toss_portfolio import TossOrderPage


class TossOrderProvider(Protocol):
    async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
        pass


@dataclass(frozen=True)
class TossOrderImportResult:
    run_id: int
    imported_count: int


async def import_toss_orders(
    db: sqlite3.Connection,
    *,
    provider: TossOrderProvider,
    account_seq: str,
    status: str,
    symbol: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> TossOrderImportResult:
    run_id = create_toss_order_import_run(
        db,
        account_seq=account_seq,
        status_filter=status,
        symbol_filter=symbol,
        from_date=from_date,
        to_date=to_date,
    )
    imported_count = 0

    try:
        with db:
            cursor: str | None = None
            while True:
                page = await provider.fetch_orders(
                    account_seq,
                    status=status,
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    cursor=cursor,
                    limit=limit,
                )
                for order in page.orders:
                    raw_json = json.dumps(order.raw, ensure_ascii=False, sort_keys=True)
                    upsert_toss_order(
                        db,
                        account_seq=account_seq,
                        order=order,
                        raw_json=raw_json,
                        import_run_id=run_id,
                    )
                    imported_count += 1

                if not page.has_next:
                    break
                cursor = page.next_cursor

            finish_toss_order_import_run(
                db,
                run_id=run_id,
                run_status="success",
                imported_count=imported_count,
            )
    except Exception as exc:
        if db.in_transaction:
            db.rollback()
        try:
            finish_toss_order_import_run(
                db,
                run_id=run_id,
                run_status="failed",
                imported_count=imported_count,
                error_message=str(exc),
            )
            db.commit()
        except Exception:
            db.rollback()
        raise

    return TossOrderImportResult(run_id=run_id, imported_count=imported_count)

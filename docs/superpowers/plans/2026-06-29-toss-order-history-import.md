# Toss Order History Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import Toss Securities order history into local SQLite so the Toss-only portfolio can show persisted account-scoped order records without restoring the removed local transaction ledger.

**Architecture:** Keep Toss holdings as the portfolio valuation source of truth. Add a narrow local order-history cache with import-run metadata, backed by Toss `GET /api/v1/orders` and optional `GET /api/v1/orders/{orderId}` parsing. The imported data is read-only history, not a replacement for `/api/transactions`, holdings mutation, growth history, or order placement.

**Tech Stack:** FastAPI, SQLite migrations, Pydantic v2, httpx, pytest/pytest-httpx, React/Vite, source-inspection frontend tests.

---

## Current Context

- Current branch: `feature/toss-order-history-import`.
- Current fresh schema version: `SCHEMA_VERSION = 10`.
- Current fresh schema tables: `schema_migrations`, `fx_rates`, `goals`, `backups`, `settings`.
- Current Toss portfolio endpoints: `GET /api/toss/accounts`, `GET /api/toss/holdings`, `GET /api/summary?account_seq=...`.
- Current Toss auth/rate-limit boundary: `TossAuthClient` and `request_with_toss_retry()` in `backend/src/portfolio_app/services/market_data.py`.
- Current frontend screens: Dashboard, Toss read-only holdings, goals, settings.

## Toss API Facts Checked On 2026-06-29

Official OpenAPI URL: `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json`

Observed official API metadata:

- OpenAPI title: `토스증권 Open API`
- OpenAPI version: `1.1.5`
- Order list endpoint: `GET /api/v1/orders`
- Order detail endpoint: `GET /api/v1/orders/{orderId}`
- Required account header: `X-Tossinvest-Account`
- List filters: `status=OPEN|CLOSED`, optional `symbol`, `from`, `to`, `cursor`, `limit`.
- List limit range: `1..100`, default `20`.
- Page shape: `orders`, `nextCursor`, `hasNext`.
- Order fields include `orderId`, `symbol`, `side`, `orderType`, `timeInForce`, `status`, `price`, `quantity`, `orderAmount`, `currency`, `orderedAt`, `canceledAt`, and `execution`.
- Execution fields include `filledQuantity`, `averageFilledPrice`, `filledAmount`, `commission`, `tax`, `filledAt`, `settlementDate`.
- The official `PaginatedOrderResponse` description currently says `status=CLOSED` returns `400 closed-not-supported`. Implement the app so CLOSED failures are surfaced cleanly instead of assuming closed-history import is already available.

## Product Decisions

- Do not reintroduce local `accounts`, `assets`, `holdings`, `transactions`, `price_snapshots`, or `portfolio_snapshots`.
- Persist imported Toss orders in new Toss-specific tables only.
- Use `(account_seq, order_id)` as the durable identity.
- Preserve Toss decimal values as text in SQLite and API responses to avoid float rounding in order quantities/prices.
- Treat Toss enum-like fields as strings in persisted records and response models. The Toss docs explicitly say clients should tolerate unknown codes.
- Keep order import manually triggered in the UI for this first implementation. Do not add background import until rate-limit behavior and user value are known.
- Keep order placement, cancel, modify, local cash-leg accounting, growth reconstruction, and tax/performance analytics out of scope.

## File Structure

- Modify `backend/src/portfolio_app/schema.sql`
  - Add `toss_order_import_runs`.
  - Add `toss_orders`.
  - Add indexes for account/date/status/symbol lookup.
- Modify `backend/src/portfolio_app/migrations.py`
  - Bump `SCHEMA_VERSION` to `11`.
  - Add v10-to-v11 migration that creates only the new Toss order-history tables.
- Modify `backend/src/portfolio_app/models.py`
  - Add request/response models for Toss order imports and imported Toss orders.
- Modify `backend/src/portfolio_app/repositories.py`
  - Add Toss order import-run create/finish/list helpers.
  - Add Toss order upsert/list helpers.
- Modify `backend/src/portfolio_app/services/toss_portfolio.py`
  - Add provider methods and parser dataclasses for order list/detail responses.
- Create `backend/src/portfolio_app/services/toss_order_imports.py`
  - Orchestrate paginated import and repository writes.
- Modify `backend/src/portfolio_app/api/toss_portfolio.py`
  - Add import and imported-order read endpoints under `/api/toss`.
- Modify `backend/tests/test_db.py`
  - Cover fresh v11 schema and v10-to-v11 migration.
- Modify `backend/tests/test_toss_portfolio.py`
  - Cover Toss order-history provider parsing, pagination, headers, and 429 retry reuse.
- Create `backend/tests/test_toss_order_imports.py`
  - Cover repository/service import behavior.
- Modify `backend/tests/test_api.py`
  - Cover HTTP import/list endpoints and OpenAPI exposure.
- Modify `backend/tests/test_toss_only_architecture.py`
  - Keep `/api/transactions` removed while allowing `/api/toss/orders`.
- Modify `frontend/src/types.ts`
  - Add Toss order/import run types.
- Modify `frontend/src/App.tsx`
  - Mount the new order-history screen.
- Modify `frontend/src/components/AppShell.tsx`
  - Add a `주문내역` navigation item with a lucide icon.
- Create `frontend/src/components/OrderHistoryPage.tsx`
  - Account selector, filters, import command, run status, imported order table.
- Create `frontend/tests/toss-order-history-page.test.mjs`
  - Lock source-level frontend contract.
- Modify `docs/toss-open-api-integration.md`
  - Move order-history import from future work into implemented/planned behavior and document CLOSED limitation.
- Modify `README.md`
  - Refresh stale MVP wording if still inaccurate after the feature lands.

---

## Task 1: Schema And Migration

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/tests/test_db.py`

- [ ] **Step 1: Write failing fresh-schema test**

Add to `backend/tests/test_db.py`:

```python
def test_migrate_creates_toss_order_history_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")

    migrate(db)

    assert migration_versions(db) == [11]
    assert {
        "toss_order_import_runs",
        "toss_orders",
    } <= table_names(db)
    assert {
        "idx_toss_orders_account_ordered_at",
        "idx_toss_orders_account_status",
        "idx_toss_orders_account_symbol",
    } <= index_names(db)
```

- [ ] **Step 2: Write failing v10-to-v11 migration test**

Add to `backend/tests/test_db.py`:

```python
def test_migrate_from_v10_adds_toss_order_history_tables(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 10)
    create_toss_only_survivor_tables(db)
    db.commit()

    migrate(db)

    assert migration_versions(db) == [10, 11]
    assert {
        "toss_order_import_runs",
        "toss_orders",
    } <= table_names(db)
    assert_removed_local_ledger_tables_gone(db)
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_migrate_creates_toss_order_history_tables backend/tests/test_db.py::test_migrate_from_v10_adds_toss_order_history_tables -q
```

Expected: FAIL because schema version 11 and the new tables do not exist yet.

- [ ] **Step 4: Add fresh-schema tables**

Append to `backend/src/portfolio_app/schema.sql`:

```sql
create table if not exists toss_order_import_runs (
  id integer primary key,
  account_seq text not null,
  status_filter text not null check (status_filter in ('OPEN','CLOSED')),
  symbol_filter text,
  from_date text,
  to_date text,
  run_status text not null check (run_status in ('running','success','failed')),
  imported_count integer not null default 0 check (imported_count >= 0),
  error_message text not null default '',
  started_at text not null default current_timestamp,
  completed_at text
);

create table if not exists toss_orders (
  id integer primary key,
  account_seq text not null,
  order_id text not null,
  symbol text not null,
  side text not null,
  order_type text not null,
  time_in_force text not null,
  order_status text not null,
  price text,
  quantity text not null,
  order_amount text,
  currency text not null,
  ordered_at text not null,
  canceled_at text,
  filled_quantity text not null,
  average_filled_price text,
  filled_amount text,
  commission text,
  tax text,
  filled_at text,
  settlement_date text,
  raw_json text not null,
  import_run_id integer references toss_order_import_runs(id) on delete set null,
  imported_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique(account_seq, order_id)
);

create index if not exists idx_toss_orders_account_ordered_at
on toss_orders(account_seq, ordered_at desc, id desc);

create index if not exists idx_toss_orders_account_status
on toss_orders(account_seq, order_status, ordered_at desc, id desc);

create index if not exists idx_toss_orders_account_symbol
on toss_orders(account_seq, symbol, ordered_at desc, id desc);
```

- [ ] **Step 5: Add migration v11**

In `backend/src/portfolio_app/migrations.py`, change:

```python
SCHEMA_VERSION = 10
```

to:

```python
SCHEMA_VERSION = 11
```

Add:

```python
def _migrate_from_10_to_11(db: sqlite3.Connection) -> None:
    with db:
        for statement in _schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            db.execute(statement)
        db.execute("insert or ignore into schema_migrations(version) values (11)")
```

Then call it in `migrate()` after v10:

```python
    if version == 10:
        _migrate_from_10_to_11(db)
        version = 11
```

- [ ] **Step 6: Update toss-only schema constants**

In `backend/tests/test_db.py`, update `TOSS_ONLY_TABLES` to include:

```python
"toss_order_import_runs",
"toss_orders",
```

Update `TOSS_ONLY_INDEXES` to include:

```python
"idx_toss_orders_account_ordered_at",
"idx_toss_orders_account_status",
"idx_toss_orders_account_symbol",
```

- [ ] **Step 7: Run schema tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py -q
```

Expected: PASS.

---

## Task 2: Provider Parsing For Toss Order History

**Files:**
- Modify: `backend/src/portfolio_app/services/toss_portfolio.py`
- Modify: `backend/tests/test_toss_portfolio.py`

- [ ] **Step 1: Write failing provider list test**

Add to `backend/tests/test_toss_portfolio.py`:

```python
@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_order_page(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://openapi.tossinvest.com/api/v1/orders"
            "?status=OPEN&symbol=005930&from=2026-06-01&to=2026-06-29&limit=100"
        ),
        json={
            "result": {
                "orders": [
                    {
                        "orderId": "order-1",
                        "symbol": "005930",
                        "side": "BUY",
                        "orderType": "LIMIT",
                        "timeInForce": "DAY",
                        "status": "PARTIAL_FILLED",
                        "price": "70000",
                        "quantity": "10",
                        "orderAmount": None,
                        "currency": "KRW",
                        "orderedAt": "2026-06-29T09:30:00+09:00",
                        "canceledAt": None,
                        "execution": {
                            "filledQuantity": "3",
                            "averageFilledPrice": "70100",
                            "filledAmount": "210300",
                            "commission": "100",
                            "tax": "0",
                            "filledAt": "2026-06-29T09:31:15+09:00",
                            "settlementDate": "2026-07-01",
                        },
                    }
                ],
                "nextCursor": "cursor-2",
                "hasNext": True,
            }
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    page = await provider.fetch_orders(
        "acct-1",
        status="OPEN",
        symbol="005930",
        from_date="2026-06-01",
        to_date="2026-06-29",
        limit=100,
    )

    assert page.next_cursor == "cursor-2"
    assert page.has_next is True
    assert page.orders[0].order_id == "order-1"
    assert page.orders[0].execution.filled_quantity == "3"
    request = httpx_mock.get_requests()[1]
    assert request.headers["x-tossinvest-account"] == "acct-1"
```

- [ ] **Step 2: Write failing detail test**

Add:

```python
@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_order_detail(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/orders/order-1",
        json={
            "result": {
                "orderId": "order-1",
                "symbol": "VOO",
                "side": "SELL",
                "orderType": "MARKET",
                "timeInForce": "DAY",
                "status": "FILLED",
                "price": None,
                "quantity": "1.25",
                "orderAmount": None,
                "currency": "USD",
                "orderedAt": "2026-06-29T09:30:00+09:00",
                "canceledAt": None,
                "execution": {
                    "filledQuantity": "1.25",
                    "averageFilledPrice": "500.12",
                    "filledAmount": "625.15",
                    "commission": "0.25",
                    "tax": None,
                    "filledAt": "2026-06-29T09:31:15+09:00",
                    "settlementDate": "2026-07-01",
                },
            }
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    order = await provider.fetch_order("acct-1", "order-1")

    assert order.order_id == "order-1"
    assert order.symbol == "VOO"
    assert order.currency == "USD"
    assert order.execution.filled_amount == "625.15"
```

- [ ] **Step 3: Run focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_fetches_order_page backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_fetches_order_detail -q
```

Expected: FAIL because the provider methods do not exist.

- [ ] **Step 4: Implement dataclasses and provider methods**

Add these dataclasses to `backend/src/portfolio_app/services/toss_portfolio.py`:

```python
@dataclass(frozen=True)
class TossOrderExecution:
    filled_quantity: str
    average_filled_price: str | None
    filled_amount: str | None
    commission: str | None
    tax: str | None
    filled_at: str | None
    settlement_date: str | None


@dataclass(frozen=True)
class TossOrder:
    order_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    status: str
    price: str | None
    quantity: str
    order_amount: str | None
    currency: str
    ordered_at: str
    canceled_at: str | None
    execution: TossOrderExecution
    raw: dict[str, Any]


@dataclass(frozen=True)
class TossOrderPage:
    orders: list[TossOrder]
    next_cursor: str | None
    has_next: bool
```

Add methods to `TossBrokerageProvider`:

```python
    async def fetch_orders(
        self,
        account_seq: str,
        *,
        status: str,
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> TossOrderPage:
        token = await self._token()
        params: dict[str, object] = {"status": status, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                params=params,
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("Toss 응답에서 주문 목록을 찾을 수 없습니다.")
        orders = result.get("orders")
        if not isinstance(orders, list):
            raise ValueError("Toss 주문 목록은 배열이어야 합니다.")
        return TossOrderPage(
            orders=[_parse_order(item) for item in orders],
            next_cursor=_optional_text(result.get("nextCursor")),
            has_next=bool(result.get("hasNext")),
        )

    async def fetch_order(self, account_seq: str, order_id: str) -> TossOrder:
        token = await self._token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/orders/{order_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("Toss 응답에서 주문 상세를 찾을 수 없습니다.")
        return _parse_order(result)
```

Add parser helpers:

```python
def _parse_order(item: dict[str, Any]) -> TossOrder:
    if not isinstance(item, dict):
        raise ValueError("Toss 주문 항목은 객체여야 합니다.")
    execution = item.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("Toss 주문 체결 정보가 필요합니다.")
    return TossOrder(
        order_id=_required_text(item.get("orderId"), "Toss 주문 식별자가 필요합니다."),
        symbol=_required_text(item.get("symbol"), "Toss 주문 종목 심볼이 필요합니다.").upper(),
        side=_required_text(item.get("side"), "Toss 주문 방향이 필요합니다."),
        order_type=_required_text(item.get("orderType"), "Toss 주문 유형이 필요합니다."),
        time_in_force=_required_text(item.get("timeInForce"), "Toss 주문 유효 조건이 필요합니다."),
        status=_required_text(item.get("status"), "Toss 주문 상태가 필요합니다."),
        price=_optional_text(item.get("price")),
        quantity=_required_text(item.get("quantity"), "Toss 주문 수량이 필요합니다."),
        order_amount=_optional_text(item.get("orderAmount")),
        currency=_required_text(item.get("currency"), "Toss 주문 통화가 필요합니다."),
        ordered_at=_required_text(item.get("orderedAt"), "Toss 주문 시간이 필요합니다."),
        canceled_at=_optional_text(item.get("canceledAt")),
        execution=TossOrderExecution(
            filled_quantity=_required_text(
                execution.get("filledQuantity"),
                "Toss 체결 수량이 필요합니다.",
            ),
            average_filled_price=_optional_text(execution.get("averageFilledPrice")),
            filled_amount=_optional_text(execution.get("filledAmount")),
            commission=_optional_text(execution.get("commission")),
            tax=_optional_text(execution.get("tax")),
            filled_at=_optional_text(execution.get("filledAt")),
            settlement_date=_optional_text(execution.get("settlementDate")),
        ),
        raw=dict(item),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
```

- [ ] **Step 5: Run provider tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py -q
```

Expected: PASS.

---

## Task 3: Repository And Import Service

**Files:**
- Modify: `backend/src/portfolio_app/repositories.py`
- Create: `backend/src/portfolio_app/services/toss_order_imports.py`
- Create: `backend/tests/test_toss_order_imports.py`

- [ ] **Step 1: Add repository/service tests**

Create `backend/tests/test_toss_order_imports.py`:

```python
from dataclasses import replace

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.toss_order_imports import import_toss_orders
from portfolio_app.services.toss_portfolio import TossOrder, TossOrderExecution, TossOrderPage


def sample_order(order_id: str = "order-1") -> TossOrder:
    return TossOrder(
        order_id=order_id,
        symbol="005930",
        side="BUY",
        order_type="LIMIT",
        time_in_force="DAY",
        status="FILLED",
        price="70000",
        quantity="10",
        order_amount=None,
        currency="KRW",
        ordered_at="2026-06-29T09:30:00+09:00",
        canceled_at=None,
        execution=TossOrderExecution(
            filled_quantity="10",
            average_filled_price="70000",
            filled_amount="700000",
            commission="1400",
            tax="0",
            filled_at="2026-06-29T09:31:00+09:00",
            settlement_date="2026-07-01",
        ),
        raw={"orderId": order_id},
    )


class StubOrderProvider:
    def __init__(self, pages: list[TossOrderPage]) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
        self.calls.append({"account_seq": account_seq, **kwargs})
        return self.pages.pop(0)


@pytest.mark.asyncio
async def test_import_toss_orders_paginates_and_upserts(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    first = sample_order("order-1")
    updated = replace(first, status="FILLED", raw={"orderId": "order-1", "status": "FILLED"})
    provider = StubOrderProvider(
        [
            TossOrderPage(orders=[first], next_cursor="cursor-2", has_next=True),
            TossOrderPage(orders=[updated, sample_order("order-2")], next_cursor=None, has_next=False),
        ]
    )

    result = await import_toss_orders(
        db,
        provider=provider,
        account_seq="acct-1",
        status="OPEN",
        symbol="005930",
        from_date="2026-06-01",
        to_date="2026-06-29",
    )

    assert result.imported_count == 3
    assert [call["cursor"] for call in provider.calls] == [None, "cursor-2"]
    rows = db.execute("select order_id, order_status from toss_orders order by order_id").fetchall()
    assert [(row["order_id"], row["order_status"]) for row in rows] == [
        ("order-1", "FILLED"),
        ("order-2", "FILLED"),
    ]
    run = db.execute("select * from toss_order_import_runs").fetchone()
    assert run["run_status"] == "success"
    assert run["imported_count"] == 3


@pytest.mark.asyncio
async def test_import_toss_orders_marks_run_failed_on_provider_error(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    class FailingProvider:
        async def fetch_orders(self, account_seq: str, **kwargs: object) -> TossOrderPage:
            raise ValueError("Toss 주문 목록을 가져올 수 없습니다.")

    with pytest.raises(ValueError, match="주문 목록"):
        await import_toss_orders(
            db,
            provider=FailingProvider(),
            account_seq="acct-1",
            status="CLOSED",
        )

    run = db.execute("select * from toss_order_import_runs").fetchone()
    assert run["run_status"] == "failed"
    assert "주문 목록" in run["error_message"]
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_order_imports.py -q
```

Expected: FAIL because repository helpers and service do not exist.

- [ ] **Step 3: Add repository helpers**

Add to `backend/src/portfolio_app/repositories.py`:

```python
def create_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    status_filter: str,
    symbol_filter: str | None,
    from_date: str | None,
    to_date: str | None,
) -> int:
    cursor = db.execute(
        """
        insert into toss_order_import_runs(
          account_seq, status_filter, symbol_filter, from_date, to_date, run_status
        )
        values (?, ?, ?, ?, ?, 'running')
        """,
        (account_seq, status_filter, symbol_filter, from_date, to_date),
    )
    db.commit()
    return int(cursor.lastrowid)


def finish_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    run_id: int,
    run_status: str,
    imported_count: int,
    error_message: str = "",
) -> None:
    db.execute(
        """
        update toss_order_import_runs
        set run_status = ?,
            imported_count = ?,
            error_message = ?,
            completed_at = current_timestamp
        where id = ?
        """,
        (run_status, imported_count, error_message, run_id),
    )
    db.commit()


def upsert_toss_order(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    order: object,
    raw_json: str,
    import_run_id: int,
) -> None:
    execution = order.execution
    db.execute(
        """
        insert into toss_orders(
          account_seq, order_id, symbol, side, order_type, time_in_force,
          order_status, price, quantity, order_amount, currency, ordered_at,
          canceled_at, filled_quantity, average_filled_price, filled_amount,
          commission, tax, filled_at, settlement_date, raw_json, import_run_id
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(account_seq, order_id)
        do update set symbol = excluded.symbol,
                      side = excluded.side,
                      order_type = excluded.order_type,
                      time_in_force = excluded.time_in_force,
                      order_status = excluded.order_status,
                      price = excluded.price,
                      quantity = excluded.quantity,
                      order_amount = excluded.order_amount,
                      currency = excluded.currency,
                      ordered_at = excluded.ordered_at,
                      canceled_at = excluded.canceled_at,
                      filled_quantity = excluded.filled_quantity,
                      average_filled_price = excluded.average_filled_price,
                      filled_amount = excluded.filled_amount,
                      commission = excluded.commission,
                      tax = excluded.tax,
                      filled_at = excluded.filled_at,
                      settlement_date = excluded.settlement_date,
                      raw_json = excluded.raw_json,
                      import_run_id = excluded.import_run_id,
                      updated_at = current_timestamp
        """,
        (
            account_seq,
            order.order_id,
            order.symbol,
            order.side,
            order.order_type,
            order.time_in_force,
            order.status,
            order.price,
            order.quantity,
            order.order_amount,
            order.currency,
            order.ordered_at,
            order.canceled_at,
            execution.filled_quantity,
            execution.average_filled_price,
            execution.filled_amount,
            execution.commission,
            execution.tax,
            execution.filled_at,
            execution.settlement_date,
            raw_json,
            import_run_id,
        ),
    )
```

- [ ] **Step 4: Implement import service**

Create `backend/src/portfolio_app/services/toss_order_imports.py`:

```python
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
    cursor: str | None = None
    try:
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
            with db:
                for order in page.orders:
                    upsert_toss_order(
                        db,
                        account_seq=account_seq,
                        order=order,
                        raw_json=json.dumps(order.raw, ensure_ascii=False, sort_keys=True),
                        import_run_id=run_id,
                    )
                    imported_count += 1
            if not page.has_next or page.next_cursor is None:
                break
            cursor = page.next_cursor
    except Exception as exc:
        finish_toss_order_import_run(
            db,
            run_id=run_id,
            run_status="failed",
            imported_count=imported_count,
            error_message=str(exc),
        )
        raise

    finish_toss_order_import_run(
        db,
        run_id=run_id,
        run_status="success",
        imported_count=imported_count,
    )
    return TossOrderImportResult(run_id=run_id, imported_count=imported_count)
```

- [ ] **Step 5: Run service tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_order_imports.py -q
```

Expected: PASS.

---

## Task 4: Backend API Surface

**Files:**
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/src/portfolio_app/api/toss_portfolio.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_toss_only_architecture.py`

- [ ] **Step 1: Write failing HTTP tests**

Add to `backend/tests/test_api.py`:

```python
def test_openapi_exposes_toss_order_history_paths(tmp_path):
    client = create_test_client(tmp_path)

    paths = set(client.get("/openapi.json").json()["paths"])

    assert "/api/toss/order-imports" in paths
    assert "/api/toss/orders" in paths
    assert "/api/transactions" not in paths


def test_toss_order_import_endpoint_imports_open_orders(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/orders?status=OPEN&limit=100",
        json={
            "result": {
                "orders": [
                    {
                        "orderId": "order-1",
                        "symbol": "005930",
                        "side": "BUY",
                        "orderType": "LIMIT",
                        "timeInForce": "DAY",
                        "status": "FILLED",
                        "price": "70000",
                        "quantity": "10",
                        "orderAmount": None,
                        "currency": "KRW",
                        "orderedAt": "2026-06-29T09:30:00+09:00",
                        "canceledAt": None,
                        "execution": {
                            "filledQuantity": "10",
                            "averageFilledPrice": "70000",
                            "filledAmount": "700000",
                            "commission": "1400",
                            "tax": "0",
                            "filledAt": "2026-06-29T09:31:00+09:00",
                            "settlementDate": "2026-07-01",
                        },
                    }
                ],
                "nextCursor": None,
                "hasNext": False,
            }
        },
    )

    response = client.post(
        "/api/toss/order-imports",
        json={"account_seq": "acct-1", "status": "OPEN"},
    )

    assert response.status_code == 201
    assert response.json()["imported_count"] == 1
    orders = client.get("/api/toss/orders?account_seq=acct-1").json()
    assert orders[0]["order_id"] == "order-1"
    assert orders[0]["filled_amount"] == "700000"
```

- [ ] **Step 2: Run focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_openapi_exposes_toss_order_history_paths backend/tests/test_api.py::test_toss_order_import_endpoint_imports_open_orders -q
```

Expected: FAIL because routes do not exist.

- [ ] **Step 3: Add models**

Add to `backend/src/portfolio_app/models.py`:

```python
OrderHistoryStatus = Literal["OPEN", "CLOSED"]


class TossOrderImportCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    account_seq: str = Field(min_length=1)
    status: OrderHistoryStatus = "OPEN"
    symbol: str | None = None
    from_date: date | None = None
    to_date: date | None = None


class TossOrderImportRunResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    account_seq: str
    status_filter: str
    symbol_filter: str | None
    from_date: str | None
    to_date: str | None
    run_status: str
    imported_count: int
    error_message: str
    started_at: str
    completed_at: str | None


class TossOrderResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: int
    account_seq: str
    order_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    order_status: str
    price: str | None
    quantity: str
    order_amount: str | None
    currency: str
    ordered_at: str
    canceled_at: str | None
    filled_quantity: str
    average_filled_price: str | None
    filled_amount: str | None
    commission: str | None
    tax: str | None
    filled_at: str | None
    settlement_date: str | None
    imported_at: str
    updated_at: str
```

- [ ] **Step 4: Add query repository helpers**

Add to `backend/src/portfolio_app/repositories.py`:

```python
def fetch_toss_order_import_runs(
    db: sqlite3.Connection,
    *,
    account_seq: str | None = None,
) -> list[sqlite3.Row]:
    if account_seq is None:
        return db.execute("select * from toss_order_import_runs order by id desc").fetchall()
    return db.execute(
        "select * from toss_order_import_runs where account_seq = ? order by id desc",
        (account_seq,),
    ).fetchall()


def fetch_toss_orders(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    symbol: str | None = None,
    order_status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[sqlite3.Row]:
    clauses = ["account_seq = ?"]
    params: list[object] = [account_seq]
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    if order_status:
        clauses.append("order_status = ?")
        params.append(order_status)
    if from_date:
        clauses.append("date(ordered_at) >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("date(ordered_at) <= ?")
        params.append(to_date)
    return db.execute(
        f"""
        select * from toss_orders
        where {' and '.join(clauses)}
        order by ordered_at desc, id desc
        """,
        params,
    ).fetchall()
```

- [ ] **Step 5: Add API routes**

In `backend/src/portfolio_app/api/toss_portfolio.py`, import the DB dependency, models, repository helpers, and service:

```python
import sqlite3
from datetime import date
from typing import Literal

from fastapi import Depends

from portfolio_app.api import get_db, row_to_dict
from portfolio_app.models import (
    TossOrderImportCreate,
    TossOrderImportRunResponse,
    TossOrderResponse,
)
from portfolio_app.repositories import fetch_toss_order_import_runs, fetch_toss_orders
from portfolio_app.services.toss_order_imports import import_toss_orders

Db = Annotated[sqlite3.Connection, Depends(get_db)]
```

Add routes:

```python
@router.post(
    "/order-imports",
    response_model=TossOrderImportRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_toss_order_import(
    request: Request,
    db: Db,
    payload: TossOrderImportCreate,
) -> TossOrderImportRunResponse:
    account_seq = normalize_account_seq(payload.account_seq)
    symbol = payload.symbol.strip().upper() if payload.symbol else None
    settings = request.app.state.settings
    try:
        result = await import_toss_orders(
            db,
            provider=TossBrokerageProvider(
                settings.toss_api_key,
                settings.toss_secret_key,
                auth_client=request.app.state.toss_auth_client,
            ),
            account_seq=account_seq,
            status=payload.status,
            symbol=symbol,
            from_date=payload.from_date.isoformat() if payload.from_date else None,
            to_date=payload.to_date.isoformat() if payload.to_date else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=toss_http_error_detail(exc),
        ) from exc

    rows = fetch_toss_order_import_runs(db, account_seq=account_seq)
    row = next(row for row in rows if int(row["id"]) == result.run_id)
    return TossOrderImportRunResponse(**row_to_dict(row))


@router.get("/order-imports", response_model=list[TossOrderImportRunResponse])
def list_toss_order_import_runs(
    db: Db,
    account_seq: str | None = None,
) -> list[TossOrderImportRunResponse]:
    normalized = normalize_account_seq(account_seq) if account_seq is not None else None
    return [
        TossOrderImportRunResponse(**row_to_dict(row))
        for row in fetch_toss_order_import_runs(db, account_seq=normalized)
    ]


@router.get("/orders", response_model=list[TossOrderResponse])
def list_imported_toss_orders(
    db: Db,
    account_seq: AccountSeq,
    symbol: str | None = None,
    order_status: str | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[TossOrderResponse]:
    normalized = normalize_account_seq(account_seq)
    return [
        TossOrderResponse(**row_to_dict(row))
        for row in fetch_toss_orders(
            db,
            account_seq=normalized,
            symbol=symbol.strip().upper() if symbol else None,
            order_status=order_status.strip() if order_status else None,
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
        )
    ]
```

- [ ] **Step 6: Keep architecture guard strict**

In `backend/tests/test_toss_only_architecture.py`, assert:

```python
assert "/api/toss/orders" in combined
assert "/api/transactions" not in combined
```

Do not re-add `/api/transactions` to allowed paths.

- [ ] **Step 7: Run backend API tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py backend/tests/test_toss_only_architecture.py -q
```

Expected: PASS.

---

## Task 5: Frontend Order History Screen

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/OrderHistoryPage.tsx`
- Create: `frontend/tests/toss-order-history-page.test.mjs`

- [ ] **Step 1: Write failing source test**

Create `frontend/tests/toss-order-history-page.test.mjs`:

```javascript
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const page = readFileSync(
  new URL("../src/components/OrderHistoryPage.tsx", import.meta.url),
  "utf8",
)
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shell = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

assert.ok(app.includes("OrderHistoryPage"), "App should mount the Toss order history page")
assert.ok(shell.includes("주문내역"), "Navigation should expose order history")
assert.ok(page.includes("/api/toss/accounts"), "Order history should load Toss accounts")
assert.ok(page.includes("/api/toss/order-imports"), "Order history should trigger imports")
assert.ok(page.includes("/api/toss/orders"), "Order history should list imported orders")
assert.ok(page.includes("account_seq"), "Order history should use Toss account sequence")
assert.ok(page.includes("OPEN"), "Order history should expose OPEN status import")
assert.ok(page.includes("CLOSED"), "Order history should expose CLOSED status with provider limitation")
assert.ok(!page.includes("/api/transactions"), "Order history must not use the removed local transaction API")
```

- [ ] **Step 2: Run failing frontend test**

Run:

```bash
cd frontend && node tests/toss-order-history-page.test.mjs
```

Expected: FAIL because the page does not exist.

- [ ] **Step 3: Add frontend types**

Add to `frontend/src/types.ts`:

```ts
export type TossOrder = {
  id: number
  account_seq: string
  order_id: string
  symbol: string
  side: string
  order_type: string
  time_in_force: string
  order_status: string
  price: string | null
  quantity: string
  order_amount: string | null
  currency: string
  ordered_at: string
  canceled_at: string | null
  filled_quantity: string
  average_filled_price: string | null
  filled_amount: string | null
  commission: string | null
  tax: string | null
  filled_at: string | null
  settlement_date: string | null
  imported_at: string
  updated_at: string
}

export type TossOrderImportRun = {
  id: number
  account_seq: string
  status_filter: "OPEN" | "CLOSED"
  symbol_filter: string | null
  from_date: string | null
  to_date: string | null
  run_status: "running" | "success" | "failed"
  imported_count: number
  error_message: string
  started_at: string
  completed_at: string | null
}
```

- [ ] **Step 4: Create `OrderHistoryPage.tsx`**

Create `frontend/src/components/OrderHistoryPage.tsx` with the same account-loading pattern as `HoldingsPage.tsx`, using:

```ts
apiGet<TossAccount[]>("/api/toss/accounts")
apiPost<TossOrderImportRun>("/api/toss/order-imports", payload)
apiGet<TossOrder[]>(`/api/toss/orders?account_seq=${encodeURIComponent(selectedAccountSeq)}`)
apiGet<TossOrderImportRun[]>(`/api/toss/order-imports?account_seq=${encodeURIComponent(selectedAccountSeq)}`)
```

The UI should include:

- Toss account selector.
- Status selector with `OPEN` and `CLOSED`.
- Optional symbol, from-date, to-date filters.
- Import button.
- Latest import run status.
- Imported order table columns: ordered time, symbol, side, status, quantity, price, filled quantity, filled amount, commission, tax, settlement date.
- Error message area.
- A small note near `CLOSED`: `Toss Open API 1.1.5 문서상 CLOSED 목록은 현재 지원되지 않을 수 있습니다.`

- [ ] **Step 5: Mount page and nav**

In `frontend/src/App.tsx`, import and mount:

```tsx
import { OrderHistoryPage } from "./components/OrderHistoryPage"
```

```tsx
{active === "orders" && <OrderHistoryPage />}
```

In `frontend/src/components/AppShell.tsx`, add a lucide icon import and nav item:

```tsx
import { BarChart3, Database, Flag, ReceiptText, Settings } from "lucide-react"
```

```tsx
{ id: "orders", label: "주문내역", icon: ReceiptText },
```

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

---

## Task 6: Documentation And Full Verification

**Files:**
- Modify: `docs/toss-open-api-integration.md`
- Modify: `README.md`

- [ ] **Step 1: Update Toss integration doc**

In `docs/toss-open-api-integration.md`:

- Add `GET /api/v1/orders` and `GET /api/v1/orders/{orderId}` to APIs in use.
- Add local tables `toss_order_import_runs` and `toss_orders` to the persistence boundary.
- State that imported order history is read-only and does not drive current holdings valuation.
- Keep order placement in future work.
- Document that CLOSED import can fail while Toss OpenAPI reports `closed-not-supported`.

- [ ] **Step 2: Update README if stale**

The current README still describes the old local personal-finance MVP. Update it so it does not claim active local transaction/growth/market-sync workflows if the current code no longer exposes them.

- [ ] **Step 3: Run backend checks**

Run from repository root:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend
```

Expected: PASS.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: PASS.

- [ ] **Step 5: Optional live smoke test**

Only if Toss credentials are configured and the user approves a live read-only check:

```bash
.venv/bin/python -m uvicorn portfolio_app.asgi:app --host 127.0.0.1 --port 8000
```

Then use the frontend or a read-only API request to import `OPEN` orders for a selected account. Do not test order placement, cancel, or modify endpoints.

---

## Recommended Commit Slices

1. `feat: add toss order history schema`
2. `feat: parse toss order history responses`
3. `feat: import toss order history`
4. `feat: show toss order history`
5. `docs: document toss order history import`

If checkpointing is requested, stop after each commit-sized task and wait for user inspection before committing or moving on.

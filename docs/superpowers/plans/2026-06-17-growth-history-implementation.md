# Growth History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily net worth snapshots and monthly/annual growth history where deposits, withdrawals, and debt payments are excluded from return while dividends and interest are included.

**Architecture:** Add a `portfolio_snapshots` table and keep monthly/annual growth as computed API output instead of persisted aggregates. Reuse the existing summary calculation for valuation, then add a focused growth service that owns snapshot upserts, cashflow conversion, and period aggregation. The frontend gets a new `성장기록` screen that reads the growth API and can refresh today's snapshot.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, pytest, React 19, Vite, TypeScript, static Node-based frontend contract tests.

---

## File Structure

- Modify `backend/src/portfolio_app/schema.sql`
  - Add `portfolio_snapshots`.
- Modify `backend/src/portfolio_app/migrations.py`
  - Bump `SCHEMA_VERSION` from `5` to `6`.
  - Add `_migrate_from_5_to_6()`.
- Modify `backend/src/portfolio_app/models.py`
  - Add `SnapshotSource`, `GrowthPeriod`, `PortfolioSnapshot`, and `GrowthHistoryRow`.
- Create `backend/src/portfolio_app/services/growth.py`
  - KST date handling, snapshot upsert/listing, transaction cashflow conversion, monthly/annual aggregation.
- Create `backend/src/portfolio_app/api/growth.py`
  - Growth snapshot and history endpoints.
- Modify `backend/src/portfolio_app/main.py`
  - Register the growth router.
- Modify `backend/src/portfolio_app/api/market_data.py`
  - Create today's snapshot after sync when summary valuation is usable.
- Modify `backend/tests/test_db.py`
  - Lock schema version 6 and migration behavior.
- Create `backend/tests/test_growth.py`
  - Unit-test snapshot and growth calculations without HTTP.
- Create `backend/tests/test_growth_api.py`
  - Test public API contracts.
- Modify `backend/tests/test_market_data.py`
  - Verify market sync creates or reports a snapshot.
- Modify `frontend/src/types.ts`
  - Add snapshot and growth row response types.
- Create `frontend/src/components/GrowthHistoryPage.tsx`
  - Render monthly and annual growth tables plus manual snapshot refresh.
- Modify `frontend/src/App.tsx`
  - Render the growth screen.
- Modify `frontend/src/components/AppShell.tsx`
  - Add the `성장기록` navigation item.
- Modify `frontend/src/styles.css`
  - Add focused growth status and signed-rate styles.
- Create `frontend/tests/growth-history-page.test.mjs`
  - Static frontend contract test for the new screen.
- Modify `frontend/package.json`
  - Add the growth test to `npm test`.

---

## Task 1: Schema, Migration, And Model Contracts

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/tests/test_db.py`

- [ ] **Step 1: Write failing schema tests**

Update `backend/tests/test_db.py`.

Change `test_migrate_creates_core_tables()` so the expected table set includes `portfolio_snapshots`:

```python
assert {
    "schema_migrations",
    "accounts",
    "assets",
    "holdings",
    "transactions",
    "price_snapshots",
    "fx_rates",
    "goals",
    "backups",
    "settings",
    "portfolio_snapshots",
}.issubset(table_names(db))
```

Change every schema version assertion in `backend/tests/test_db.py` from the old terminal version to version 6:

```python
assert migration_versions(db) == [6]
```

For upgrade-chain tests, preserve prior versions and append `6`:

```python
assert migration_versions(db) == [4, 5, 6]
assert migration_versions(db) == [2, 3, 4, 5, 6]
```

Change the newer-schema rejection setup to insert version 7:

```python
db.execute("insert into schema_migrations(version) values (7)")
```

Add this test near the other migration tests:

```python
def test_migrate_upgrades_version_5_database_with_portfolio_snapshots(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        create table accounts (
          id integer primary key,
          name text not null,
          type text not null check (type in ('cash','savings','brokerage','debt')),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        insert into schema_migrations(version) values (5);
        """
    )
    db.commit()

    migrate(db)

    columns = {
        row["name"]
        for row in db.execute("pragma table_info(portfolio_snapshots)").fetchall()
    }
    assert migration_versions(db) == [5, 6]
    assert {
        "id",
        "snapshot_date",
        "net_worth_krw",
        "gross_assets_krw",
        "debt_krw",
        "monthly_income_krw",
        "asset_mix_json",
        "source",
        "created_at",
        "updated_at",
    }.issubset(columns)
```

Add this constraint test:

```python
def test_portfolio_snapshots_enforce_unique_kst_date(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-06-17", 1_000_000, 1_000_000, 0, 0, "{}", "manual"),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            insert into portfolio_snapshots(
              snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
              monthly_income_krw, asset_mix_json, source
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-17", 2_000_000, 2_000_000, 0, 0, "{}", "manual"),
        )
```

- [ ] **Step 2: Run schema tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py -q
```

Expected: FAIL because `portfolio_snapshots` does not exist and schema version is still `5`.

- [ ] **Step 3: Add the snapshot table**

Append this table to `backend/src/portfolio_app/schema.sql` after `settings`:

```sql
create table if not exists portfolio_snapshots (
  id integer primary key,
  snapshot_date text not null unique,
  net_worth_krw real not null,
  gross_assets_krw real not null check (gross_assets_krw >= 0),
  debt_krw real not null check (debt_krw >= 0),
  monthly_income_krw real not null default 0 check (monthly_income_krw >= 0),
  asset_mix_json text not null default '{}',
  source text not null check (source in ('scheduled','manual','market_sync','import')),
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);
```

- [ ] **Step 4: Add migration version 6**

In `backend/src/portfolio_app/migrations.py`, change:

```python
SCHEMA_VERSION = 6
```

Add this function after `_migrate_from_4_to_5()`:

```python
def _migrate_from_5_to_6(db: sqlite3.Connection) -> None:
    with db:
        db.execute(
            """
            create table if not exists portfolio_snapshots (
              id integer primary key,
              snapshot_date text not null unique,
              net_worth_krw real not null,
              gross_assets_krw real not null check (gross_assets_krw >= 0),
              debt_krw real not null check (debt_krw >= 0),
              monthly_income_krw real not null default 0 check (monthly_income_krw >= 0),
              asset_mix_json text not null default '{}',
              source text not null check (source in ('scheduled','manual','market_sync','import')),
              created_at text not null default current_timestamp,
              updated_at text not null default current_timestamp
            )
            """
        )
        db.execute("insert or ignore into schema_migrations(version) values (6)")
```

In `migrate()`, append this block after the version 4 migration block:

```python
if version == 5:
    _migrate_from_5_to_6(db)
    version = 6
```

- [ ] **Step 5: Add response models**

In `backend/src/portfolio_app/models.py`, extend the imports:

```python
from datetime import date
from typing import Literal
```

Keep the existing `AssetType` and `GoalType`, then add:

```python
SnapshotSource = Literal["scheduled", "manual", "market_sync", "import"]
GrowthPeriod = Literal["monthly", "annual"]
```

Append these models after `PortfolioSummary`:

```python
class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    snapshot_date: date
    net_worth_krw: float = Field(allow_inf_nan=False)
    gross_assets_krw: float = Field(ge=0, allow_inf_nan=False)
    debt_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(ge=0, allow_inf_nan=False)
    asset_mix: dict[str, float]
    source: SnapshotSource
    created_at: str
    updated_at: str


class GrowthHistoryRow(BaseModel):
    model_config = ConfigDict(strict=True)

    period: str
    start_date: date
    end_date: date
    starting_net_worth_krw: float = Field(allow_inf_nan=False)
    ending_net_worth_krw: float = Field(allow_inf_nan=False)
    external_cash_flow_krw: float = Field(allow_inf_nan=False)
    dividend_interest_krw: float = Field(ge=0, allow_inf_nan=False)
    profit_krw: float = Field(allow_inf_nan=False)
    growth_rate: float | None = Field(default=None, allow_inf_nan=False)
    cumulative_profit_krw: float = Field(allow_inf_nan=False)
    cumulative_growth_rate: float | None = Field(default=None, allow_inf_nan=False)
```

- [ ] **Step 6: Run schema tests and Ruff**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/schema.sql backend/src/portfolio_app/migrations.py backend/src/portfolio_app/models.py backend/tests/test_db.py
```

Expected: `backend/tests/test_db.py` passes. Ruff reports no Python issues; if Ruff ignores `.sql`, rerun only with Python paths:

```bash
.venv/bin/python -m ruff check backend/src/portfolio_app/migrations.py backend/src/portfolio_app/models.py backend/tests/test_db.py
```

- [ ] **Step 7: Commit schema and model contracts**

```bash
git add backend/src/portfolio_app/schema.sql backend/src/portfolio_app/migrations.py backend/src/portfolio_app/models.py backend/tests/test_db.py
git commit -m "feat: add portfolio snapshot schema"
```

---

## Task 2: Growth Service Calculations

**Files:**
- Create: `backend/src/portfolio_app/services/growth.py`
- Create: `backend/tests/test_growth.py`

- [ ] **Step 1: Write failing growth service tests**

Create `backend/tests/test_growth.py`:

```python
from datetime import date

import pytest

from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, upsert_holding
from portfolio_app.services.growth import (
    build_growth_history,
    create_or_refresh_today_snapshot,
)


def create_growth_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def builtin_asset_id(db, *, asset_type: str, currency: str = "KRW") -> int:
    row = db.execute(
        """
        select id
        from assets
        where type = ?
          and currency = ?
          and symbol is null
          and market is null
        order by id
        limit 1
        """,
        (asset_type, currency),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def insert_snapshot(db, snapshot_date: str, net_worth_krw: float) -> None:
    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_date, net_worth_krw, max(net_worth_krw, 0), 0, 0, "{}", "manual"),
    )
    db.commit()


def insert_transaction(db, occurred_on: str, transaction_type: str, amount: float) -> None:
    db.execute(
        """
        insert into transactions(occurred_on, type, amount, currency, memo)
        values (?, ?, ?, ?, ?)
        """,
        (occurred_on, transaction_type, amount, "KRW", transaction_type),
    )
    db.commit()


def test_create_or_refresh_today_snapshot_updates_one_kst_date(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        account_id = create_account(db, name="원화 현금", type="cash")
        cash_asset_id = builtin_asset_id(db, asset_type="cash")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_000_000,
            average_cost=None,
        )

        first = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_500_000,
            average_cost=None,
        )
        second = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        count = db.execute("select count(*) from portfolio_snapshots").fetchone()[0]
    finally:
        db.close()

    assert count == 1
    assert first.id == second.id
    assert first.net_worth_krw == 1_000_000
    assert second.net_worth_krw == 1_500_000
    assert second.snapshot_date == date(2026, 6, 17)


def test_create_or_refresh_today_snapshot_can_keep_existing_row(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        account_id = create_account(db, name="원화 현금", type="cash")
        cash_asset_id = builtin_asset_id(db, asset_type="cash")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=1_000_000,
            average_cost=None,
        )
        first = create_or_refresh_today_snapshot(
            db,
            source="manual",
            today=date(2026, 6, 17),
        )
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=cash_asset_id,
            quantity=2_000_000,
            average_cost=None,
        )
        second = create_or_refresh_today_snapshot(
            db,
            source="market_sync",
            today=date(2026, 6, 17),
            refresh=False,
        )
    finally:
        db.close()

    assert second.id == first.id
    assert second.net_worth_krw == 1_000_000
    assert second.source == "manual"


def test_monthly_history_excludes_external_cashflow_and_includes_income(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 56_200_000)
        insert_transaction(db, "2026-06-05", "deposit", 5_000_000)
        insert_transaction(db, "2026-06-12", "withdrawal", 1_000_000)
        insert_transaction(db, "2026-06-20", "dividend", 200_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert len(rows) == 1
    row = rows[0]
    assert row.period == "2026-06"
    assert row.external_cash_flow_krw == 4_000_000
    assert row.dividend_interest_krw == 200_000
    assert row.profit_krw == 2_200_000
    assert row.growth_rate == pytest.approx(0.044)
    assert row.cumulative_profit_krw == 2_200_000
    assert row.cumulative_growth_rate == pytest.approx(0.044)


def test_monthly_history_excludes_debt_payments_from_profit(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 51_000_000)
        insert_transaction(db, "2026-06-15", "debt_payment", 1_000_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert rows[0].external_cash_flow_krw == 1_000_000
    assert rows[0].profit_krw == 0
    assert rows[0].growth_rate == 0


def test_growth_rate_is_missing_when_starting_net_worth_is_zero(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-06-01", 0)
        insert_snapshot(db, "2026-06-30", 1_000_000)

        rows = build_growth_history(
            db,
            period="monthly",
            from_value="2026-06",
            to_value="2026-06",
        )
    finally:
        db.close()

    assert rows[0].profit_krw == 1_000_000
    assert rows[0].growth_rate is None
    assert rows[0].cumulative_growth_rate is None


def test_annual_history_uses_annual_snapshots_and_cashflow(tmp_path):
    db = create_growth_db(tmp_path)
    try:
        insert_snapshot(db, "2026-01-02", 10_000_000)
        insert_snapshot(db, "2026-12-30", 11_300_000)
        insert_transaction(db, "2026-03-01", "deposit", 1_000_000)
        insert_transaction(db, "2026-09-01", "interest", 300_000)

        rows = build_growth_history(
            db,
            period="annual",
            from_value="2026",
            to_value="2026",
        )
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].period == "2026"
    assert rows[0].external_cash_flow_krw == 1_000_000
    assert rows[0].dividend_interest_krw == 300_000
    assert rows[0].profit_krw == 300_000
    assert rows[0].growth_rate == pytest.approx(0.03)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth.py -q
```

Expected: FAIL because `portfolio_app.services.growth` does not exist.

- [ ] **Step 3: Implement the growth service**

Create `backend/src/portfolio_app/services/growth.py`:

```python
import json
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_app.api.summary import build_summary
from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource

KST = ZoneInfo("Asia/Seoul")
EXTERNAL_CONTRIBUTION_TYPES = {"deposit", "debt_payment"}
EXTERNAL_WITHDRAWAL_TYPES = {"withdrawal"}
INCOME_TYPES = {"dividend", "interest"}


def today_kst(now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(KST).date()


def _snapshot_from_row(row: sqlite3.Row) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=int(row["id"]),
        snapshot_date=date.fromisoformat(str(row["snapshot_date"])),
        net_worth_krw=float(row["net_worth_krw"]),
        gross_assets_krw=float(row["gross_assets_krw"]),
        debt_krw=float(row["debt_krw"]),
        monthly_income_krw=float(row["monthly_income_krw"]),
        asset_mix=json.loads(str(row["asset_mix_json"])),
        source=row["source"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _fetch_snapshot_by_date(db: sqlite3.Connection, snapshot_date: date) -> PortfolioSnapshot | None:
    row = db.execute(
        "select * from portfolio_snapshots where snapshot_date = ?",
        (snapshot_date.isoformat(),),
    ).fetchone()
    if row is None:
        return None
    return _snapshot_from_row(row)


def create_or_refresh_today_snapshot(
    db: sqlite3.Connection,
    *,
    source: SnapshotSource = "manual",
    today: date | None = None,
    refresh: bool = True,
) -> PortfolioSnapshot:
    snapshot_date = today or today_kst()
    existing = _fetch_snapshot_by_date(db, snapshot_date)
    if existing is not None and not refresh:
        return existing

    summary, asset_mix, _asset_allocations = build_summary(db, today=snapshot_date)
    asset_mix_json = json.dumps(asset_mix, ensure_ascii=False, sort_keys=True)

    with db:
        db.execute(
            """
            insert into portfolio_snapshots(
              snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
              monthly_income_krw, asset_mix_json, source
            )
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(snapshot_date)
            do update set net_worth_krw = excluded.net_worth_krw,
                          gross_assets_krw = excluded.gross_assets_krw,
                          debt_krw = excluded.debt_krw,
                          monthly_income_krw = excluded.monthly_income_krw,
                          asset_mix_json = excluded.asset_mix_json,
                          source = excluded.source,
                          updated_at = current_timestamp
            """,
            (
                snapshot_date.isoformat(),
                summary.net_worth_krw,
                summary.gross_assets_krw,
                summary.debt_krw,
                summary.monthly_income_krw,
                asset_mix_json,
                source,
            ),
        )

    snapshot = _fetch_snapshot_by_date(db, snapshot_date)
    if snapshot is None:
        raise RuntimeError("오늘의 성장 기록 스냅샷을 찾을 수 없습니다.")
    return snapshot


def list_snapshots(
    db: sqlite3.Connection,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[PortfolioSnapshot]:
    clauses: list[str] = []
    params: list[str] = []
    if from_date is not None:
        clauses.append("snapshot_date >= ?")
        params.append(from_date.isoformat())
    if to_date is not None:
        clauses.append("snapshot_date <= ?")
        params.append(to_date.isoformat())

    where = f"where {' and '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"select * from portfolio_snapshots {where} order by snapshot_date, id",
        params,
    ).fetchall()
    return [_snapshot_from_row(row) for row in rows]


def _parse_month(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def _parse_period_start(period: GrowthPeriod, value: str | None) -> date | None:
    if value is None:
        return None
    if period == "monthly":
        return _parse_month(value)
    return date(int(value), 1, 1)


def _parse_period_end(period: GrowthPeriod, value: str | None) -> date | None:
    if value is None:
        return None
    if period == "monthly":
        start = _parse_month(value)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        return next_month - timedelta(days=1)
    return date(int(value), 12, 31)


def _period_key(snapshot_date: date, period: GrowthPeriod) -> str:
    if period == "monthly":
        return snapshot_date.strftime("%Y-%m")
    return snapshot_date.strftime("%Y")


def _period_bounds(key: str, period: GrowthPeriod) -> tuple[str, str]:
    if period == "monthly":
        start = _parse_month(key)
        if start.month == 12:
            end = date(start.year + 1, 1, 1)
        else:
            end = date(start.year, start.month + 1, 1)
        return start.isoformat(), end.isoformat()

    year = int(key)
    return date(year, 1, 1).isoformat(), date(year + 1, 1, 1).isoformat()


def _amount_to_krw(row: sqlite3.Row) -> float:
    amount = float(row["amount"] or 0)
    currency = str(row["currency"]).upper()
    if currency == "KRW" or amount == 0:
        return amount

    rate = row["fx_rate_to_krw"]
    if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
        raise ValueError(f"{currency} 거래의 성장률 계산에 필요한 환율 정보가 없습니다.")
    return amount * float(rate)


def _period_cashflow(db: sqlite3.Connection, *, start: str, end: str) -> tuple[float, float]:
    rows = db.execute(
        """
        select type, amount, currency, fx_rate_to_krw
        from transactions
        where occurred_on >= ?
          and occurred_on < ?
          and type in ('deposit', 'withdrawal', 'debt_payment', 'dividend', 'interest')
        order by occurred_on, id
        """,
        (start, end),
    ).fetchall()
    external_cash_flow = 0.0
    dividend_interest = 0.0

    for row in rows:
        amount_krw = _amount_to_krw(row)
        transaction_type = str(row["type"])
        if transaction_type in EXTERNAL_CONTRIBUTION_TYPES:
            external_cash_flow += amount_krw
        elif transaction_type in EXTERNAL_WITHDRAWAL_TYPES:
            external_cash_flow -= amount_krw
        elif transaction_type in INCOME_TYPES:
            dividend_interest += amount_krw

    return external_cash_flow, dividend_interest


def build_growth_history(
    db: sqlite3.Connection,
    *,
    period: GrowthPeriod,
    from_value: str | None = None,
    to_value: str | None = None,
) -> list[GrowthHistoryRow]:
    from_date = _parse_period_start(period, from_value)
    to_date = _parse_period_end(period, to_value)
    snapshots = list_snapshots(db, from_date=from_date, to_date=to_date)

    grouped: dict[str, list[PortfolioSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[_period_key(snapshot.snapshot_date, period)].append(snapshot)

    rows: list[GrowthHistoryRow] = []
    cumulative_external_cash_flow = 0.0
    first_baseline: float | None = None
    latest_ending: float | None = None

    for key in sorted(grouped):
        period_snapshots = grouped[key]
        starting = period_snapshots[0]
        ending = period_snapshots[-1]
        start_bound, end_bound = _period_bounds(key, period)
        external_cash_flow, dividend_interest = _period_cashflow(
            db,
            start=start_bound,
            end=end_bound,
        )
        profit = ending.net_worth_krw - starting.net_worth_krw - external_cash_flow
        growth_rate = profit / starting.net_worth_krw if starting.net_worth_krw > 0 else None

        if first_baseline is None:
            first_baseline = starting.net_worth_krw if starting.net_worth_krw > 0 else None
        cumulative_external_cash_flow += external_cash_flow
        latest_ending = ending.net_worth_krw
        cumulative_profit = (
            latest_ending - first_baseline - cumulative_external_cash_flow
            if first_baseline is not None
            else profit
        )
        cumulative_growth_rate = (
            cumulative_profit / first_baseline
            if first_baseline is not None and first_baseline > 0
            else None
        )

        rows.append(
            GrowthHistoryRow(
                period=key,
                start_date=starting.snapshot_date,
                end_date=ending.snapshot_date,
                starting_net_worth_krw=starting.net_worth_krw,
                ending_net_worth_krw=ending.net_worth_krw,
                external_cash_flow_krw=external_cash_flow,
                dividend_interest_krw=dividend_interest,
                profit_krw=profit,
                growth_rate=growth_rate,
                cumulative_profit_krw=cumulative_profit,
                cumulative_growth_rate=cumulative_growth_rate,
            )
        )

    return rows
```

- [ ] **Step 4: Run growth service tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py
```

Expected: tests pass and Ruff reports no issues.

- [ ] **Step 5: Commit growth service**

```bash
git add backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py
git commit -m "feat: calculate growth history"
```

---

## Task 3: Growth API Endpoints

**Files:**
- Create: `backend/src/portfolio_app/api/growth.py`
- Modify: `backend/src/portfolio_app/main.py`
- Create: `backend/tests/test_growth_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_growth_api.py`:

```python
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def insert_snapshot(db, snapshot_date: str, net_worth_krw: float) -> None:
    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_date, net_worth_krw, max(net_worth_krw, 0), 0, 0, "{}", "manual"),
    )
    db.commit()


def test_create_today_snapshot_endpoint_returns_snapshot(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post("/api/growth/snapshots/today", json={"source": "manual"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["snapshot_date"]
    assert payload["net_worth_krw"] == 0
    assert payload["gross_assets_krw"] == 0
    assert payload["debt_krw"] == 0
    assert payload["asset_mix"] == {}
    assert payload["source"] == "manual"


def test_list_snapshots_endpoint_returns_date_order(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
    try:
        insert_snapshot(db, "2026-06-02", 2_000_000)
        insert_snapshot(db, "2026-06-01", 1_000_000)
    finally:
        db.close()

    response = client.get("/api/growth/snapshots?from=2026-06-01&to=2026-06-30")

    assert response.status_code == 200
    assert [row["snapshot_date"] for row in response.json()] == ["2026-06-01", "2026-06-02"]


def test_growth_history_endpoint_returns_monthly_rows(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
    try:
        insert_snapshot(db, "2026-06-01", 50_000_000)
        insert_snapshot(db, "2026-06-30", 56_200_000)
        db.execute(
            """
            insert into transactions(occurred_on, type, amount, currency, memo)
            values (?, ?, ?, ?, ?)
            """,
            ("2026-06-05", "deposit", 5_000_000, "KRW", "입금"),
        )
        db.execute(
            """
            insert into transactions(occurred_on, type, amount, currency, memo)
            values (?, ?, ?, ?, ?)
            """,
            ("2026-06-20", "dividend", 200_000, "KRW", "배당"),
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/growth/history?period=monthly&from=2026-06&to=2026-06")

    assert response.status_code == 200
    assert response.json()[0]["period"] == "2026-06"
    assert response.json()[0]["external_cash_flow_krw"] == 5_000_000
    assert response.json()[0]["dividend_interest_krw"] == 200_000
    assert response.json()[0]["profit_krw"] == 1_200_000
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth_api.py -q
```

Expected: FAIL with 404 or import errors because the growth router does not exist.

- [ ] **Step 3: Implement growth API**

Create `backend/src/portfolio_app/api/growth.py`:

```python
import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import get_db
from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource
from portfolio_app.services.growth import (
    build_growth_history,
    create_or_refresh_today_snapshot,
    list_snapshots,
)

router = APIRouter(prefix="/api/growth", tags=["growth"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class TodaySnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SnapshotSource = "manual"


@router.post(
    "/snapshots/today",
    response_model=PortfolioSnapshot,
    status_code=status.HTTP_201_CREATED,
)
def create_today_snapshot(payload: TodaySnapshotRequest, db: Db) -> PortfolioSnapshot:
    try:
        return create_or_refresh_today_snapshot(db, source=payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/snapshots", response_model=list[PortfolioSnapshot])
def get_snapshots(
    db: Db,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[PortfolioSnapshot]:
    return list_snapshots(db, from_date=from_date, to_date=to_date)


@router.get("/history", response_model=list[GrowthHistoryRow])
def get_growth_history(
    db: Db,
    period: GrowthPeriod,
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
) -> list[GrowthHistoryRow]:
    try:
        return build_growth_history(
            db,
            period=period,
            from_value=from_value,
            to_value=to_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

- [ ] **Step 4: Register the router**

In `backend/src/portfolio_app/main.py`, add `growth` to the API imports:

```python
from portfolio_app.api import (
    accounts,
    assets,
    backups,
    goals,
    growth,
    market_data,
    summary,
    transactions,
)
```

Add the router before `market_data`:

```python
app.include_router(growth.router)
```

- [ ] **Step 5: Run API tests and Ruff**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth_api.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/api/growth.py backend/src/portfolio_app/main.py backend/tests/test_growth_api.py
```

Expected: tests pass and Ruff reports no issues.

- [ ] **Step 6: Commit growth API**

```bash
git add backend/src/portfolio_app/api/growth.py backend/src/portfolio_app/main.py backend/tests/test_growth_api.py
git commit -m "feat: expose growth history api"
```

---

## Task 4: Automatic Snapshot After Market Sync

**Files:**
- Modify: `backend/src/portfolio_app/api/market_data.py`
- Modify: `backend/tests/test_market_data.py`

- [ ] **Step 1: Write failing market sync snapshot test**

In `backend/tests/test_market_data.py`, update `test_sync_records_stale_status_when_alpha_vantage_key_missing()` after the existing summary assertion:

```python
payload = response.json()
assert payload["snapshot"]["source"] == "market_sync"
assert payload["snapshot"]["net_worth_krw"] == 700_000

db = connect(client.app.state.settings.database_path)
try:
    count = db.execute("select count(*) from portfolio_snapshots").fetchone()[0]
finally:
    db.close()

assert count == 1
```

Add this test to ensure an unusable valuation reports a snapshot error without crashing the sync response:

```python
def test_sync_reports_snapshot_error_when_summary_cannot_be_valued(tmp_path):
    client = create_test_client(tmp_path)
    account = client.post(
        "/api/accounts",
        json={"name": "달러 현금", "type": "cash"},
    ).json()
    usd_cash = next(
        asset
        for asset in client.get("/api/assets").json()
        if asset["type"] == "cash" and asset["currency"] == "USD"
    )
    client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-17",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": usd_cash["id"],
            "quantity": None,
            "amount": 1_000,
            "currency": "USD",
            "memo": "환율 없는 달러 현금",
        },
    )

    response = client.post("/api/market-data/sync")

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "snapshot_error" in response.json()
    assert "환율" in response.json()["snapshot_error"]
```

- [ ] **Step 2: Run market data tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_market_data.py::test_sync_records_stale_status_when_alpha_vantage_key_missing backend/tests/test_market_data.py::test_sync_reports_snapshot_error_when_summary_cannot_be_valued -q
```

Expected: FAIL because `/api/market-data/sync` does not return `snapshot` or `snapshot_error`.

- [ ] **Step 3: Create a snapshot after market sync**

In `backend/src/portfolio_app/api/market_data.py`, add imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_app.services.growth import create_or_refresh_today_snapshot
```

Keep the existing `HTTPException` import if it is already present through the FastAPI import line.

At the end of `sync_market_data_for_settings()`, replace:

```python
return {"results": results}
```

with:

```python
response: dict[str, object] = {"results": results}
try:
    snapshot = create_or_refresh_today_snapshot(db, source="market_sync", refresh=False)
    response["snapshot"] = snapshot.model_dump(mode="json")
except (HTTPException, ValueError, sqlite3.Error) as exc:
    response["snapshot_error"] = str(exc.detail if isinstance(exc, HTTPException) else exc)

return response
```

Change the function return annotation from:

```python
) -> dict[str, list[dict[str, object]]]:
```

to:

```python
) -> dict[str, object]:
```

Change `sync_market_data()` return annotation to:

```python
def sync_market_data(request: Request, db: Db) -> dict[str, object]:
```

- [ ] **Step 4: Run market data tests and Ruff**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_market_data.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/api/market_data.py backend/tests/test_market_data.py
```

Expected: tests pass and Ruff reports no issues.

- [ ] **Step 5: Commit automatic snapshot trigger**

```bash
git add backend/src/portfolio_app/api/market_data.py backend/tests/test_market_data.py
git commit -m "feat: snapshot after market sync"
```

---

## Task 5: Growth History Frontend

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/GrowthHistoryPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/growth-history-page.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write failing frontend contract test**

Create `frontend/tests/growth-history-page.test.mjs`:

```javascript
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shell = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const source = readFileSync(new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url), "utf8")
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const types = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const packageJson = readFileSync(new URL("../package.json", import.meta.url), "utf8")

assert.ok(types.includes("export type PortfolioSnapshot"), "types should expose portfolio snapshots")
assert.ok(types.includes("export type GrowthHistoryRow"), "types should expose growth history rows")
assert.ok(source.includes('"/api/growth/history?period=monthly"'), "page should load monthly history")
assert.ok(source.includes('"/api/growth/history?period=annual"'), "page should load annual history")
assert.ok(source.includes('"/api/growth/snapshots/today"'), "page should refresh today's snapshot")
assert.ok(source.includes("apiPost<PortfolioSnapshot>"), "manual refresh should use the snapshot API")
assert.ok(source.includes("formatPercent"), "page should format growth rates")
assert.ok(source.includes('rate === null ? "-"'), "missing growth rates should render as dash")
assert.ok(source.includes("배당/이자"), "page should show dividend and interest")
assert.ok(source.includes("순입금"), "page should show external cashflow")
assert.ok(source.includes("월별 성장률"), "page should render monthly section")
assert.ok(source.includes("연간 성장률"), "page should render annual section")
assert.ok(shell.includes("성장기록"), "sidebar should include growth history navigation")
assert.ok(app.includes('<GrowthHistoryPage />'), "app should render growth history screen")
assert.ok(styles.includes(".growth-status"), "growth page should have status styling")
assert.ok(styles.includes(".signed-positive"), "growth page should style positive values")
assert.ok(styles.includes(".signed-negative"), "growth page should style negative values")
assert.ok(packageJson.includes("growth-history-page.test.mjs"), "npm test should include growth test")
```

- [ ] **Step 2: Run frontend test and verify failure**

Run:

```bash
cd frontend && node tests/growth-history-page.test.mjs
```

Expected: FAIL because `GrowthHistoryPage.tsx` does not exist.

- [ ] **Step 3: Add frontend response types**

Append to `frontend/src/types.ts`:

```typescript
export type PortfolioSnapshot = {
  id: number
  snapshot_date: string
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  asset_mix: Record<string, number>
  source: "scheduled" | "manual" | "market_sync" | "import"
  created_at: string
  updated_at: string
}

export type GrowthHistoryRow = {
  period: string
  start_date: string
  end_date: string
  starting_net_worth_krw: number
  ending_net_worth_krw: number
  external_cash_flow_krw: number
  dividend_interest_krw: number
  profit_krw: number
  growth_rate: number | null
  cumulative_profit_krw: number
  cumulative_growth_rate: number | null
}
```

- [ ] **Step 4: Create growth history page**

Create `frontend/src/components/GrowthHistoryPage.tsx`:

```tsx
import { RefreshCw } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { apiGet, apiPost } from "../api"
import type { GrowthHistoryRow, PortfolioSnapshot } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatKrw = (value: number) =>
  `${value.toLocaleString("ko-KR", { maximumFractionDigits: 0 })} 원`

const formatPercent = (rate: number | null) =>
  rate === null ? "-" : `${(rate * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`

const signedClass = (value: number | null) => {
  if (value === null || value === 0) {
    return "signed-flat"
  }
  return value > 0 ? "signed-positive" : "signed-negative"
}

function GrowthTable({ rows, title }: { rows: GrowthHistoryRow[]; title: string }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h3>{title}</h3>
        <span>{rows.length.toLocaleString("ko-KR")}개 구간</span>
      </div>
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>구간</th>
                <th>시작</th>
                <th>종료</th>
                <th>순입금</th>
                <th>수익금</th>
                <th>성장률</th>
                <th>누적 수익률</th>
                <th>배당/이자</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.period}>
                  <td>{row.period}</td>
                  <td className="numeric-cell">{formatKrw(row.starting_net_worth_krw)}</td>
                  <td className="numeric-cell">{formatKrw(row.ending_net_worth_krw)}</td>
                  <td className="numeric-cell">{formatKrw(row.external_cash_flow_krw)}</td>
                  <td className={`numeric-cell ${signedClass(row.profit_krw)}`}>
                    {formatKrw(row.profit_krw)}
                  </td>
                  <td className={`numeric-cell ${signedClass(row.growth_rate)}`}>
                    {formatPercent(row.growth_rate)}
                  </td>
                  <td className={`numeric-cell ${signedClass(row.cumulative_growth_rate)}`}>
                    {formatPercent(row.cumulative_growth_rate)}
                  </td>
                  <td className="numeric-cell">{formatKrw(row.dividend_interest_krw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-state">성장 기록이 없습니다.</p>
      )}
    </section>
  )
}

export function GrowthHistoryPage() {
  const [monthlyRows, setMonthlyRows] = useState<GrowthHistoryRow[]>([])
  const [annualRows, setAnnualRows] = useState<GrowthHistoryRow[]>([])
  const [latestSnapshot, setLatestSnapshot] = useState<PortfolioSnapshot | null>(null)
  const [error, setError] = useState("")
  const [refreshMessage, setRefreshMessage] = useState("")
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadGrowthHistory = useCallback(async () => {
    const [monthly, annual] = await Promise.all([
      apiGet<GrowthHistoryRow[]>("/api/growth/history?period=monthly"),
      apiGet<GrowthHistoryRow[]>("/api/growth/history?period=annual"),
    ])
    setMonthlyRows(monthly)
    setAnnualRows(annual)
  }, [])

  useEffect(() => {
    loadGrowthHistory()
      .then(() => setError(""))
      .catch((err) => setError(getErrorMessage(err)))
  }, [loadGrowthHistory])

  const handleRefreshToday = async () => {
    setIsRefreshing(true)
    setRefreshMessage("")
    try {
      const snapshot = await apiPost<PortfolioSnapshot>("/api/growth/snapshots/today", {
        source: "manual",
      })
      setLatestSnapshot(snapshot)
      await loadGrowthHistory()
      setError("")
      setRefreshMessage(`${snapshot.snapshot_date} 스냅샷을 갱신했습니다.`)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsRefreshing(false)
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header growth-header">
        <div>
          <h2>성장기록</h2>
          <p>입금과 출금을 제외한 월별/연간 순자산 성장률을 확인합니다.</p>
        </div>
        <button className="secondary-action" disabled={isRefreshing} onClick={handleRefreshToday} type="button">
          <RefreshCw aria-hidden="true" size={16} />
          오늘 스냅샷 갱신
        </button>
      </header>

      {error && <div className="error">{error}</div>}
      {(latestSnapshot || refreshMessage) && (
        <div className="panel growth-status">
          <span>{refreshMessage || "최근 스냅샷"}</span>
          {latestSnapshot && <strong>{formatKrw(latestSnapshot.net_worth_krw)}</strong>}
        </div>
      )}

      <GrowthTable rows={monthlyRows} title="월별 성장률" />
      <GrowthTable rows={annualRows} title="연간 성장률" />
    </section>
  )
}
```

- [ ] **Step 5: Add navigation and rendering**

In `frontend/src/App.tsx`, add the import:

```typescript
import { GrowthHistoryPage } from "./components/GrowthHistoryPage"
```

Add the render branch:

```tsx
{active === "growth" && <GrowthHistoryPage />}
```

In `frontend/src/components/AppShell.tsx`, update the lucide import:

```typescript
import { BarChart3, Database, Flag, History, Settings, TrendingUp } from "lucide-react"
```

Add this nav item after `대시보드`:

```typescript
{ id: "growth", label: "성장기록", icon: TrendingUp },
```

- [ ] **Step 6: Add focused styles**

Append to `frontend/src/styles.css`:

```css
.growth-header {
  align-items: end;
  grid-template-columns: minmax(0, 1fr) auto;
}

.secondary-action {
  align-items: center;
  background: #111827;
  border: 0;
  border-radius: 8px;
  color: #ffffff;
  cursor: pointer;
  display: inline-flex;
  font-weight: 700;
  gap: 8px;
  min-height: 38px;
  padding: 8px 12px;
}

.secondary-action:disabled {
  cursor: wait;
  opacity: 0.64;
}

.growth-status {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.growth-status strong {
  color: #111827;
}

.signed-positive {
  color: #b91c1c;
  font-weight: 700;
}

.signed-negative {
  color: #1d4ed8;
  font-weight: 700;
}

.signed-flat {
  color: #475569;
}
```

- [ ] **Step 7: Add the frontend test to npm test**

In `frontend/package.json`, change the test script to:

```json
"test": "node tests/holdings-page-form.test.mjs && node tests/dashboard-currency-toggle.test.mjs && node tests/settings-market-sync.test.mjs && node tests/growth-history-page.test.mjs"
```

- [ ] **Step 8: Run frontend tests and build checks**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: all commands pass.

- [ ] **Step 9: Commit frontend growth history**

```bash
git add frontend/src/types.ts frontend/src/components/GrowthHistoryPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/styles.css frontend/tests/growth-history-page.test.mjs frontend/package.json
git commit -m "feat: add growth history screen"
```

---

## Task 6: Full Verification And Handoff

**Files:**
- No new files.
- Verify all files changed by Tasks 1-5.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py backend/tests/test_growth.py backend/tests/test_growth_api.py backend/tests/test_market_data.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full backend tests and Ruff**

Run:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend/src backend/tests
```

Expected: pytest passes and Ruff reports no issues.

- [ ] **Step 3: Run full frontend checks**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: all frontend checks pass.

- [ ] **Step 4: Run diff hygiene checks**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` has no output. `git status --short` shows only intentional files if the final commit has not been made.

- [ ] **Step 5: Commit final verification fixes if any file changed**

If formatting or verification fixes changed files, commit them:

```bash
git add backend frontend
git commit -m "test: verify growth history"
```

If no files changed after Task 5, do not create an empty commit.

- [ ] **Step 6: Handoff summary**

Report:

```text
Implemented growth history with daily KST snapshots, monthly/annual growth rows, market-sync snapshot creation, and a Korean growth history screen.
Verification:
- .venv/bin/python -m pytest backend/tests -q
- .venv/bin/python -m ruff check backend/src backend/tests
- cd frontend && npm test
- cd frontend && npm run build
- cd frontend && npm run lint
- git diff --check
```

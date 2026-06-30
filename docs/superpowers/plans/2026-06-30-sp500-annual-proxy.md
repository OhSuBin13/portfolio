# S&P 500 Annual Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `S&P 500 연 성장률` to `Growth Annual History` using seeded `VOO` annual proxy prices for 2021 through 2025, while hiding the value for the unfinished current year.

**Architecture:** Add a small Toss-only-compatible `sp500_proxy_prices` table instead of restoring removed local ledger tables. The fresh schema seeds 2021 through 2025 VOO year-end close prices, and the v13→v14 migration backfills those seed rows into existing databases without overwriting user-edited prices. The annual history endpoint derives a year-to-ratio map from the seed table and passes that map into the existing annual history assembly. The frontend renders the new annual column.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, pytest, React, TypeScript, Vite, Node source-inspection tests.

---

### Task 1: Backend Proxy Price Seed Storage And Annual Ratio

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/src/portfolio_app/services/growth_history.py`
- Modify: `backend/src/portfolio_app/api/growth_history.py`
- Test: `backend/tests/test_db.py`
- Test: `backend/tests/test_growth_history.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing schema and repository tests**

Add tests to `backend/tests/test_db.py`:

```python
SP500_PROXY_PRICE_INDEXES = {
    "idx_sp500_proxy_prices_symbol_year",
}
```

Add `sp500_proxy_prices` to `TOSS_ONLY_TABLES` and `SP500_PROXY_PRICE_INDEXES` to `TOSS_ONLY_INDEXES`.

Add:

```python
def assert_seeded_sp500_proxy_prices(db: sqlite3.Connection) -> None:
    rows = db.execute(
        """
        select year, price
        from sp500_proxy_prices
        where year between 2021 and 2025
        order by year
        """
    ).fetchall()
    assert [(row["year"], row["price"]) for row in rows] == [
        (2021, 436.57),
        (2022, 351.34),
        (2023, 436.80),
        (2024, 538.81),
        (2025, 627.13),
    ]
```

Add:

```python
def assert_sp500_proxy_prices_contract(db: sqlite3.Connection) -> None:
    assert "sp500_proxy_prices" in table_names(db)
    assert column_names(db, "sp500_proxy_prices") == {
        "id",
        "year",
        "proxy_symbol",
        "price",
        "currency",
        "created_at",
        "updated_at",
    }
    assert index_names(db) >= SP500_PROXY_PRICE_INDEXES

    db.execute(
        """
        insert into sp500_proxy_prices(year, price)
        values (?, ?)
        """,
        (2026, 500.0),
    )
    row = db.execute("select * from sp500_proxy_prices where year = 2026").fetchone()
    assert row["proxy_symbol"] == "VOO"
    assert row["currency"] == "USD"

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into sp500_proxy_prices(year, price) values (?, ?)",
            (2026, 510.0),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "insert into sp500_proxy_prices(year, price) values (?, ?)",
            (2027, 0),
        )
```

Add fresh and migration tests:

```python
def test_sp500_proxy_prices_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert migration_versions(db) == [14]
    assert_sp500_proxy_prices_contract(db)
    assert_seeded_sp500_proxy_prices(db)


def test_migrate_from_v12_adds_sp500_proxy_prices_table(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 12)
    create_toss_only_survivor_tables(db)
    create_v11_toss_order_history_tables(db)
    db.execute(
        """
        create table growth_month_history (
          id integer primary key,
          account_seq text not null,
          year integer not null check (year >= 2000 and year <= 2099),
          month integer not null check (month >= 1 and month <= 12),
          net_worth_krw real not null check (net_worth_krw >= 0),
          monthly_dividend_krw real not null default 0 check (monthly_dividend_krw >= 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, year, month)
        )
        """
    )
    db.execute(
        """
        create index idx_growth_month_history_account_period
        on growth_month_history(account_seq, year, month)
        """
    )
    db.commit()

    migrate(db)

    assert migration_versions(db) == [12, 13, 14]
    assert_sp500_proxy_prices_contract(db)
    assert_seeded_sp500_proxy_prices(db)
```

Add a repository helper test:

```python
def test_sp500_proxy_price_repository_helpers_fetch_seeded_ratios(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert [(row["year"], row["price"]) for row in repositories.fetch_sp500_proxy_prices(db)] == [
        (2021, 436.57),
        (2022, 351.34),
        (2023, 436.80),
        (2024, 538.81),
        (2025, 627.13),
    ]
    ratios = repositories.fetch_sp500_proxy_annual_return_ratios(
        db,
        years=[2021, 2022, 2023, 2024, 2025, 2026],
        current_year=2026,
    )
    assert ratios[2022] == pytest.approx(351.34 / 436.57)
    assert ratios[2023] == pytest.approx(436.80 / 351.34)
    assert ratios[2024] == pytest.approx(538.81 / 436.80)
    assert ratios[2025] == pytest.approx(627.13 / 538.81)
    assert 2021 not in ratios
    assert 2026 not in ratios
```

- [ ] **Step 2: Write failing growth API/model tests**

In `backend/tests/test_growth_history.py`, add:

```python
def test_annual_history_attaches_sp500_proxy_ratios_for_completed_years():
    rows = build_annual_history(
        [
            month(2024, 12, 1_000_000),
            month(2025, 12, 1_250_000),
            month(2026, 6, 1_500_000),
        ],
        sp500_annual_return_ratios={2025: 1.2, 2026: 1.25},
        current_year=2026,
    )

    assert rows[0].sp500_annual_return_ratio is None
    assert rows[1].sp500_annual_return_ratio == pytest.approx(1.2)
    assert rows[2].sp500_annual_return_ratio is None
```

Extend `valid_annual` with:

```python
"sp500_annual_return_ratio": None,
```

and assert non-finite rejection:

```python
with pytest.raises(ValidationError):
    GrowthAnnualHistoryRow(**{**valid_annual, "sp500_annual_return_ratio": float("inf")})
```

Add an endpoint test:

```python
def test_get_annual_history_includes_sp500_proxy_for_completed_years(tmp_path):
    client = create_test_client(tmp_path)
    for year, month_number, net_worth in [
        (2023, 12, 900_000),
        (2024, 12, 1_000_000),
        (2025, 12, 1_200_000),
        (2026, 6, 1_500_000),
    ]:
        put_month(
            client,
            account_seq="acct-1",
            year=year,
            month_number=month_number,
            net_worth_krw=net_worth,
            monthly_dividend_krw=0,
        )

    response = client.get("/api/growth/annual-history", params={"account_seq": "acct-1"})

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["sp500_annual_return_ratio"] == pytest.approx(436.80 / 351.34)
    assert rows[1]["sp500_annual_return_ratio"] == pytest.approx(538.81 / 436.80)
    assert rows[2]["sp500_annual_return_ratio"] == pytest.approx(627.13 / 538.81)
    assert rows[3]["sp500_annual_return_ratio"] is None
```

In `backend/tests/test_api.py`, assert the annual response field:

```python
annual_component = schema["components"]["schemas"]["GrowthAnnualHistoryRow"]
assert "sp500_annual_return_ratio" in annual_component["properties"]
```

- [ ] **Step 3: Run backend tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py backend/tests/test_growth_history.py backend/tests/test_api.py -q
```

Expected: fail because schema version 13 and the 2021~2025 VOO seed rows do not exist yet.

- [ ] **Step 4: Implement schema and migration**

In `backend/src/portfolio_app/schema.sql`, add:

```sql
create table if not exists sp500_proxy_prices (
  id integer primary key,
  year integer not null check (year >= 2000 and year <= 2099),
  proxy_symbol text not null default 'VOO' check (proxy_symbol = 'VOO'),
  price real not null check (price > 0),
  currency text not null default 'USD' check (currency = 'USD'),
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique(proxy_symbol, year)
);

create index if not exists idx_sp500_proxy_prices_symbol_year
on sp500_proxy_prices(proxy_symbol, year);

insert or ignore into sp500_proxy_prices(year, price)
values
  (2021, 436.57),
  (2022, 351.34),
  (2023, 436.80),
  (2024, 538.81),
  (2025, 627.13);
```

In `backend/src/portfolio_app/migrations.py`:

- set `SCHEMA_VERSION = 14`
- add `_migrate_from_13_to_14()` that executes schema statements and inserts version 14
- call it from `migrate()` when `version == 13`

- [ ] **Step 5: Implement model, repository, service, and route**

In `backend/src/portfolio_app/models.py`, add:

```python
sp500_annual_return_ratio: float | None = Field(default=None, ge=0, allow_inf_nan=False)
```

to `GrowthAnnualHistoryRow`.

In `backend/src/portfolio_app/repositories.py`, add `fetch_sp500_proxy_prices` and `fetch_sp500_proxy_annual_return_ratios` helpers using `sp500_proxy_prices`.

In `backend/src/portfolio_app/services/growth_history.py`, extend `build_annual_history()` with optional `sp500_annual_return_ratios` and `current_year`, and set `sp500_annual_return_ratio` to `None` for `row.year >= current_year`.

In `backend/src/portfolio_app/api/growth_history.py`, wire annual history to call `fetch_sp500_proxy_annual_return_ratios(..., current_year=date.today().year)`.

- [ ] **Step 6: Run backend tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py backend/tests/test_growth_history.py backend/tests/test_api.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 7: Commit backend work**

Run:

```bash
git add backend/src/portfolio_app/schema.sql backend/src/portfolio_app/migrations.py backend/src/portfolio_app/models.py backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services/growth_history.py backend/src/portfolio_app/api/growth_history.py backend/tests/test_db.py backend/tests/test_growth_history.py backend/tests/test_api.py
git diff --cached --stat
git diff --cached --name-status
git commit -m "feat: seed sp500 proxy prices"
```

### Task 2: Frontend Annual Column

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/GrowthHistoryPage.tsx`
- Test: `frontend/tests/growth-history-page.test.mjs`

- [ ] **Step 1: Write failing frontend source test**

In `frontend/tests/growth-history-page.test.mjs`, add assertions for:

```javascript
assert.ok(pageSource.includes("S&P 500 연 성장률"), "Page should show the S&P 500 annual growth column")
assert.ok(pageSource.includes("sp500_annual_return_ratio"), "Page should render S&P 500 annual proxy returns")
assert.ok(pageSource.includes("formatReturnPercent(row.sp500_annual_return_ratio)"), "Page should format proxy returns as percentages")
assert.ok(pageSource.includes("getReturnToneClass(row.sp500_annual_return_ratio)"), "Page should color proxy returns")
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```bash
cd frontend && npm test
```

Expected: fail because the page does not render S&P 500 proxy returns.

- [ ] **Step 3: Implement frontend type and column**

In `frontend/src/types.ts`, add:

```ts
sp500_annual_return_ratio: number | null
```

to `GrowthAnnualHistoryRow`.

In `GrowthHistoryPage.tsx`, add the annual table header and body cell:

```tsx
<th className="numeric-cell">S&P 500 연 성장률</th>
<td className={`numeric-cell ${getReturnToneClass(row.sp500_annual_return_ratio)}`}>
  {formatReturnPercent(row.sp500_annual_return_ratio)}
</td>
```

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run:

```bash
cd frontend && npm test
```

Expected: all frontend source tests pass.

- [ ] **Step 5: Commit frontend work**

Run:

```bash
git add frontend/src/types.ts frontend/src/components/GrowthHistoryPage.tsx frontend/tests/growth-history-page.test.mjs
git diff --cached --stat
git diff --cached --name-status
git commit -m "feat: show sp500 annual proxy growth"
```

### Task 3: Full Verification

**Files:**
- No code files.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py backend/tests/test_growth_history.py backend/tests/test_api.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run backend lint**

Run:

```bash
.venv/bin/python -m ruff check backend/src/portfolio_app backend/tests
```

Expected: no lint errors.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: all commands exit with code 0.

- [ ] **Step 4: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Inspect final status**

Run:

```bash
git status --short --branch
```

Expected: no uncommitted tracked changes. The existing untracked `docs/superpowers/plans/2026-06-30-growth-period-history.md` may remain if still unrelated.

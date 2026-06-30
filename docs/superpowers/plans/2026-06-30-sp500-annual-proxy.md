# S&P 500 Annual Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `S&P 500 연 성장률` to `Growth Annual History` using `VOO` price snapshots as the ETF proxy, while hiding the value for the unfinished current year.

**Architecture:** Keep the derived annual portfolio history in `services/growth_history.py`. Fetch `VOO` proxy prices from existing `assets` and `price_snapshots` data in `repositories.py`, pass a year-to-ratio map through the annual history route, and render the nullable field in the existing React table.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, pytest, React, TypeScript, Vite, Node source-inspection tests.

---

### Task 1: Backend S&P 500 Proxy Field

**Files:**
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/src/portfolio_app/services/growth_history.py`
- Modify: `backend/src/portfolio_app/api/growth_history.py`
- Test: `backend/tests/test_growth_history.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing service/model tests**

Add tests that expect `GrowthAnnualHistoryRow.sp500_annual_return_ratio` to exist, accept `None`, and receive values passed through from `build_annual_history`.

```python
def test_annual_history_attaches_sp500_proxy_ratios_for_completed_years():
    rows = build_annual_history(
        [
            month(2024, 12, 1_000_000),
            month(2025, 12, 1_250_000),
            month(2026, 6, 1_500_000),
        ],
        sp500_annual_return_ratios={2025: 1.2},
        current_year=2026,
    )

    assert rows[0].sp500_annual_return_ratio is None
    assert rows[1].sp500_annual_return_ratio == pytest.approx(1.2)
    assert rows[2].sp500_annual_return_ratio is None
```

In the existing `valid_annual` dict inside `test_growth_history_models_reject_extra_and_non_finite_values`, add:

```python
"sp500_annual_return_ratio": None,
```

Then add:

```python
with pytest.raises(ValidationError):
    GrowthAnnualHistoryRow(**{**valid_annual, "sp500_annual_return_ratio": float("inf")})
```

- [ ] **Step 2: Write the failing endpoint test**

Add a route-level test in `backend/tests/test_growth_history.py` that creates a `VOO` asset and price snapshots, then confirms only completed years get the proxy value.

```python
def test_get_annual_history_includes_sp500_proxy_for_completed_years(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.db_path)
    try:
        asset_id = create_asset(
            db,
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            type="stock_etf",
            currency="USD",
            market="US",
            is_listed=True,
            instrument_type="ETF",
        )
        insert_price_snapshot(
            db,
            asset_id=asset_id,
            source="manual",
            price=100,
            currency="USD",
            price_krw=100,
            status="ok",
            fetched_at="2024-12-31T23:59:00+00:00",
        )
        insert_price_snapshot(
            db,
            asset_id=asset_id,
            source="manual",
            price=120,
            currency="USD",
            price_krw=120,
            status="ok",
            fetched_at="2025-12-31T23:59:00+00:00",
        )
        insert_price_snapshot(
            db,
            asset_id=asset_id,
            source="manual",
            price=150,
            currency="USD",
            price_krw=150,
            status="ok",
            fetched_at="2026-12-31T23:59:00+00:00",
        )
        db.commit()
    finally:
        db.close()
    for year, month_number, net_worth in [
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
    assert rows[0]["sp500_annual_return_ratio"] is None
    assert rows[1]["sp500_annual_return_ratio"] == pytest.approx(1.2)
    assert rows[2]["sp500_annual_return_ratio"] is None
```

Import helpers at the top of the test file:

```python
from portfolio_app.db import connect
from portfolio_app.repositories import create_asset
from portfolio_app.services.market_data import insert_price_snapshot
```

- [ ] **Step 3: Run backend tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth_history.py backend/tests/test_api.py -q
```

Expected: fail because `sp500_annual_return_ratio` and the new `build_annual_history` parameters do not exist yet.

- [ ] **Step 4: Implement the model and pure annual assembly**

In `backend/src/portfolio_app/models.py`, add:

```python
sp500_annual_return_ratio: float | None = Field(default=None, ge=0, allow_inf_nan=False)
```

to `GrowthAnnualHistoryRow`.

In `backend/src/portfolio_app/services/growth_history.py`, change `build_annual_history` to accept:

```python
def build_annual_history(
    rows: Iterable[GrowthMonthInput],
    *,
    sp500_annual_return_ratios: dict[int, float] | None = None,
    current_year: int | None = None,
) -> list[GrowthAnnualHistoryRow]:
```

Inside the loop, set:

```python
proxy_ratios = sp500_annual_return_ratios or {}
sp500_annual_return_ratio = (
    None if current_year is not None and row.year >= current_year else proxy_ratios.get(row.year)
)
```

and pass `sp500_annual_return_ratio=sp500_annual_return_ratio` into `GrowthAnnualHistoryRow`.

- [ ] **Step 5: Implement repository proxy lookup**

In `backend/src/portfolio_app/repositories.py`, add:

```python
def fetch_price_snapshot_at_or_before(
    db: sqlite3.Connection,
    *,
    symbol: str,
    market: str,
    fetched_at: str,
) -> sqlite3.Row | None:
    return db.execute(
        """
        select ps.*
        from price_snapshots ps
        join assets a on a.id = ps.asset_id
        where upper(a.symbol) = upper(?)
          and a.market = ?
          and ps.status in ('ok', 'manual', 'stale')
          and ps.fetched_at <= ?
        order by ps.fetched_at desc, ps.id desc
        limit 1
        """,
        (symbol, market, fetched_at),
    ).fetchone()
```

Then add:

```python
def fetch_sp500_proxy_annual_return_ratios(
    db: sqlite3.Connection,
    *,
    years: list[int],
    current_year: int,
    proxy_symbol: str = "VOO",
    proxy_market: str = "US",
) -> dict[int, float]:
    ratios: dict[int, float] = {}
    for year in sorted(set(years)):
        if year >= current_year:
            continue
        start = fetch_price_snapshot_at_or_before(
            db,
            symbol=proxy_symbol,
            market=proxy_market,
            fetched_at=f"{year - 1}-12-31T23:59:59+00:00",
        )
        end = fetch_price_snapshot_at_or_before(
            db,
            symbol=proxy_symbol,
            market=proxy_market,
            fetched_at=f"{year}-12-31T23:59:59+00:00",
        )
        if start is None or end is None:
            continue
        start_price = float(start["price"])
        if start_price <= 0:
            continue
        ratios[year] = float(end["price"]) / start_price
    return ratios
```

- [ ] **Step 6: Wire endpoint to proxy lookup**

In `backend/src/portfolio_app/api/growth_history.py`, import:

```python
from datetime import date
```

and `fetch_sp500_proxy_annual_return_ratios`.

Change `_build_annual_history` to accept `sp500_annual_return_ratios` and call:

```python
return build_annual_history(
    rows,
    sp500_annual_return_ratios=sp500_annual_return_ratios,
    current_year=date.today().year,
)
```

In `list_growth_annual_history`, fetch month inputs once, build the years list, call `fetch_sp500_proxy_annual_return_ratios`, and pass the result into `_build_annual_history`.

- [ ] **Step 7: Update OpenAPI test expectation**

In `backend/tests/test_api.py`, extend the growth annual schema assertion to check that the component has the new field:

```python
annual_component = schema["components"]["schemas"]["GrowthAnnualHistoryRow"]
assert "sp500_annual_return_ratio" in annual_component["properties"]
```

- [ ] **Step 8: Run backend tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_growth_history.py backend/tests/test_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit backend work**

Run:

```bash
git add backend/src/portfolio_app/models.py backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services/growth_history.py backend/src/portfolio_app/api/growth_history.py backend/tests/test_growth_history.py backend/tests/test_api.py
git diff --cached --stat
git diff --cached --name-status
git commit -m "feat: add sp500 annual proxy growth"
```

### Task 2: Frontend Annual Table Column

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/GrowthHistoryPage.tsx`
- Test: `frontend/tests/growth-history-page.test.mjs`

- [ ] **Step 1: Write the failing frontend source test**

In `frontend/tests/growth-history-page.test.mjs`, add assertions:

```javascript
assert.ok(pageSource.includes("S&P 500 연 성장률"), "Page should show the S&P 500 annual growth column")
assert.ok(
  pageSource.includes("sp500_annual_return_ratio") &&
    pageSource.includes("formatReturnPercent(row.sp500_annual_return_ratio)"),
  "Page should render S&P 500 annual proxy returns as percentages",
)
assert.ok(
  pageSource.includes("getReturnToneClass(row.sp500_annual_return_ratio)"),
  "Page should apply return colors to S&P 500 annual proxy returns",
)
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```bash
cd frontend && npm test
```

Expected: fail because the annual table does not render `sp500_annual_return_ratio`.

- [ ] **Step 3: Implement frontend type and table column**

In `frontend/src/types.ts`, add to `GrowthAnnualHistoryRow`:

```ts
sp500_annual_return_ratio: number | null
```

In `frontend/src/components/GrowthHistoryPage.tsx`, add the header after `연 수익률` or next to the annual return columns:

```tsx
<th className="numeric-cell">S&P 500 연 성장률</th>
```

Add the body cell:

```tsx
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
.venv/bin/python -m pytest backend/tests/test_growth_history.py backend/tests/test_api.py -q
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

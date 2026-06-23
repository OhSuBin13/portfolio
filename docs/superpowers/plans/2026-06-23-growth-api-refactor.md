# Growth API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `/api/growth` so HTTP routing, DB persistence, snapshot policy, and growth calculations have clear boundaries while preserving the visible API contract.

**Architecture:** Keep `backend/src/portfolio_app/api/growth.py` as a thin FastAPI adapter. Move growth-specific SQL row fetching and snapshot persistence into repository helpers, then expose DB-free calculation functions from `services/growth.py` so policy tests can exercise behavior without a database. Preserve frontend response models unless a task explicitly changes behavior.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, Ruff, React/Vite static contract tests.

---

### Task 1: Add DB-Free Growth Assembly

**Files:**
- Modify: `backend/src/portfolio_app/services/growth.py`
- Modify: `backend/tests/test_growth.py`

- [ ] Write a failing test that calls a DB-free growth assembly helper with snapshot and cashflow inputs.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py::test_build_growth_history_from_inputs_calculates_monthly_rows_without_db -q` and verify it fails because the helper is missing.
- [ ] Add focused input dataclasses and `build_growth_history_from_inputs()` while keeping `build_growth_history()` behavior unchanged.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py`.
- [ ] Commit as `refactor: add db-free growth history assembly`.

### Task 2: Move Growth Persistence Queries To Repositories

**Files:**
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/src/portfolio_app/services/growth.py`
- Modify: `backend/tests/test_growth.py`

- [ ] Write a failing static contract test that expects growth snapshot and cashflow repository helpers to exist and keeps raw `portfolio_snapshots` SQL out of `services/growth.py`.
- [ ] Run the focused test and verify it fails.
- [ ] Add `GrowthSnapshotRow`, `GrowthCashflowRow`, snapshot fetch/list/upsert helpers, and growth cashflow row fetching in `repositories.py`.
- [ ] Route `services/growth.py` through those helpers.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py`.
- [ ] Commit as `refactor: move growth queries to repositories`.

### Task 3: Clarify Growth Cashflow Date Boundaries

**Files:**
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/src/portfolio_app/services/growth.py`
- Modify: `backend/tests/test_growth.py`

- [ ] Write a failing test showing a starting snapshot date deposit is already in the starting baseline and must not reduce period profit.
- [ ] Run the focused test and verify it fails under the current inclusive start boundary.
- [ ] Change the growth cashflow window to exclude the starting snapshot date and include through the ending snapshot date.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py`.
- [ ] Commit as `fix: exclude starting date cashflow from growth`.

### Task 4: Preserve Market Sync Snapshot Refresh Policy

**Files:**
- Modify: `backend/src/portfolio_app/services/growth.py`
- Modify: `backend/tests/test_growth.py`
- Verify: `backend/tests/test_market_data.py`

- [ ] Write focused service tests showing market-sync snapshots refresh automatic same-day rows but preserve manual/import rows.
- [ ] Run the focused tests and verify any missing policy coverage fails.
- [ ] Keep or adjust `create_or_refresh_market_sync_snapshot()` so it refreshes `market_sync`/`scheduled` rows and preserves `manual`/`import` rows.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py backend/tests/test_market_data.py::test_market_sync_refreshes_existing_market_sync_snapshot_after_price_update -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/services/growth.py backend/tests/test_growth.py`.
- [ ] Commit as `test: cover automatic growth snapshot refresh policy`.

### Task 5: Keep Growth API As Thin Adapter

**Files:**
- Modify: `backend/src/portfolio_app/api/growth.py`
- Modify: `backend/tests/test_growth_api.py`

- [ ] Write a static/API contract test proving the route module delegates to service functions and contains no raw SQL.
- [ ] Run the focused static test and verify it fails if the contract is missing.
- [ ] Adjust route helper naming/imports only as needed after the service split.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth_api.py::test_growth_api_routes_delegate_to_service_layer -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/api/growth.py backend/tests/test_growth_api.py`.
- [ ] Commit as `refactor: assert growth api delegates to service layer`.

### Task 6: Make Growth API Tests Reliable

**Files:**
- Modify: `backend/tests/test_growth_api.py`
- Optionally modify: `backend/src/portfolio_app/main.py`

- [ ] Write or adjust the growth API test fixture so app background schedulers are disabled for TestClient runs.
- [ ] Run `timeout 10 .venv/bin/python -m pytest backend/tests/test_growth_api.py::test_create_today_snapshot_endpoint_defaults_to_manual_source -q` and verify it completes.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth_api.py -q`.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py backend/tests/test_growth_api.py -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/tests/test_growth_api.py`.
- [ ] Commit as `test: disable schedulers in growth api tests`.

### Final Verification

- [ ] Run `.venv/bin/python -m pytest backend/tests/test_growth.py backend/tests/test_growth_api.py backend/tests/test_market_data.py::test_market_sync_refreshes_existing_market_sync_snapshot_after_price_update -q`.
- [ ] Run `.venv/bin/python -m ruff check backend/src/portfolio_app/api/growth.py backend/src/portfolio_app/services/growth.py backend/src/portfolio_app/repositories.py backend/tests/test_growth.py backend/tests/test_growth_api.py`.
- [ ] Run `git status --short --branch`.

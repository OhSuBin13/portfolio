# Market Data API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `/api/market-data` so the API layer is thin, the sync workflow is service-owned, response contracts are typed, and future provider integration has a stable boundary.

**Architecture:** Keep FastAPI route modules responsible for HTTP request/response adaptation only. Move market sync, snapshot persistence, provider selection, FX conversion, stale fallback, and growth snapshot policy into service modules. Preserve the current frontend-visible `/api/market-data/status` contract and backend-owned automatic sync behavior.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, pytest, React/Vite source-inspection tests.

---

### Task 1: Move Sync Internals Out of the API Module

**Files:**
- Modify: `backend/src/portfolio_app/api/market_data.py`
- Modify: `backend/src/portfolio_app/services/market_data.py`
- Modify: `backend/tests/test_market_data.py`
- Add: `docs/superpowers/plans/2026-06-23-market-data-api-refactor.md`

- [ ] Write a failing source-boundary test asserting `sync_market_data_for_settings()` is implemented in the service module, not the API module.
- [ ] Move sync helpers and implementation from `api/market_data.py` to `services/market_data.py`.
- [ ] Keep the route path and existing response payload behavior unchanged.
- [ ] Run `backend/tests/test_market_data.py`.
- [ ] Commit as `refactor: move market sync logic into service`.

### Task 2: Remove Scheduler Dependency on API Module

**Files:**
- Modify: `backend/src/portfolio_app/services/market_sync_scheduler.py`
- Modify: `backend/tests/test_market_sync_scheduler.py`

- [ ] Write a failing source-boundary test asserting the scheduler imports from the service module, not `portfolio_app.api.market_data`.
- [ ] Update `run_market_sync_once()` to call `portfolio_app.services.market_data.sync_market_data_for_settings`.
- [ ] Run scheduler and market-data tests.
- [ ] Commit as `refactor: decouple market sync scheduler from api`.

### Task 3: Type Market Data API Responses

**Files:**
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/api/market_data.py`
- Modify: `backend/tests/test_market_data.py`

- [ ] Write a failing OpenAPI test for named schemas on manual-price, status, and sync responses.
- [ ] Add Pydantic response models for price snapshots, status rows, sync rows, and sync responses.
- [ ] Attach `response_model` declarations to the route handlers.
- [ ] Run market-data tests.
- [ ] Commit as `refactor: type market data api responses`.

### Task 4: Extract Market Data Provider Selection

**Files:**
- Modify: `backend/src/portfolio_app/services/market_data.py`
- Modify: `backend/tests/test_market_data.py`

- [ ] Write failing service tests for selecting Alpha Vantage for US/USD stock ETFs and rejecting unsupported KR/KRW stock ETFs through a provider boundary.
- [ ] Add a `MarketDataProvider` protocol, unsupported provider implementation, and `market_data_provider_for_asset()` resolver.
- [ ] Route quote fetching through the resolver while preserving existing error messages.
- [ ] Run market-data tests.
- [ ] Commit as `refactor: add market data provider resolver`.

### Task 5: Clarify Market-Sync Growth Snapshot Refresh Policy

**Files:**
- Modify: `backend/src/portfolio_app/services/growth.py`
- Modify: `backend/src/portfolio_app/services/market_data.py`
- Modify: `backend/tests/test_market_data.py`

- [ ] Write a failing test showing a later successful market sync refreshes an existing same-day `market_sync` growth snapshot.
- [ ] Add a growth service helper that refreshes existing `market_sync` or `scheduled` snapshots but preserves manual/import snapshots.
- [ ] Call the helper from market sync.
- [ ] Run market-data and growth tests.
- [ ] Commit as `fix: refresh automatic snapshot after market sync`.

### Task 6: Preserve Frontend Status Contract and Remove Stale Sync Types

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/tests/settings-market-sync.test.mjs`

- [ ] Write a failing frontend source test asserting status uses a constrained status union and stale manual sync response types are gone.
- [ ] Add `MarketSnapshotStatus` and use it in `MarketDataStatus`.
- [ ] Remove unused `MarketSyncRow` and `MarketSyncResult` types.
- [ ] Run the settings frontend test.
- [ ] Commit as `refactor: tighten market status frontend types`.

### Task 7: Split API and Service Test Coverage

**Files:**
- Create: `backend/tests/test_market_data_service.py`
- Create: `backend/tests/test_market_data_test_structure.py`
- Modify: `backend/tests/test_market_data.py`

- [ ] Write a failing structure test asserting API tests do not import provider implementation classes.
- [ ] Move provider, FX provider, fallback, and provider resolver tests into `test_market_data_service.py`.
- [ ] Keep route and persistence behavior tests in `test_market_data.py`.
- [ ] Run market-data test files and Ruff.
- [ ] Commit as `test: split market data service coverage`.

### Final Verification

- [ ] Run `.venv/bin/python -m pytest backend/tests/test_market_data.py backend/tests/test_market_data_service.py backend/tests/test_market_sync_scheduler.py backend/tests/test_growth.py -q`.
- [ ] Run `.venv/bin/python -m ruff check backend`.
- [ ] Run `node frontend/tests/settings-market-sync.test.mjs`.
- [ ] Report the seven commits and verification results.

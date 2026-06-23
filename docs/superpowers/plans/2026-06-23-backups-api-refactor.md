# Backups API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/backups` a typed, read-only history endpoint backed by automatic backup creation and a startup dedupe policy.

**Architecture:** Keep backup creation in services and schedulers, keep the API as history display only, and split filesystem/database reconciliation from pure listing. Preserve SQLite backup creation behavior while reducing unintended write side effects during GET.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, pytest, React/Vite source-inspection tests.

---

### Task 1: Remove Manual Backup API Contract

**Files:**
- Modify: `backend/src/portfolio_app/api/backups.py`
- Modify: `backend/tests/test_backups.py`

- [ ] **Step 1: Write the failing tests**

Assert OpenAPI no longer exposes `POST /api/backups`, and replace POST-based backup creation tests with service-owned backup creation.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_backup_api_is_read_only_in_openapi -q`
Expected: FAIL because the test does not exist yet, then FAIL because POST still exists.

- [ ] **Step 3: Remove endpoint**

Delete the `@router.post("")` handler from `backend/src/portfolio_app/api/backups.py` and remove the unused `create_recorded_backup` import.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_backup_api_is_read_only_in_openapi -q`
Expected: PASS.

### Task 2: Add Typed Backup Response Model

**Files:**
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/api/backups.py`
- Modify: `backend/tests/test_backups.py`

- [ ] **Step 1: Write the failing tests**

Assert `/api/backups` OpenAPI uses a named `BackupRecord` schema and that backup reasons are constrained to `startup`, `automatic`, or `manual`.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_backup_api_uses_typed_response_schema -q`
Expected: FAIL because response schema is currently anonymous `dict[str, object]`.

- [ ] **Step 3: Implement model**

Add `BackupReason` and `BackupRecord` in `backend/src/portfolio_app/models.py`, then declare `response_model=list[BackupRecord]` on the GET route.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_backup_api_uses_typed_response_schema -q`
Expected: PASS.

### Task 3: Split Listing From Reconciliation

**Files:**
- Modify: `backend/src/portfolio_app/services/backups.py`
- Modify: `backend/src/portfolio_app/api/backups.py`
- Modify: `backend/tests/test_backups.py`

- [ ] **Step 1: Write the failing tests**

Assert `list_backup_records()` does not mutate stale metadata or backfill orphan files, and add explicit tests for `reconcile_backup_records()`.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_list_backup_records_does_not_reconcile_filesystem_metadata -q`
Expected: FAIL because listing currently reconciles.

- [ ] **Step 3: Implement separation**

Remove the implicit `reconcile_backup_records()` call from `list_backup_records()`. Call reconciliation explicitly before API listing and after backup creation where needed.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_list_backup_records_does_not_reconcile_filesystem_metadata backend/tests/test_backups.py::test_reconcile_backup_records_hides_stale_metadata_and_backfills_orphans -q`
Expected: PASS.

### Task 4: Throttle Startup Backups

**Files:**
- Modify: `backend/src/portfolio_app/services/backups.py`
- Modify: `backend/src/portfolio_app/main.py`
- Modify: `backend/tests/test_backups.py`

- [ ] **Step 1: Write the failing tests**

Assert repeated `create_app()` calls within a short window keep one startup backup, while automatic backup creation remains unaffected.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_create_app_throttles_recent_startup_backup -q`
Expected: FAIL because every app creation currently creates a startup backup.

- [ ] **Step 3: Implement dedupe**

Add a service helper that checks for a recent `reason='startup'` backup row with an existing file and create a startup backup only if needed.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest backend/tests/test_backups.py::test_create_app_throttles_recent_startup_backup -q`
Expected: PASS.

### Task 5: Fix Backup Test Verification Path

**Files:**
- Modify: `backend/tests/test_backups.py`
- Modify: `backend/pyproject.toml` if dependency cleanup is confirmed necessary.

- [ ] **Step 1: Reproduce TestClient issue**

Run a minimal `TestClient(FastAPI()).get()` script to confirm current environment behavior.

- [ ] **Step 2: Replace fragile tests**

Use `app.openapi()` and direct route/service calls for backup API contract tests so the backup test suite does not depend on the hanging client path.

- [ ] **Step 3: Run verification**

Run:
`.venv/bin/python -m pytest backend/tests/test_backups.py backend/tests/test_backup_scheduler.py -q`
`.venv/bin/python -m ruff check backend`
`node frontend/tests/settings-market-sync.test.mjs`

Expected: all commands exit 0.

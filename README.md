# Portfolio MVP

Private local Korean personal finance portfolio app for tracking accounts, assets,
transactions, goals, growth history, backups, and market data sync from a local
machine.

## Backend Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python -m uvicorn portfolio_app.asgi:app --reload --host 127.0.0.1 --port 8000
```

The API is served at `http://127.0.0.1:8000`.

Market data sync runs automatically when the backend starts and then repeats
while the backend is running. The default interval is 5 minutes and can be
changed with `PORTFOLIO_MARKET_SYNC_INTERVAL_SECONDS`. Set
`PORTFOLIO_MARKET_SYNC_ENABLED=false` to disable it.

Backups are created on startup and then run automatically while the backend is
running. The default periodic backup interval is 1 hour and can be changed with
`PORTFOLIO_BACKUP_INTERVAL_SECONDS`. Set `PORTFOLIO_BACKUP_ENABLED=false` to
disable periodic backups.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

The frontend uses `http://127.0.0.1:8000` as the default API base. Set
`VITE_API_BASE` if the backend is running elsewhere.

## Data Notes

- SQLite database files live under `data/`; the main local database is
  `data/portfolio.sqlite`.
- Backup files live in `data/backups/`.
- Growth history uses daily records in `portfolio_snapshots`. Today's snapshot
  can be refreshed from the `성장기록` screen and is also created after market
  sync when valuation is available.
- Do not commit database files, backup files, API keys, `node_modules`, or build outputs.

## Verification

Run backend checks from the repository root:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend
```

Run frontend checks:

```bash
cd frontend
npm test
npm run build
npm run lint
```

## MVP Flow

1. Create a KRW cash account and use the built-in KRW cash asset.
2. Add a `1,000,000` KRW deposit transaction.
3. Confirm the dashboard net worth shows `1,000,000 원`.
4. Open `성장기록`, refresh today's snapshot, and confirm growth rows can load.
5. Create a net worth goal for `100,000,000 원`.
6. Confirm an automatic backup record and path appear after the backend has been running.
7. Check market status and confirm failures are shown without crashing.

# Portfolio MVP

Private local Korean personal finance portfolio app for tracking accounts, assets,
transactions, goals, backups, and market data sync from a local machine.

## Backend Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python -m uvicorn portfolio_app.asgi:app --reload --host 127.0.0.1 --port 8000
```

The API is served at `http://127.0.0.1:8000`.

Market data sync runs automatically while the backend is running. The default
interval is 5 minutes and can be changed with
`PORTFOLIO_MARKET_SYNC_INTERVAL_SECONDS`.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Data Notes

- SQLite database files live under `data/`; the main local database is
  `data/portfolio.sqlite`.
- Backup files live in `data/backups/`.
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
npm run build
npm run lint
```

## MVP Flow

1. Create a KRW cash account and a KRW cash asset.
2. Add a `1,000,000` KRW deposit transaction.
3. Confirm the dashboard net worth shows `1,000,000 원`.
4. Create a net worth goal for `100,000,000 원`.
5. Trigger a manual backup and confirm the backup record and path appear.
6. Check market status and confirm failures are shown without crashing.

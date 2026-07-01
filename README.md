# Toss Portfolio

Private local Korean brokerage portfolio app focused on a Toss Securities-backed
portfolio view. Toss accounts and holdings are read through the backend, while
local SQLite stores app settings, goals, backups, FX cache data, and imported
read-only Toss order history.

## Backend Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python -m uvicorn portfolio_app.asgi:app --reload --host 127.0.0.1 --port 8000
```

The API is served at `http://127.0.0.1:8000`.

Toss Open API credentials stay on the backend. Configure them through environment
variables or `.env` before using Toss-backed screens:

```bash
PORTFOLIO_TOSS_API_KEY=...
PORTFOLIO_TOSS_SECRET_KEY=...
```

The backend owns all Toss API calls. The frontend calls local API routes such as
`/api/toss/accounts`, `/api/toss/holdings`, `/api/toss/buying-power`,
`/api/toss/order-imports`, `/api/toss/orders`, and `/api/summary`.

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
- Fresh local schema includes `schema_migrations`, `settings`, `fx_rates`,
  `goals`, `backups`, `toss_order_import_runs`, and `toss_orders`.
- Imported Toss order history is read-only. It does not update current holdings,
  drive dashboard valuation, or recreate the removed local transaction ledger.
- Dashboard valuation uses live Toss holdings for the selected account,
  Toss-derived buying power, and Toss USD/KRW FX data when USD holdings or USD
  buying power are present.
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

## Current Flow

1. Configure Toss Open API credentials on the backend and start the backend.
2. Start the frontend and open the dashboard.
3. Select a Toss account and confirm Toss-derived holdings, buying power, and
   summary values load.
4. Open `보유자산` to inspect the selected account's Toss stock/ETF holdings and
   Toss-derived KRW/USD buying power.
5. Open `주문내역` and import OPEN Toss order history for the selected account.
6. Review imported orders from the local read-only cache. CLOSED imports may fail
   if Toss reports `closed-not-supported`.
7. Create or review local goals and confirm automatic backup records appear after
   the backend has been running.

The app no longer exposes local account creation, asset creation, transaction
entry, growth history refresh, local market-sync status, or `portfolio_snapshots`
as active user workflows.

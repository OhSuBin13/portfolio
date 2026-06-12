# Personal Finance Portfolio App Design

Date: 2026-06-12
Status: Approved for specification review
Reference: Google Sheet `일일퀘스트`, tab `Portfolio`

## 1. Purpose

Build a private, local-only personal finance portfolio application. The app replaces the spreadsheet as the system of record while using the spreadsheet's `Portfolio` tab as reference for the first data concepts: net worth, asset groups, holdings, goals, dividends/income, and growth history.

The MVP is for one user on one local machine. It does not need public sharing, authentication, hosted deployment, brokerage integration, or mobile-first behavior.

## 2. Product Scope

The first version focuses on daily personal use:

- Show today's financial snapshot first.
- Maintain current balances and holdings directly.
- Record transaction history.
- Track first-class asset types: cash, savings, stocks/ETFs, crypto, and debts.
- Import starting holdings from a CSV export of the spreadsheet.
- Fetch market prices automatically for Korean stocks/ETFs, US stocks/ETFs, major crypto, and FX rates.
- Use KRW as the base currency.
- Track net worth and monthly dividend/income goals.
- Create automatic dated backups in the project folder.

Out of scope for MVP:

- Public read-only pages.
- Login or multi-user access.
- Hosted deployment.
- Mobile-first PWA behavior.
- Brokerage or exchange account connection.
- Full accounting-style double-entry ledger.
- Live Google Sheets sync after setup import.

## 3. Architecture

Use a local full-stack web app.

The frontend runs in the browser and presents a Korean dashboard UI. It communicates with a local backend over HTTP. The backend owns persistence and finance logic: SQLite database access, CSV import, price fetching, FX conversion, goal calculations, backup creation, and validation.

The SQLite database and backups live inside the project folder so the application stays private and easy to back up or migrate.

Core modules:

- Frontend UI: dashboard, holdings editor, transaction ledger, goals, import, and settings.
- Backend API: typed endpoints for portfolio summary, holdings, transactions, goals, prices, imports, and backups.
- Finance engine: net worth, asset allocation, KRW conversion, monthly income, goal progress, and holding valuation.
- Market data service: Korean/US stock and ETF prices, crypto prices, and FX rates through configured providers.
- Import service: CSV parsing, preview, mapping, confirmation, and row-level import reporting.
- Backup service: automatic dated SQLite database copies and retention.

The implementation plan may choose the exact web framework, but it must preserve this separation: UI in the frontend, finance and persistence logic in the backend.

## 4. User Interface

The MVP uses a Snapshot First dashboard. Korean is the primary UI language.

Screens:

- `대시보드`: net worth, goal progress, asset mix, holdings preview, recent transactions, price sync status, and backup status.
- `보유자산`: editable accounts and holdings for cash, savings, stocks/ETFs, crypto, and debts.
- `거래내역`: transaction ledger with supported transaction types.
- `목표`: net worth goal and monthly dividend/income goals.
- `가져오기`: CSV import from spreadsheet export.
- `설정`: API keys, market data settings, currency settings, and backup settings.

Dashboard structure:

- Top summary: 순자산 in KRW, change indicators, and goal progress.
- Asset bucket cards: 현금, 적금, 주식/ETF, 코인, 부채.
- Holdings preview: asset, account, quantity/balance, average cost, current price, valuation, and profit/loss.
- Recent transactions: date, type, account, asset, amount, and memo.
- System status: market sync freshness and latest backup.

## 5. Data Model

The app stores enough structure to support both direct balance editing and transaction history without requiring full double-entry accounting.

Core records:

- `accounts`: named places where value lives, such as KRW cash, USD cash, savings account, brokerage account, crypto wallet, or debt account.
- `assets`: trackable instruments, such as Samsung Electronics, VOO, BTC, KRW cash, USD cash, savings principal, or debt principal.
- `holdings`: current quantity or balance per account and asset, including average cost where applicable.
- `transactions`: dated events that explain changes.
- `price_snapshots`: fetched market prices by asset, timestamp, source, and native currency.
- `fx_rates`: exchange rates into KRW.
- `goals`: target records for net worth and monthly dividend/income.
- `import_runs`: CSV import attempts, summaries, and row-level warnings/errors.
- `backups`: metadata for automatic dated backup files.

Supported transaction types:

- Deposit.
- Withdrawal.
- Buy.
- Sell.
- Dividend.
- Interest.
- Fee.
- Debt payment.
- Manual adjustment.

Rules:

- Direct holding edits create a manual adjustment transaction so history stays explainable.
- Transactions update or recalculate holdings according to their type.
- Valuation always reports totals in KRW.
- Market-priced assets keep native currency and latest KRW-converted value.
- Debts reduce net worth.
- CSV import creates starting accounts, assets, holdings, and starting adjustment transactions.

## 6. Market Data

Automatic market data is part of the MVP.

Coverage:

- Korean stocks and ETFs.
- US stocks and ETFs.
- Major crypto assets.
- FX rates into KRW.

Provider requirements:

- API keys are acceptable when setup is simple and free or low-cost.
- API keys are stored locally and masked in the UI.
- Providers must be configurable from settings.
- The backend keeps the last known good price if a refresh fails.
- Every price snapshot records source, timestamp, asset, native currency, and fetched value.
- The UI shows last successful sync, failed symbols, provider errors, and stale prices.
- Manual price override exists as a fallback for unsupported symbols or provider outages.

## 7. CSV Import

CSV import is setup-oriented. It is not live spreadsheet sync.

Flow:

1. User exports the existing spreadsheet to CSV.
2. User uploads the CSV in `가져오기`.
3. The app parses rows and shows a preview.
4. The preview shows mapped accounts, assets, holdings, ignored rows, and warnings.
5. User confirms before any data is written.
6. The app creates a backup before writing imported data.
7. The app reports created records and row-level errors.

Parsing requirements:

- Accept currency symbols, commas, percentages, blank cells, and Korean labels.
- Ignore or warn on formula error text such as `#DIV/0!` and `#REF!`.
- Map spreadsheet-style holding rows into asset type, name, quantity, price, average cost, FX rate, valuation, investment amount, dividend data, and weight when present.
- Never silently overwrite existing user-entered data during import.

## 8. Backups

The app creates automatic dated backups of the local SQLite database into a project-folder backup directory.

Backup triggers:

- On app startup or shutdown.
- Before CSV import.
- Before other bulk changes.

Retention:

- Keep the latest 30 daily backups.
- Keep the newest backup even if cleanup would otherwise remove it.

UI requirements:

- Dashboard and settings show latest backup status.
- Backup failures are visible and blocking for risky operations.
- Restore/export can be considered after MVP, but backup creation and retention are in MVP.

## 9. Error Handling And Safety

The app treats financial data as sensitive and high-value.

Safety rules:

- Destructive actions require confirmation.
- CSV import uses preview-confirm before writing.
- A dated backup is created before CSV import and other bulk changes.
- API keys are validated before market sync is enabled.
- Failed price fetches do not overwrite last known good prices.
- Stale prices are visible in the dashboard and holdings table.
- Manual adjustments are labeled clearly.
- If the database cannot open or a required backup fails, the app shows a blocking local error.

Validation examples:

- Missing transaction date.
- Negative quantity where not allowed.
- Unsupported or unresolved market symbol.
- Sell quantity greater than current holding.
- Debt payment greater than outstanding debt balance unless explicitly allowed as an adjustment.
- Missing FX rate for a non-KRW valuation.

Errors are shown in Korean and should identify the field, cause, and recovery action.

## 10. Testing Strategy

Prioritize tests around data correctness and safety.

Required coverage:

- Finance calculations: net worth, debts, asset allocation, KRW conversion, monthly income, and goal progress.
- Transaction effects on holdings.
- Direct holding edits creating adjustment transactions.
- CSV parsing, mapping, preview, confirmation, and row-level error reporting.
- Market-data failure behavior, stale price display data, and manual price override.
- Backup creation, backup-before-import, and retention cleanup.
- API validation for create, update, delete, import, sync, and backup flows.

UI tests should cover the main user flows after the finance logic has coverage:

- View dashboard.
- Add/edit holding.
- Add transaction.
- Run CSV import preview and confirm.
- Configure market data provider.
- Observe backup status.

## 11. Acceptance Criteria

The MVP is complete when:

- A local user can run the app and open the Korean dashboard.
- The app persists data in a project-local SQLite database.
- The user can create/edit accounts, assets, holdings, transactions, and goals.
- Direct holding edits are recorded as adjustment transactions.
- Net worth, asset mix, KRW valuation, goal progress, and monthly income are calculated from stored data.
- CSV import supports preview-confirm and creates starting data from a spreadsheet export.
- Market sync supports Korean stocks/ETFs, US stocks/ETFs, major crypto, and FX into KRW through configured providers.
- Stale/failed market data is visible and does not erase last known good data.
- Automatic dated backups are created and retained.
- Destructive and bulk operations have confirmation and backup safeguards.
- Core finance, import, market failure, and backup behavior are covered by tests.

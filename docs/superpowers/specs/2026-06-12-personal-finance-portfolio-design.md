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
- Enter starting balances and holdings directly in the app.
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
- Bulk file-based onboarding.
- Live Google Sheets sync.

## 3. Architecture

Use a local full-stack web app.

The frontend runs in the browser and presents a Korean dashboard UI. It communicates with a local backend over HTTP. The backend owns persistence and finance logic: SQLite database access, price fetching, FX conversion, goal calculations, backup creation, and validation.

The SQLite database and backups live inside the project folder so the application stays private and easy to back up or migrate.

Core modules:

- Frontend UI: dashboard, holdings editor, transaction ledger, goals, growth history, and settings.
- Backend API: typed endpoints for portfolio summary, holdings, transactions, goals, growth history, prices, and backups.
- Finance engine: net worth, asset allocation, KRW conversion, monthly income, goal progress, and holding valuation.
- Market data service: Korean/US stock and ETF prices, crypto prices, and FX rates through configured providers.
- Backup service: automatic dated SQLite database copies and retention.

The implementation plan may choose the exact web framework, but it must preserve this separation: UI in the frontend, finance and persistence logic in the backend.

## 4. User Interface

The MVP uses a Snapshot First dashboard. Korean is the primary UI language.

Screens:

- `대시보드`: net worth, goal progress, asset mix, holdings preview, recent transactions, price sync status, and backup status.
- `보유자산`: editable accounts and holdings for cash, savings, stocks/ETFs, crypto, and debts.
- `거래내역`: transaction ledger with supported transaction types.
- `목표`: net worth goal and monthly dividend/income goals.
- `성장기록`: daily snapshots and monthly/yearly growth history.
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
- Starting balances and holdings are entered through holdings and transaction screens, and direct balance edits create adjustment transactions.

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

## 7. Backups

The app creates automatic dated backups of the local SQLite database into a project-folder backup directory.

Backup triggers:

- On app startup or shutdown.
- Before other bulk changes.

Retention:

- Keep the latest 30 daily backups.
- Keep the newest backup even if cleanup would otherwise remove it.

UI requirements:

- Dashboard and settings show latest backup status.
- Backup failures are visible and blocking for risky operations.
- Restore/export can be considered after MVP, but backup creation and retention are in MVP.

## 8. Error Handling And Safety

The app treats financial data as sensitive and high-value.

Safety rules:

- Destructive actions require confirmation.
- A dated backup is created before risky bulk changes.
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

## 9. Testing Strategy

Prioritize tests around data correctness and safety.

Required coverage:

- Finance calculations: net worth, debts, asset allocation, KRW conversion, monthly income, and goal progress.
- Transaction effects on holdings.
- Direct holding edits creating adjustment transactions.
- Market-data failure behavior, stale price display data, and manual price override.
- Backup creation and retention cleanup.
- API validation for create, update, delete, sync, and backup flows.

UI tests should cover the main user flows after the finance logic has coverage:

- View dashboard.
- Add/edit holding.
- Add transaction.
- Configure market data provider.
- Observe backup status.

## 10. Acceptance Criteria

The MVP is complete when:

- A local user can run the app and open the Korean dashboard.
- The app persists data in a project-local SQLite database.
- The user can create/edit accounts, assets, holdings, transactions, and goals.
- Direct holding edits are recorded as adjustment transactions.
- Net worth, asset mix, KRW valuation, goal progress, and monthly income are calculated from stored data.
- Market sync supports Korean stocks/ETFs, US stocks/ETFs, major crypto, and FX into KRW through configured providers.
- Stale/failed market data is visible and does not erase last known good data.
- Automatic dated backups are created and retained.
- Destructive and bulk operations have confirmation and backup safeguards.
- Core finance, market failure, and backup behavior are covered by tests.

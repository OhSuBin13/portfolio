# Namuh / NH Securities Open API Integration Review

Date: 2026-06-19

This document reviews whether NH Investment & Securities' Namuh/N2 Open API can
replace or augment features in this portfolio app.

The short answer is conservative: unlike Toss Securities Open API, a public REST
API reference with stable endpoint, authentication, account, market-data, and
order contracts was not verified during this review. NH's official mobile page
does list `N2 Open API` as an online trading channel, but it describes it as a
connection-module based trading-system integration rather than a public HTTP API
that can be directly plugged into this FastAPI backend.

## 1. Sources Checked

Primary and official sources checked:

- NH Investment & Securities mobile trading-channel page:
  <https://m.nhsec.com/static/MNHSI0209>
- NH Investment & Securities public website:
  <https://www.nhsec.com/>
- Namuh public website:
  <https://www.mynamuh.com/>

Candidate API portal hostnames checked, but not resolved from this environment:

- <https://apiportal.nhqv.com/>
- <https://openapi.nhqv.com/>

Searches also surfaced third-party blog posts, cafes, and generic securities
Open API articles. Those are useful only as discovery hints and are not treated
as implementation authority.

Important exclusion:

- Korea Investment Securities KIS Developers appears often in search results,
  but it is a different broker and must not be treated as NH/Namuh
  documentation.

## 2. Current Project Boundary

The current app is a local-first personal finance portfolio system. It stores
accounts, assets, holdings, transactions, prices, FX rates, goals, snapshots,
and backups in SQLite.

Relevant implementation areas:

- `backend/src/portfolio_app/api/market_data.py`
- `backend/src/portfolio_app/services/market_data.py`
- `backend/src/portfolio_app/services/fx_rates.py`
- `backend/src/portfolio_app/services/summary.py`
- `backend/src/portfolio_app/services/transactions.py`
- `backend/src/portfolio_app/db/schema.sql`
- `frontend/src/components/SettingsPage.tsx`
- `frontend/src/components/HoldingsPage.tsx`
- `frontend/src/components/TransactionsPage.tsx`

The current app behavior relevant to broker integration:

- US stock/ETF price sync uses Alpha Vantage.
- KR stock/ETF price sync is explicitly unsupported today.
- USD/KRW FX rates are stored in `fx_rates` and used by `/api/summary`.
- Prices are stored as `price_snapshots`.
- Holdings are the local source of truth and are updated by local transactions
  or manual adjustments.
- Transactions cover more than broker orders: deposit, withdrawal, buy, sell,
  dividend, interest, fee, debt payment, and adjustment.

## 3. Verified NH/Namuh Coverage

The official NH mobile trading-channel page lists `N2 Open API` under online
trading. The page describes it as a service that connects a customer-built
trading strategy system to NH's trading system through a provided connection
module, enabling linkage with market prices, balances, and orders.

That confirms the existence of an NH/N2 Open API-style trading channel at a
product level.

However, this review did not verify a public developer reference equivalent to
Toss Securities Open API:

- No public REST base URL was verified.
- No endpoint list was verified.
- No OAuth or app-key flow was verified.
- No account authorization flow was verified.
- No request/response schema was verified.
- No rate-limit, environment, sandbox, or production-use policy was verified.
- No official SDK or downloadable reference manual was verified from the
  checked public pages.

The available official evidence points more toward a desktop trading-system
connection module than a modern backend-to-broker HTTP integration.

## 4. Replacement Candidate Summary

| Priority | Current feature | Namuh/NH replacement | Assessment |
| --- | --- | --- | --- |
| 1 | US stock price sync through Alpha Vantage | Not verified | Do not replace. A public quote API contract was not confirmed. |
| 1 | Missing KR stock/ETF market sync | Possible only if official market-price API docs are obtained | Not implementable from verified sources. |
| 1 | USD/KRW FX provider | Not verified | Do not replace. No official FX endpoint was confirmed. |
| 2 | Manual stock asset metadata input | Not verified | Do not replace. No stock-master or symbol-search API contract was confirmed. |
| 2 | Manual brokerage holding setup | Product-level possibility only | Official page mentions balance linkage, but no usable account/holding schema was verified. |
| 3 | Manual buy/sell transaction entry | Product-level possibility only | Official page mentions order linkage, but order APIs are too risky without full official contracts. |
| 4 | Direct trading from this app | Not recommended | Treat as out of scope unless NH provides official docs, approval terms, and a separate trading-risk design. |

## 5. Feature-Level Assessment

### 5.1 Market Price Sync

Current behavior:

- Market sync stores latest usable prices in `price_snapshots`.
- US `stock_etf` assets can use Alpha Vantage.
- KR `stock_etf` sync currently records an unsupported-provider result.
- Summary valuation uses the latest valid price snapshot and should not be
  destroyed by provider failures.

Namuh/NH assessment:

- Official page confirms that `N2 Open API` is related to market price linkage
  at a product level.
- A callable public quote endpoint was not verified.
- A connection-module API would likely require a Windows desktop process or
  broker-specific runtime instead of a plain HTTP provider.

Recommendation:

- Do not replace Alpha Vantage with Namuh/NH yet.
- Do not enable KR stock sync through Namuh/NH until official API reference,
  authentication, environment, and quote schema are available.
- If official docs are later obtained, implement it behind the existing market
  data provider boundary and persist into `price_snapshots` with
  `source = 'namuh'` or `source = 'nh_n2'`.

### 5.2 FX Rate Sync

Current behavior:

- USD/KRW rates are stored in `fx_rates`.
- `/api/summary` can refresh FX data independently of stock-price sync.

Namuh/NH assessment:

- No official FX endpoint was verified.
- The checked official page is about trading channels, not currency reference
  data.

Recommendation:

- Do not replace the current FX provider with Namuh/NH.
- If NH later provides official FX data, integrate it as a provider that writes
  to the existing `fx_rates` table before summary calculation.

### 5.3 Stock Metadata And Warnings

Current behavior:

- Stock/ETF assets are manually created with symbol, name, currency, and market.
- The frontend currently limits stock market selection to the supported sync
  surface.

Namuh/NH assessment:

- No official symbol-search, stock master, listing metadata, or warning endpoint
  was verified.

Recommendation:

- Do not use Namuh/NH for symbol validation or metadata autofill yet.
- If official stock-master docs become available, add a backend-only lookup
  endpoint and keep user confirmation before modifying local assets.

### 5.4 Account And Holdings Sync

Current behavior:

- Local holdings are the app's source of truth.
- Holdings cover cash, savings, stock/ETF, and debt assets.
- Non-broker assets must remain local.

Namuh/NH assessment:

- Official page mentions balance linkage at the product level.
- No account-list, holding-list, quantity, cost basis, market value, or cash
  balance schema was verified.
- Namuh customers may have separate channel constraints from QV/N2, so account
  eligibility must be confirmed before any integration.

Recommendation:

- Do not implement holdings sync from Namuh/NH based on public search results.
- If official docs are provided, start with read-only import preview:
  1. authenticate on backend only,
  2. list eligible accounts,
  3. fetch holdings,
  4. show a diff against local holdings,
  5. require explicit confirmation before writing local assets or holdings.

### 5.5 Order History Import

Current behavior:

- Local transactions are broader than broker orders.
- Buy/sell transactions update holdings.
- Dividend, interest, fee, debt payment, deposit, withdrawal, and adjustment
  events are modeled separately.

Namuh/NH assessment:

- Official page mentions order linkage at the product level.
- No order-history schema or execution-detail schema was verified.

Recommendation:

- Do not import Namuh/NH order history until official schemas are available.
- If later available, import filled orders into a review queue instead of
  writing directly to `transactions`.
- Keep broker order IDs in a dedicated external mapping field or table to avoid
  duplicate imports.

### 5.6 Direct Order Placement

Direct trading should not be considered a replacement for current transaction
entry.

Reasons:

- It changes the app from portfolio tracking into a trading system.
- The app currently has no trading-risk model, order preview, compliance flow,
  buying-power checks, sellable-quantity checks, cancellation flow, or market
  state handling.
- The verified NH source does not provide enough public implementation detail.
- Connection-module based trading usually implies runtime and operational
  constraints that do not fit a local Linux/FastAPI app cleanly.

Recommendation:

- Keep direct order placement out of scope.
- Revisit only after read-only data sync is stable and official NH/Namuh
  documentation is available.

## 6. If The API Is Connection-Module Based

If NH/Namuh's usable developer surface is a desktop connection module rather
than REST, it should be treated as a separate adapter architecture, not as a
normal HTTP provider.

Likely implications:

- Windows-only or broker-runtime-dependent process.
- Local bridge process required between FastAPI and the broker module.
- Separate installation, login, certificate, and session handling.
- Real-time event callbacks rather than simple request/response HTTP calls.
- More difficult automated tests and CI.
- Higher operational risk than Toss-style REST integration.

Possible architecture if this path is required later:

- Keep the existing FastAPI app as the only frontend-facing API.
- Add a local bridge process on a supported machine.
- Expose only minimal read-only bridge endpoints at first.
- Push normalized data into the existing backend service layer.
- Never expose broker credentials or account identifiers to the frontend.
- Keep all writes preview-confirmed and idempotent.

This is substantially more work than adding a standard REST market-data
provider.

## 7. Features Namuh/NH Should Not Replace

| Local feature | Reason |
| --- | --- |
| Goals and goal progress | Broker API data does not model personal goals. |
| Backup scheduler and restore flow | Purely local operational feature. |
| Cash, savings, and debt tracking | Brokerage data is not the full personal balance sheet. |
| Manual adjustments | Needed for onboarding, corrections, unsupported assets, and non-NH holdings. |
| Transaction semantics beyond orders | The app tracks broader finance events than broker executions. |
| Portfolio snapshots | Local historical state should remain app-owned. |

## 8. Adoption Recommendation

Do not prioritize Namuh/NH Open API integration ahead of Toss Securities Open
API.

Recommended order:

1. Keep the current Alpha Vantage and FX provider behavior unchanged.
2. Use Toss as the preferred REST-style candidate for market price and FX
   provider replacement.
3. Treat Namuh/NH as blocked until official API documentation is available.
4. If NH/Namuh docs are provided later, reassess only read-only features first:
   market prices, account list, holdings, then order history preview.
5. Keep direct order placement out of scope until a separate trading design is
   written and reviewed.

Minimum documents required before implementation:

- Official NH/Namuh developer guide.
- API reference or connection-module manual.
- Authentication and account authorization guide.
- Production approval and terms of use.
- Rate-limit and throttling rules.
- Error-code reference.
- Sandbox or test environment guide.
- Market-data usage policy.
- Order, balance, and holding schemas.
- Runtime requirements, especially OS and installation dependencies.

## 9. Implementation Notes If Docs Become Available

Backend configuration:

- Keep all secrets backend-only.
- Use `PORTFOLIO_`-prefixed settings for local environment variables.
- Do not store broker credentials in SQLite unless an explicit encrypted-secret
  design is added.

Provider design:

- Add a provider class only after official contracts are known.
- Normalize external data before it reaches summary or transaction services.
- Keep stale-price fallback behavior.
- Keep all provider failures non-destructive.
- Store raw external identifiers in a mapping table instead of overloading local
  asset or transaction IDs.

Suggested staged implementation:

1. `NamuhMarketDataProvider` or `NhN2MarketDataProvider` behind the existing
   market-data boundary.
2. Optional `NamuhFxProvider` only if an official FX endpoint exists.
3. Read-only account and holdings preview.
4. Order-history import preview.
5. Direct trading only as a separate project with explicit risk controls.

Testing:

- Use mocked official responses.
- Do not call live broker APIs in normal test runs.
- Add provider unit tests, persistence tests, and preview-confirm service tests.
- For connection-module integration, separate bridge integration tests from
  regular backend CI.

## 10. Final Position

Namuh/NH Open API should not replace current project features yet.

The only officially verified fact from public pages is that NH lists `N2 Open
API` as an online trading channel for connecting customer-built trading systems
with market price, balance, and order functions through a provided module. That
is not enough to safely implement a backend provider in this project.

For this app, Namuh/NH can become a candidate only after official developer
documentation is obtained. Until then:

- no Alpha Vantage replacement,
- no KR market sync replacement,
- no FX replacement,
- no holdings sync,
- no order-history import,
- no direct order placement.

The practical recommendation is to proceed with Toss first for REST-style
market-data and account integration, while leaving Namuh/NH as a future
investigation item pending official documentation.

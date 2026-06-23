# Toss Securities Open API Integration Review

Date: 2026-06-19
Status: Investigation note

## 1. Purpose

This document summarizes which current portfolio-app features can be replaced or
augmented by Toss Securities Open API.

The current app is a private local personal-finance portfolio app. It stores
accounts, assets, holdings, transactions, market prices, FX rates, goals,
snapshots, and backups in local SQLite. Toss Securities Open API can improve the
market-data and brokerage-account parts, but it should not replace the whole
local finance ledger.

## 2. Sources

Official Toss Securities Open API sources:

- `https://developers.tossinvest.com/llms.txt`
- `https://openapi.tossinvest.com/openapi-docs/overview.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/README.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/MarketDataApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/MarketInfoApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/StockInfoApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/AccountApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/AssetApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/OrderApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/OrderHistoryApi.md`
- `https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/OrderInfoApi.md`

Current project reference points:

- `README.md`
- `backend/src/portfolio_app/schema.sql`
- `backend/src/portfolio_app/api/market_data.py`
- `backend/src/portfolio_app/services/market_data.py`
- `backend/src/portfolio_app/services/fx_rates.py`
- `backend/src/portfolio_app/services/summary.py`
- `backend/src/portfolio_app/services/transactions.py`

## 3. Current Project Boundary

The app currently owns the full local portfolio model:

- `accounts`: cash, savings, brokerage, and debt accounts.
- `assets`: cash, savings, stock/ETF, and debt assets.
- `holdings`: current local balance or quantity per account and asset.
- `transactions`: local ledger events such as deposit, withdrawal, buy, sell,
  dividend, interest, fee, debt payment, and manual adjustment.
- `price_snapshots`: fetched or manual market prices.
- `fx_rates`: FX snapshots used for KRW valuation.
- `goals`: net-worth and monthly-income goals.
- `portfolio_snapshots`: daily growth-history snapshots.
- `backups`: local SQLite backup metadata.

The summary calculation reads local holdings, latest usable prices, latest FX
rates, and current-month income transactions. This means external API data should
usually be persisted into the existing local tables before the dashboard uses it.
That keeps the app usable when a provider fails and preserves the existing
"last known good" design.

## 4. Toss Open API Coverage

Toss Securities Open API currently covers these groups:

| Group | Main endpoints | Relevant to this app |
| --- | --- | --- |
| Auth | `POST /oauth2/token` | Required for all Toss API calls. |
| Market Data | `/api/v1/prices`, `/orderbook`, `/trades`, `/price-limits`, `/candles` | Replace or augment market-price sync. |
| Stock Info | `/api/v1/stocks`, `/stocks/{symbol}/warnings` | Validate symbols and auto-fill asset metadata. |
| Market Info | `/api/v1/exchange-rate`, `/market-calendar/KR`, `/market-calendar/US` | Replace FX provider and optionally show market-open status. |
| Account | `/api/v1/accounts` | Link Toss brokerage accounts. |
| Asset | `/api/v1/holdings` | Sync Toss stock holdings. |
| Order History | `/api/v1/orders`, `/orders/{orderId}` | Import or reconcile completed buy/sell activity. |
| Order Info | `/api/v1/buying-power`, `/sellable-quantity`, `/commissions` | Useful if trading features are added. |
| Order | `POST /api/v1/orders`, modify, cancel | New high-risk trading feature, not a direct MVP replacement. |

Market-data and stock-info calls require OAuth access token. Account, holdings,
orders, and order-info calls also require the `X-Tossinvest-Account` header using
an account sequence from `GET /api/v1/accounts`.

## 5. Replacement Candidates

| Priority | Current feature | Toss API replacement | Assessment |
| --- | --- | --- | --- |
| 1 | US stock price sync through Alpha Vantage | `GET /api/v1/prices` | Strong replacement candidate. It supports KR and US stock symbols and removes the current US-only provider dependency. |
| 1 | Missing KR stock/ETF market sync | `GET /api/v1/prices` | Strong new coverage. The current app explicitly rejects KR market sync. |
| 1 | USD/KRW FX provider | `GET /api/v1/exchange-rate` | Strong replacement candidate for the provider layer. Store into `fx_rates` before summary reads it. |
| 2 | Manual stock asset metadata input | `GET /api/v1/stocks` | Good augmentation. Can auto-fill name, market, currency, listed status, and instrument metadata. |
| 2 | No stock warning visibility | `GET /api/v1/stocks/{symbol}/warnings` | Good augmentation for holdings or transaction screens. |
| 2 | Manual brokerage holding setup | `GET /api/v1/accounts`, `GET /api/v1/holdings` | Good read-only sync candidate for stock/ETF holdings. It should not erase local cash, savings, debt, or manual holdings. |
| 3 | Manual buy/sell transaction entry | `GET /api/v1/orders`, `GET /api/v1/orders/{orderId}` | Useful for importing or reconciling filled orders. Not a complete transaction-ledger replacement. |
| 4 | No real trading feature | `POST /api/v1/orders`, modify, cancel | Possible future feature, but it changes the app from tracking to trading and needs separate safety design. |

## 6. Feature-by-Feature Notes

### 6.1 Market Price Sync

Best first integration target.

Current behavior:

- Backend market sync runs periodically.
- US `stock_etf` assets use Alpha Vantage.
- KR `stock_etf` assets currently fail with "KR market sync is not supported".
- Successful or stale results are stored in `price_snapshots`.
- Summary reads the latest usable snapshot.

Recommended Toss mapping:

| Toss field | Local destination |
| --- | --- |
| `PriceResponse.symbol` | Match `assets.symbol`. |
| `PriceResponse.lastPrice` | `price_snapshots.price`. |
| `PriceResponse.currency` | `price_snapshots.currency`. |
| KRW-converted value | `price_snapshots.price_krw`. |
| `PriceResponse.timestamp` or request time | `price_snapshots.fetched_at`. |
| provider name | `price_snapshots.source = 'toss'`. |

Implementation direction:

- Add a Toss market-data provider behind the existing quote provider boundary.
- Keep the existing "last known good price" behavior.
- Batch up to the official endpoint limit where practical.
- Persist results first, then let summary use the same local query path.

### 6.2 FX Rate Sync

Good first integration target together with market prices.

Current behavior:

- The app stores USD/KRW snapshots in `fx_rates`.
- Summary uses the latest local FX snapshot or falls back to transaction FX.
- `/api/summary` can refresh FX with a short TTL.

Recommended Toss mapping:

| Toss field | Local destination |
| --- | --- |
| `baseCurrency` | `fx_rates.base_currency`. |
| `quoteCurrency` | `fx_rates.quote_currency`. |
| `rate` | `fx_rates.rate`. |
| request time or `validFrom` | `fx_rates.fetched_at`. |
| source | `fx_rates.source = 'toss'`. |
| `rateChangeType`, `basisPoint` | Optional future fields if the schema is expanded. |

Important caveat:

- Toss documentation describes the exchange-rate endpoint as a reference display
  rate. It may differ from the actual trade execution FX rate. For dashboard KRW
  valuation this is acceptable, but it should not be represented as a guaranteed
  order settlement rate.

### 6.3 Stock Master And Warning Data

Good augmentation, especially for the holdings screen.

Current behavior:

- Stock/ETF assets are manually created with symbol, name, currency, and market.
- The backend only enforces that stock/ETF assets have a market value.

Recommended Toss usage:

- Use `GET /api/v1/stocks?symbols=...` when creating or editing a stock asset.
- Auto-fill Korean name, English name, market, currency, listing status, and
  security type where useful.
- Use `/stocks/{symbol}/warnings` to show active trading warnings before a buy
  record or future order is entered.

This should not replace the local `assets` table. It should reduce manual input
and validation errors.

### 6.4 Toss Account And Holdings Sync

Useful, but it should be read-only at first.

Current behavior:

- The app lets the user create local accounts and assets.
- Holdings are updated by local transactions and manual adjustments.
- The dashboard includes stock/ETF, cash, savings, and debt values.

Toss behavior:

- `GET /api/v1/accounts` currently exposes brokerage accounts.
- `GET /api/v1/holdings` returns domestic and US stock holdings. It excludes
  non-stock products such as overseas options and bonds.
- Holding items include symbol, name, market country, currency, quantity, last
  price, average purchase price, market value, profit/loss, daily profit/loss,
  and cost data.

Recommended mapping:

| Toss field | Local destination |
| --- | --- |
| `accountSeq` | New local mapping field or settings entry, not a replacement for local `accounts.id`. |
| `HoldingsItem.symbol` | `assets.symbol`. |
| `HoldingsItem.name` | `assets.name`. |
| `marketCountry` | `assets.market`. |
| `currency` | `assets.currency`. |
| `quantity` | `holdings.quantity`. |
| `averagePurchasePrice` | `holdings.average_cost`. |
| `lastPrice`, `marketValue` | `price_snapshots` or optional reporting fields. |

Recommended safety rules:

- Start with a preview-confirm sync, not automatic destructive overwrite.
- Track Toss-origin holdings separately or store a source/mapping field before
  changing current local holdings.
- Do not delete local holdings just because Toss does not return them.
- Keep cash, savings, debt, manual goals, backups, and snapshots local.

### 6.5 Order History Import

Useful for reducing manual buy/sell entry, but not a complete ledger replacement.

Current behavior:

- Local `buy` and `sell` transactions update holdings.
- Dividends, interest, deposits, withdrawals, fees, debt payments, and adjustments
  are also first-class local transaction types.

Toss order history can provide:

- order ID, symbol, side, order type, status, ordered time, quantity, price,
  currency, execution average price, filled quantity, filled amount, commission,
  tax, filled time, and settlement date.

Recommended use:

- Import filled orders as proposed local `buy` or `sell` transactions.
- Use `orderId` as an external id if a schema field is added.
- Reconcile partial fills carefully.
- Store commission and tax either as separate fee transactions or in new fields
  after a schema decision.

This is lower priority than holdings and price sync because the current local
transaction model does not yet have an external order identity or detailed
execution model.

### 6.6 Trading

Toss order creation, modification, and cancellation should be treated as a new
product area, not a replacement for existing tracking functions.

If added later, it needs:

- A dedicated trading screen or flow.
- Explicit confirmations for every order.
- High-value order handling.
- Market-hours checks using Toss market calendar APIs.
- Buying-power and sellable-quantity pre-checks.
- Clear display of expected versus executed price.
- Idempotency or client-order-id handling where supported by the API contract.
- A way to import the resulting executed order back into the local ledger.

The current app is designed as a local portfolio tracker. Adding trading changes
the risk profile and should be a separate design document.

## 7. Features Toss Should Not Replace

These features should remain local:

| Feature | Reason |
| --- | --- |
| Cash, savings, and debt tracking | Toss holdings API is stock-holdings oriented and does not model the app's full personal balance sheet. |
| Goals | Net-worth and monthly-income goals are user-defined local planning data. |
| Backups | Local SQLite backup policy is unrelated to brokerage APIs. |
| Portfolio snapshots and growth history | The app calculates these from local summary state and cashflow semantics. |
| Manual adjustments | Needed for onboarding, corrections, non-Toss assets, and unsupported products. |
| Manual onboarding and adjustments | Still useful for initial balances, corrections, and non-brokerage data. |
| Transaction semantics beyond orders | Deposits, withdrawals, dividends, interest, fees, and debt payments are broader than Toss order history. |

## 8. Recommended Adoption Plan

### Phase 1: Read-Only Market Data Provider

Add Toss as a backend-only market-data and FX provider.

Deliverables:

- OAuth client credentials configuration through environment variables.
- Token fetch and cache module.
- Toss price provider for KR and US `stock_etf` assets.
- Toss FX provider for USD/KRW.
- Existing `price_snapshots` and `fx_rates` persistence retained.
- Settings page shows source/status but does not expose secrets.

This phase replaces the most fragile current area while keeping local summary
logic unchanged.

### Phase 2: Stock Metadata Validation

Use Toss stock info during stock/ETF asset creation.

Deliverables:

- Symbol lookup endpoint in the local backend.
- Auto-fill name, currency, and market in the holdings screen.
- Optional warning badges for active stock warnings.

This reduces manual data entry errors without changing the ledger.

### Phase 3: Brokerage Holdings Sync Preview

Add read-only Toss account and holdings import preview.

Deliverables:

- List Toss accounts.
- Let the user choose a Toss brokerage account.
- Show a diff between Toss holdings and local holdings.
- Confirm before creating assets or updating local holdings.
- Record source metadata or external mapping before any automatic reconciliation.

This should be preview-confirm first. Automatic overwrites can come later only
after mapping and conflict behavior are explicit.

### Phase 4: Order History Reconciliation

Import filled orders as local buy/sell transactions.

Deliverables:

- Store external `orderId` or a deduplication key.
- Handle partial fills and commissions.
- Show a review table before writing local transactions.
- Preserve local transaction semantics for non-order events.

### Phase 5: Trading Flow

Only consider this after read-only integration is stable.

Deliverables:

- Separate order-entry UX.
- Pre-trade checks with buying power, sellable quantity, commission, market
  calendar, price limits, and warnings.
- Confirmation flow and post-trade reconciliation.

## 9. Implementation Considerations

Credential handling:

- Keep `client_id` and `client_secret` only in backend settings or environment.
- Do not send Toss secrets to the frontend.
- Account sequence can be stored as local settings after the user selects an
  account.

Rate limits and retries:

- Respect Toss rate-limit response headers.
- On `429`, retry after `Retry-After`.
- Use exponential backoff with jitter for background sync.
- Batch price and stock-info requests up to documented limits.

Local data model:

- Prefer adding provider classes before changing schema.
- For holdings sync and order import, likely add external mapping fields or new
  tables instead of overloading existing local IDs.
- Continue persisting provider results locally so the dashboard is not coupled to
  live API availability.

Error handling:

- Convert Toss error envelopes into Korean user-facing messages.
- Preserve request IDs in logs for troubleshooting.
- Keep provider failures non-destructive: stale price is better than wiping a
  usable local valuation.

Testing:

- Add provider-level unit tests with mocked Toss responses.
- Add service tests for price and FX persistence.
- Add preview-confirm tests before enabling holdings sync writes.
- Avoid live Toss API calls in normal test runs.

## 10. Final Recommendation

Start with Phase 1: replace market price and FX provider logic with Toss-backed
read-only providers while preserving existing local storage and summary
calculation.

This gives the largest immediate benefit:

- KR stock/ETF price sync becomes possible.
- US stock/ETF sync no longer depends on Alpha Vantage.
- USD/KRW refresh can use one official brokerage data source.
- The dashboard and growth snapshots can keep their existing local query path.

Do not start with order placement. It is technically available, but it is a
different product surface from the current local portfolio tracker and needs a
separate safety-first design.

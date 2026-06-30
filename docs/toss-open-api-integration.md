# Toss Securities Open API Integration

Date: 2026-06-30
Status: Toss-only brokerage portfolio slice with manual Growth History implemented

## 1. Product Direction

Current product direction for the brokerage slice is Toss-only.

`accounts`, `assets`, `holdings`, and `transactions` are no longer the source of
truth for brokerage data. Toss `GET /api/v1/accounts` and `GET /api/v1/holdings`
own the displayed account and stock/ETF holding state. SQLite remains for app
settings, goals, backups, migration bookkeeping, FX cache data, and imported
read-only Toss order history.

Removed behavior:

- local account creation,
- local asset creation,
- local initial balance setup,
- local transaction entry,
- transaction-derived growth history.

Known limitation: Toss holdings currently cover KR/US stock holdings, not the
app's former cash, savings, debt, manual adjustment, or full personal-finance
ledger features.

The new Growth History screen is separate from that removed local-ledger model.
It stores Toss-account-scoped manual monthly history and derives annual history
from those monthly entries. It does not recreate transaction-derived growth,
local holdings, or old portfolio snapshots.

## 2. Toss APIs In Use

| Product need | Toss API | Local surface |
| --- | --- | --- |
| Brokerage account list | `GET /api/v1/accounts` | `GET /api/toss/accounts` |
| Brokerage holdings | `GET /api/v1/holdings` with `X-Tossinvest-Account` | `GET /api/toss/holdings?account_seq=...` |
| Held stock/ETF candles | `GET /api/v1/candles` | `GET /api/toss/candles?symbol=...` |
| Order-history import | `GET /api/v1/orders` with `X-Tossinvest-Account` | `POST /api/toss/order-imports` |
| Imported order-history list | Local SQLite cache populated from `GET /api/v1/orders` | `GET /api/toss/orders?account_seq=...` |
| Order detail parsing | `GET /api/v1/orders/{orderId}` with `X-Tossinvest-Account` | Backend provider/parser boundary |
| USD/KRW valuation | `GET /api/v1/exchange-rate` | `GET /api/summary?account_seq=...` |
| Buying power | `GET /api/v1/buying-power` with `X-Tossinvest-Account` and `currency=KRW\|USD` | `GET /api/toss/buying-power?account_seq=...`, `GET /api/summary?account_seq=...` |
| OAuth token | `POST /oauth2/token` | Backend-only provider boundary |

All Toss credentials stay on the backend. The frontend only receives normalized
account, holding, candle, buying-power, order-history, summary, goal, and backup
response models.

## 3. Local Persistence Boundary

SQLite tables that remain in the fresh schema:

- `schema_migrations`
- `settings`
- `fx_rates`
- `goals`
- `backups`
- `toss_order_import_runs`
- `toss_orders`
- `growth_month_history`
- `sp500_proxy_prices`

The app no longer creates source-of-truth local tables for Toss brokerage
accounts, assets, holdings, transactions, market price snapshots, or growth
snapshots. Migration v10 drops the old local ledger tables and preserves
survivor data such as goals, backups, settings, and FX rates. Migration v11 adds
the Toss order-history import cache tables. Migration v12 adds
`growth_month_history`. Migration v13 adds `sp500_proxy_prices`; migration v14
seeds 2021~2025 VOO year-end prices without overwriting existing user-edited
proxy prices.

Imported Toss order history is read-only historical data. It does not mutate
holdings, replace the removed `/api/transactions` command path, drive current
holdings valuation, or create growth snapshots. Current holdings and valuation
still come from live Toss holdings plus Toss-derived buying power, with KRW
buying power treated as cash and USD buying power converted through the same
Toss USD/KRW FX rate used for USD holdings.

Growth History is local, manual, and scoped by Toss `account_seq`. Users record
monthly net worth and monthly dividend values in `growth_month_history`;
`GET /api/growth/month-history` returns the account's monthly history, and
`GET /api/growth/annual-history` derives annual history from the latest saved
month in each year. These records are not local holdings, transaction rollups, or
old `portfolio_snapshots`.

S&P 500 annual growth is derived from the global `sp500_proxy_prices` VOO proxy
price table, not from Toss holdings. The current unfinished calendar year keeps
that benchmark field blank.

## 4. Summary Behavior

`GET /api/summary` now requires `account_seq`.

The backend fetches Toss holdings for the selected account and builds the
portfolio summary from those live holdings:

- KRW holdings contribute their Toss market value directly.
- USD holdings require a Toss USD/KRW FX rate and are converted to KRW.
- KRW and USD buying power are fetched live for the selected account.
- KRW buying power contributes directly to cash.
- USD buying power is converted with the same Toss USD/KRW rate used for USD
  holdings.
- Gross assets and net worth are equal for this slice because local debt is no
  longer modeled.
- Monthly income is `0` because local transaction-derived income has been
  removed.
- Goal progress is calculated against Toss holdings plus converted buying power.

## 5. Frontend Behavior

The dashboard and holdings page load Toss accounts first, keep a selected
`account_seq`, and request account-scoped holdings, buying power, or summary
data. The dashboard includes Toss-derived buying power in summary values and
goal progress. The holdings page is read-only and displays KRW/USD buying power
for the selected Toss account.

The chart page also starts from the selected Toss account's holdings. It keeps a
single chart panel, lets the user select one held stock/ETF, and requests
normalized OHLCV candles from `GET /api/toss/candles`. Candle data is read-only
and is not persisted to SQLite.

The Growth History page uses the same selected Toss account. It lets the user
manually save month-level net worth and dividend values, then displays monthly
history plus annual history derived from those saved month rows. Annual history
also includes the seeded VOO-based `S&P 500 연 성장률` benchmark for completed
years.

The order-history page loads imported orders from the local read-only cache and
can start an order-history import for the selected Toss account. OPEN order
imports are supported through the Toss order list API. CLOSED imports can fail
while the Toss OpenAPI reports `closed-not-supported`; the app records the failed
import run and surfaces the provider failure instead of assuming closed history
is available.

The app no longer mounts transaction entry, transaction-derived growth history,
local market-sync status, local account creation, local asset creation, or
initial balance setup views.

## 6. Error Handling

Provider errors are translated into backend API errors without exposing Toss
credentials, access tokens, or provider response bodies. Toss HTTP failures are
reported as Korean user-facing 502 responses such as:

```text
Toss 요청 실패: HTTP 500 Internal Server Error
```

### Rate-limit mitigation

Toss rate limits are enforced per client and API group. The backend reduces
burst traffic in three places:

- a single app-scoped `TossAuthClient` reuses the OAuth access token across
  account, holding, order-history, summary, and FX API calls;
- `/api/toss/accounts` uses a short in-memory TTL cache so repeated dashboard
  and holdings page loads do not hit the `ACCOUNT` group every time;
- Toss providers retry one `429` response after the provider's `Retry-After`
  header, falling back to `X-RateLimit-Reset` when `Retry-After` is absent.

The cache is process-local and intentionally short-lived. It protects the local
UI from refresh and React development-mode duplicate requests without making
Toss account data a durable local source of truth.

Validation errors such as a blank `account_seq`, malformed Toss account items,
or unsupported holding market/currency combinations return 400-level responses
or service-level `ValueError`s in tests.

## 7. Future Work

These areas are outside the current Toss-only brokerage slice:

- Toss order placement.
- Confirmed CLOSED order-history availability if Toss enables it beyond the
  current `closed-not-supported` behavior.
- Cash, savings, debt, and non-stock products.
- Local manual onboarding or adjustment flows.

If any of those features return, they need a new product and schema design
instead of reusing the removed local ledger path.

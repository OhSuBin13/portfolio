# Toss Securities Open API Integration

Date: 2026-06-29
Status: Toss-only brokerage portfolio slice implemented

## 1. Product Direction

Current product direction for the brokerage slice is Toss-only.

`accounts`, `assets`, `holdings`, and `transactions` are no longer the source of
truth for brokerage data. Toss `GET /api/v1/accounts` and `GET /api/v1/holdings`
own the displayed account and stock/ETF holding state. SQLite remains for app
settings, goals, backups, migration bookkeeping, and optional provider cache
data only.

Removed behavior:

- local account creation,
- local asset creation,
- local initial balance setup,
- local transaction entry,
- transaction-derived growth history.

Known limitation: Toss holdings currently cover KR/US stock holdings, not the
app's former cash, savings, debt, manual adjustment, or full personal-finance
ledger features.

## 2. Toss APIs In Use

| Product need | Toss API | Local surface |
| --- | --- | --- |
| Brokerage account list | `GET /api/v1/accounts` | `GET /api/toss/accounts` |
| Brokerage holdings | `GET /api/v1/holdings` with `X-Tossinvest-Account` | `GET /api/toss/holdings?account_seq=...` |
| USD/KRW valuation | `GET /api/v1/exchange-rate` | `GET /api/summary?account_seq=...` |
| OAuth token | `POST /oauth2/token` | Backend-only provider boundary |

All Toss credentials stay on the backend. The frontend only receives normalized
account, holding, summary, goal, and backup response models.

## 3. Local Persistence Boundary

SQLite tables that remain in the fresh schema:

- `schema_migrations`
- `settings`
- `fx_rates`
- `goals`
- `backups`

The app no longer creates source-of-truth local tables for Toss brokerage
accounts, assets, holdings, transactions, market price snapshots, or growth
snapshots. Migration v10 drops the old local ledger tables and preserves
survivor data such as goals, backups, settings, and FX rates.

## 4. Summary Behavior

`GET /api/summary` now requires `account_seq`.

The backend fetches Toss holdings for the selected account and builds the
portfolio summary from those live holdings:

- KRW holdings contribute their Toss market value directly.
- USD holdings require a Toss USD/KRW FX rate and are converted to KRW.
- Gross assets and net worth are equal for this slice because local debt is no
  longer modeled.
- Monthly income is `0` because local transaction-derived income has been
  removed.
- Goal progress is still local and is calculated against the Toss-derived
  summary.

## 5. Frontend Behavior

The dashboard and holdings page load Toss accounts first, keep a selected
`account_seq`, and request account-scoped holdings or summary data. The holdings
page is read-only.

The app no longer mounts transaction entry, growth history, local market-sync
status, local account creation, local asset creation, or initial balance setup
views.

## 6. Error Handling

Provider errors are translated into backend API errors without exposing Toss
credentials, access tokens, or provider response bodies. Toss HTTP failures are
reported as Korean user-facing 502 responses such as:

```text
Toss 요청 실패: HTTP 500 Internal Server Error
```

Validation errors such as a blank `account_seq`, malformed Toss account items,
or unsupported holding market/currency combinations return 400-level responses
or service-level `ValueError`s in tests.

## 7. Future Work

These areas are outside the current Toss-only brokerage slice:

- Toss order placement.
- Toss order-history import.
- Cash, savings, debt, and non-stock products.
- Local manual onboarding or adjustment flows.
- A new growth-history model based on a future durable snapshot source.

If any of those features return, they need a new product and schema design
instead of reusing the removed local ledger path.

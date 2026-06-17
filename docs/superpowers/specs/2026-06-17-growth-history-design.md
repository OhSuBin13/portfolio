# Growth History Design

Date: 2026-06-17
Status: Approved for specification review
Reference: `docs/Growth_History.png`

## 1. Purpose

Build a growth history feature for the private local portfolio app. The feature
records daily net worth snapshots and derives monthly and annual growth history
from those snapshots.

The goal is to distinguish actual portfolio growth from external cash movement.
Additional deposits, withdrawals, and debt payments must not inflate or reduce
the reported growth rate. Dividends and interest are investment results, so they
are included in monthly profit and monthly growth.

This feature should prepare the app for a later Toss Securities API integration,
but it must not depend on Toss data. Toss should later act as one data provider
that feeds the same internal snapshot and growth calculation model.

## 2. Product Scope

Included:

- Save one daily portfolio snapshot per KST date.
- Create the daily snapshot automatically after market sync completes when the
  current KST date has no snapshot yet.
- Let the user manually refresh today's snapshot.
- Calculate monthly growth from daily snapshots.
- Calculate annual growth from daily snapshots.
- Exclude external deposits, withdrawals, and debt payments from profit and
  growth rate.
- Include dividends, interest, realized profit, unrealized profit, and FX-driven
  valuation movement in profit and growth rate.
- Show first-month or missing-baseline growth rate as `-` instead of dividing by
  zero.

Out of scope for this feature:

- Direct Toss Securities API integration.
- Hosted or multi-user reporting.
- Tax reporting.
- Time-weighted return or money-weighted return calculations.
- Per-broker performance attribution.

## 3. Growth Calculation Contract

The app uses KRW as the base currency for all growth history calculations.

Monthly calculation:

```text
net_external_cash_flow_krw = deposits_krw + debt_payments_krw - withdrawals_krw
monthly_profit_krw = ending_net_worth_krw - starting_net_worth_krw - net_external_cash_flow_krw
monthly_growth_rate = monthly_profit_krw / starting_net_worth_krw
```

Annual calculation follows the same rule over the year:

```text
annual_net_external_cash_flow_krw = annual_deposits_krw + annual_debt_payments_krw - annual_withdrawals_krw
annual_profit_krw = ending_net_worth_krw - starting_net_worth_krw - annual_net_external_cash_flow_krw
annual_growth_rate = annual_profit_krw / starting_net_worth_krw
```

Rules:

- `starting_net_worth_krw` is the first available daily snapshot in the month or
  year.
- `ending_net_worth_krw` is the last available daily snapshot in the month or
  year.
- External deposits, withdrawals, and debt payments are excluded from profit.
- Dividends and interest are included in profit.
- If `starting_net_worth_krw` is missing or less than or equal to zero, return a
  profit amount but no growth rate.
- Growth rate should be stored or returned as a decimal ratio and formatted as a
  percentage only in the UI.

Transaction classification:

- External contributions: `deposit`, `debt_payment`.
- External withdrawals: `withdrawal`.
- Investment income: `dividend`, `interest`.
- Costs that affect return: `fee`.
- Debt payments are treated as external contributions for growth calculations.
  They reduce debt and increase net worth, but they are not investment profit.
- Manual adjustments should be included in the resulting net worth. If a manual
  adjustment represents an external cash movement, the user should record it as
  a deposit or withdrawal instead.

## 4. Data Model

Add a daily snapshot record that captures the portfolio state for one KST date.

Proposed table: `portfolio_snapshots`

- `id`
- `snapshot_date`: KST date, unique.
- `net_worth_krw`
- `gross_assets_krw`
- `debt_krw`
- `monthly_income_krw`: current calendar-month dividend and interest value at
  capture time, for display context only.
- `asset_mix_json`: optional serialized asset mix at capture time.
- `source`: `scheduled`, `manual`, `market_sync`, or `import`.
- `created_at`
- `updated_at`

The daily snapshot stores state. Monthly and annual growth rows can be computed
from snapshots and transactions on demand. A cached aggregate table can be added
later if the query becomes expensive, but it is unnecessary for the MVP-sized
local app.

Future Toss integration should not write broker-specific growth history directly.
It should update holdings, transactions, prices, and FX data first, then trigger
the same snapshot creation path.

## 5. Backend Design

Add a growth history service with three responsibilities:

- Create or refresh today's snapshot from the existing portfolio summary logic.
- Read snapshots for a date range.
- Build monthly and annual growth rows from snapshots plus transaction cashflow.

The service should reuse the existing summary calculation rather than duplicate
valuation rules. This keeps debt handling, FX conversion, latest prices, and
manual prices consistent with the dashboard.

Suggested API shape:

- `POST /api/growth/snapshots/today`
  - Creates or refreshes today's KST snapshot.
  - Accepts an optional source value.
  - Returns the stored snapshot.
- `GET /api/growth/snapshots?from=YYYY-MM-DD&to=YYYY-MM-DD`
  - Returns daily snapshots in date order.
- `GET /api/growth/history?period=monthly&from=YYYY-MM&to=YYYY-MM`
  - Returns monthly growth rows.
- `GET /api/growth/history?period=annual&from=YYYY&to=YYYY`
  - Returns annual growth rows.

Automatic snapshot trigger:

- After market sync finishes successfully or with stale prices, check whether
  today's KST snapshot exists.
- If it does not exist, create one.
- If market sync fully fails before any usable valuation can be calculated,
  skip automatic snapshot creation and expose the failure in the sync result.
- Manual refresh can overwrite today's values because the date is unique.

## 6. Frontend Design

Add a `성장기록` view that follows the spreadsheet reference while fitting the
current app layout.

Initial UI:

- Monthly table with year, month, net worth, monthly profit, monthly growth rate,
  cumulative growth rate, and dividend/interest amount.
- Annual table with year, net worth, annual profit, annual growth rate,
  cumulative growth rate, and cumulative dividend/interest amount.
- A compact status row showing the latest snapshot date and a button to refresh
  today's snapshot.

Formatting:

- KRW amounts use Korean number formatting.
- Positive growth uses the app's positive style, negative growth uses the
  negative style, and unavailable growth shows `-`.
- The table should remain readable before a chart is added.

Charts can be added after the table contract is stable.

## 7. Error Handling

Snapshot creation should fail clearly when the current portfolio summary cannot
be calculated, for example because a non-KRW asset has no FX rate. The error
message should use the existing Korean API error style and should not write a
partial snapshot.

Manual refresh should show whether today's snapshot was created or updated.

If a monthly or annual range has fewer than two snapshots, the API should still
return the available row with profit and growth rate set according to the
baseline rules. The UI should show missing rates as `-`.

## 8. Testing Strategy

Backend tests:

- Daily snapshot creation stores one row per KST date.
- Manual refresh updates today's snapshot rather than creating duplicates.
- Monthly profit excludes deposits and withdrawals.
- Monthly profit excludes debt payments.
- Monthly profit includes dividends and interest.
- Monthly growth rate uses monthly starting net worth as the denominator.
- Zero or missing starting net worth returns no growth rate.
- Annual growth is derived from daily snapshots and annual external cashflow.
- Automatic market sync creates a snapshot only when valuation is usable.

Frontend tests:

- Growth history view renders monthly and annual tables.
- Missing growth rates render as `-`.
- Manual refresh button calls the snapshot endpoint.
- Positive and negative rates use distinct styling.

## 9. Implementation Order

1. Add the snapshot schema and migration path.
2. Add backend models for daily snapshot and growth rows.
3. Add the growth history service and unit tests for calculation rules.
4. Add growth history API endpoints and HTTP tests.
5. Hook automatic snapshot creation into market sync completion.
6. Add the frontend `성장기록` view and navigation entry.
7. Add focused frontend tests.

This feature should be implemented before Toss integration so that Toss can be
attached to a stable internal growth model instead of defining the growth model
itself.

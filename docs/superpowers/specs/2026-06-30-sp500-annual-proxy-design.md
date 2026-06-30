# S&P 500 Annual Proxy Growth Design

## Goal

Add `S&P 500 연 성장률` to `Growth Annual History`.

The value uses an ETF proxy instead of a direct index feed. The proxy ETF is `VOO`, matching the existing portfolio examples and stock/ETF data model. The current unfinished calendar year must not display this value.

## Data Contract

`GrowthAnnualHistoryRow` will gain a nullable field:

- `sp500_annual_return_ratio: float | null`

The value is a return ratio, consistent with the existing growth history contract. The frontend will format it with the same percent-change display used for portfolio annual returns.

## Calculation

For a completed year `Y`, find the latest usable `price_snapshots` row for `VOO` at or before:

- Start point: December 31 of `Y - 1`
- End point: December 31 of `Y`

If both prices exist and the start price is greater than zero:

```text
sp500_annual_return_ratio = end_price / start_price
```

If either price is missing, the start price is zero, or the annual row belongs to the current calendar year, the field is `null`.

## Backend Shape

The annual history endpoint remains `/api/growth/annual-history`.

Implementation will keep growth-history assembly in `services/growth_history.py`, with a small repository query for ETF proxy prices. The route will fetch the annual proxy map and pass it into `build_annual_history`.

No schema migration is needed because this derives from existing `assets` and `price_snapshots` data.

## Frontend Shape

`Growth Annual History` gains one numeric column:

- `S&P 500 연 성장률`

The cell uses existing return percent formatting and positive/negative color classes. Current-year rows and missing proxy data render as `-`.

## Testing

Backend tests will cover:

- Annual response includes `sp500_annual_return_ratio`.
- Completed years calculate from `VOO` price snapshots.
- Current calendar year returns `null` even if a price exists.
- Missing proxy price data returns `null`.

Frontend source tests will cover:

- The new column label exists.
- The new field is rendered through the return formatter.
- The existing return-tone classes apply to the new column.

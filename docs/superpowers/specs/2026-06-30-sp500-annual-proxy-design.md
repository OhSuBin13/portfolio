# S&P 500 Annual Proxy Growth Design

## Goal

Add `S&P 500 연 성장률` to `Growth Annual History`.

The value uses an ETF proxy instead of a direct index feed. The proxy ETF is `VOO`. The current Toss-only schema no longer has local `assets` or `price_snapshots`, so the app stores a small global table of annual VOO year-end prices.

The current unfinished calendar year must not display this value.

## Data Contract

`GrowthAnnualHistoryRow` will gain a nullable field:

- `sp500_annual_return_ratio: float | null`

The value is a return ratio, consistent with the existing growth history contract. The frontend will format it with the same percent-change display used for portfolio annual returns.

The app will store annual VOO proxy prices internally in `sp500_proxy_prices`:

- `year: int`
- `proxy_symbol: "VOO"`
- `price: float` (unadjusted Close/Last for the final trading day of the year)
- `currency: "USD"`
- `created_at: str`
- `updated_at: str`

Initial seed data:

| Year | Final trading day | VOO close |
| --- | --- | ---: |
| 2021 | 2021-12-31 | 436.57 |
| 2022 | 2022-12-30 | 351.34 |
| 2023 | 2023-12-29 | 436.80 |
| 2024 | 2024-12-31 | 538.81 |
| 2025 | 2025-12-31 | 627.13 |

These values come from Nasdaq historical data for `VOO`, queried for 2021-12-01 through 2025-12-31. The stored source label is `nasdaq`.

## Calculation

For a completed year `Y`, find the saved VOO year-end price rows for:

- Start point: year `Y - 1`
- End point: year `Y`

If both prices exist and the start price is greater than zero:

```text
sp500_annual_return_ratio = end_price / start_price
```

If either price is missing, the start price is zero, or the annual row belongs to the current calendar year, the field is `null`.

## Backend Shape

The annual history endpoint remains `/api/growth/annual-history`.

Implementation will keep growth-history assembly in `services/growth_history.py`, with a small repository query for ETF proxy prices. The route will fetch the annual proxy map and pass it into `build_annual_history`.

Schema version `13` will add `sp500_proxy_prices`:

- one row per `proxy_symbol` and `year`
- `price > 0`
- `year` between 2000 and 2099
- default `proxy_symbol = 'VOO'`
- default `currency = 'USD'`
- seeded 2021 through 2025 VOO year-end close prices

The annual history response derives S&P 500 growth from these saved rows. No proxy-price editing API is included in this change; that can be added later if maintaining future annual prices through the UI becomes necessary.

## Frontend Shape

`Growth Annual History` gains one numeric column:

- `S&P 500 연 성장률`

The cell uses existing return percent formatting and positive/negative color classes. Current-year rows and missing proxy data render as `-`.

## Testing

Backend tests will cover:

- Annual response includes `sp500_annual_return_ratio`.
- Completed years calculate from saved VOO annual proxy prices.
- Current calendar year returns `null` even if a price exists.
- Missing proxy price data returns `null`.
- Schema migration creates `sp500_proxy_prices` in fresh and v12 databases.
- Fresh and migrated schemas seed 2021 through 2025 VOO year-end close prices.

Frontend source tests will cover:

- The new column label exists.
- The new field is rendered through the return formatter.
- The existing return-tone classes apply to the new column.

# CAN SLIM Analysis Design

## Goal

Add a dedicated CAN SLIM analysis screen for arbitrary US-listed stock symbols.

The feature is a research checklist, not a buy/sell recommendation engine. It
shows each CAN SLIM letter with source-backed evidence, missing-data states, and
the time/source of the data used.

## Scope

The v1 scope is US common stocks only.

Supported:

- Search by ticker, such as `NVDA` or `AAPL`.
- Analyze US-listed common stocks through a backend-owned FMP provider.
- Show C/A/N/S/L/I/M evidence with `pass`, `watch`, `fail`, `unknown`, or `info`
  states.
- Show institutional flow and top-performing institutional holders for I.
- Show SPY chart, volume, and traded value for M without making a market
  direction judgment.

Out of scope for v1:

- Korean stocks.
- ETFs as the analyzed target symbol.
- Automatic news/product launch detection for N.
- Automatic ranking across many symbols.
- Buy/sell recommendation text.
- Frontend direct calls to FMP.

SPY is still used as the market context instrument for M, even though ETFs are
not accepted as the analyzed target symbol.

## Data Provider

Use Financial Modeling Prep (FMP) as the first provider. FMP is the best fit for
v1 because it can cover financial statements, earnings, historical price/volume,
shares float, institutional positions, and holder performance behind one
backend provider boundary.

Backend settings:

- `PORTFOLIO_FMP_API_KEY`

The key stays backend-only, following the existing Toss credential pattern.
Frontend code never receives or calls the FMP key.

Provider caveat:

- FMP's 13F institutional holdings data appears to require an Ultimate-tier
  plan. If the configured key cannot access 13F data, the I letter returns
  `unknown` while the remaining letters still render.

Reference sources checked on 2026-07-06:

- FMP API docs: https://site.financialmodelingprep.com/developer/docs
- FMP pricing: https://site.financialmodelingprep.com/developer/docs/pricing
- FMP shares float docs: https://site.financialmodelingprep.com/developer/docs/stable/shares-float
- FMP positions summary docs: https://site.financialmodelingprep.com/developer/docs/stable/positions-summary
- FMP holder performance summary docs: https://site.financialmodelingprep.com/developer/docs/stable/holder-performance-summary

## CAN SLIM Rules

Each letter returns a status, headline, details, metrics, source, and `as_of`
timestamp. Missing source fields do not fail the whole analysis; they make only
the affected letter `unknown`.

### C: Current Quarterly Earnings

Use latest quarterly EPS year-over-year growth.

- `pass`: EPS YoY growth is at least 25%.
- `watch`: EPS YoY growth is from 0% to below 25%.
- `fail`: EPS YoY growth is negative.
- `unknown`: current or comparable prior-year quarter EPS is unavailable.

### A: Annual Earnings Increase

Use the latest three completed fiscal years of annual EPS.

- `pass`: EPS is positive, grows year over year, and 3-year EPS CAGR is at least
  25%.
- `watch`: EPS growth is positive overall but not continuously above the pass
  rule.
- `fail`: annual EPS declines materially, turns negative, or the 3-year CAGR is
  negative.
- `unknown`: fewer than three completed annual EPS values are available.

### N: New Products, Services, Or Events

v1 does not infer new products, services, or events.

Return `info` with:

- company name
- exchange
- sector
- industry
- business description

The UI label should make this explicit as company context, not an automatic
new-event detector.

### S: Supply And Demand

Use historical daily price/volume plus share float data.

- `pass`: the latest completed trading day closed above the previous close and
  had volume at least 1.5x the recent 50-trading-day average.
- `watch`: the latest completed trading day closed above the previous close and
  had volume from 1.2x to below 1.5x average, or volume is strong but float is
  very large.
- `fail`: the latest completed trading day did not close above the previous
  close, or it rose without at least 1.2x volume confirmation.
- `unknown`: insufficient price/volume or float data.

Show:

- latest close
- latest volume
- 50-day average volume
- volume ratio
- float shares
- shares outstanding when available

### L: Leader Or Laggard

Use 6-month and 12-month stock performance versus SPY and sector/industry peers
when peer data is available from FMP.

- `pass`: relative-strength percentile is at least 80.
- `watch`: percentile is from 60 to below 80.
- `fail`: percentile is below 60.
- `unknown`: insufficient price history or peer set.

If sector peers are unavailable, compute the SPY-relative component and mark the
peer-ranking metric as `unknown` instead of inventing a peer result.

### I: Institutional Sponsorship

I has two layers.

`institutional_flow` summarizes whether institutions are increasing or reducing
exposure to the target stock:

- holder count change
- share count change percentage
- ownership percentage
- market value change

`top_performing_holders` shows whether high-performing institutional investors
hold the stock:

- holder name
- CIK
- shares
- market value
- position change percentage
- portfolio weight percentage
- 1-year, 3-year, and 5-year holder performance
- excess performance versus S&P 500

Status:

- `pass`: institutional flow is positive and at least one top-performing holder
  has a meaningful position or has increased the position.
- `watch`: mixed institutional flow or top-performing holders are present but
  position changes are flat.
- `fail`: institutional flow is negative and no top-performing holder support is
  evident.
- `unknown`: 13F access is unavailable or data is insufficient.

API-call control:

- Fetch detailed holder performance for only the top N holders, initially 10.
- Cache institutional data for 24 hours.

### M: Market Direction

M does not compute a pass/watch/fail judgment in v1.

Return `info` only with SPY market context:

- SPY daily OHLC candles
- SPY daily volume
- SPY traded value in USD

Traded value calculation:

- Prefer `vwap * volume` when the provider response has a reliable VWAP field.
- Otherwise use `close * volume`.

Supported M chart ranges:

- 3 months
- 6 months
- 1 year

The UI must not display market-direction verdict text. The user interprets the
SPY chart, volume, and traded value directly.

## Backend API

Add one public local API:

```text
GET /api/canslim/analysis?symbol=NVDA
GET /api/canslim/analysis?symbol=NVDA&refresh=true
GET /api/canslim/analysis?symbol=NVDA&market_range=1y
```

Behavior:

- Trim and uppercase `symbol`.
- Accept `market_range` values `3m`, `6m`, and `1y`; default to `6m`.
- Reject blank symbols with HTTP 400.
- Reject unsupported non-US or non-common-stock targets with HTTP 400 and a
  Korean message stating that CAN SLIM v1 supports US-listed common stocks only.
- Use cache unless `refresh=true` is provided.
- Return partial results when only optional data such as 13F holder data is
  unavailable.
- Hide FMP response bodies and secrets from frontend-visible errors.

High-level response:

```ts
type CanslimAnalysis = {
  symbol: string
  company_name: string
  exchange: string
  sector: string | null
  industry: string | null
  description: string
  currency: "USD"
  provider: "fmp"
  generated_at: string
  cached: boolean
  letters: {
    c: CanslimLetter
    a: CanslimLetter
    n: CanslimLetter
    s: CanslimLetter
    l: CanslimLetter
    i: CanslimInstitutionalLetter
    m: CanslimMarketContext
  }
}

type CanslimLetter = {
  status: "pass" | "watch" | "fail" | "unknown" | "info"
  headline: string
  details: string[]
  metrics: Record<string, number | string | null>
  source: string
  as_of: string | null
}

type CanslimInstitutionalLetter = CanslimLetter & {
  institutional_flow: {
    holders_count_change: number | null
    shares_change_percent: number | null
    ownership_percent: number | null
    market_value_change_percent: number | null
  }
  top_performing_holders: {
    holder_name: string
    cik: string
    shares: number
    market_value: number
    position_change_percent: number | null
    portfolio_weight_percent: number | null
    performance_1y_percent: number | null
    performance_3y_percent: number | null
    performance_5y_percent: number | null
    excess_vs_sp500_percent: number | null
  }[]
}

type CanslimMarketContext = {
  status: "info"
  symbol: "SPY"
  range: "3m" | "6m" | "1y"
  candles: {
    date: string
    open: number
    high: number
    low: number
    close: number
    volume: number
    traded_value_usd: number
  }[]
  source: "fmp"
  as_of: string | null
}
```

## Persistence

Add a cache table only. CAN SLIM analysis is derived from provider data and does
not become portfolio source-of-truth state.

```sql
create table canslim_cache_entries (
  cache_key text primary key,
  provider text not null,
  payload_json text not null,
  fetched_at text not null,
  expires_at text not null
);
```

Cache TTL:

- Company profile, financials, EPS, float, institutional data: 24 hours.
- Price/volume and SPY market context: 1 hour.
- `refresh=true`: bypass current cache and replace it after a successful fetch.

Cache keys should include symbol, provider, payload category, and range where
applicable.

## Frontend

Add a new nav item:

```text
CAN SLIM
```

Add `CanslimPage.tsx` with an immediate tool surface, not a landing page.

Layout:

- Top controls: ticker input, analyze button, refresh button.
- Company summary: name, exchange, sector, industry, business description,
  provider, generated time, cache state.
- Status tiles: C/A/N/S/L/I/M.
- Evidence table: letter, status, headline, key metrics, source.
- Institutional section: flow summary and top-performing holders table.
- Market context section: SPY candle chart, volume, traded value.

UI behavior:

- Default example symbol may be empty; do not auto-call external APIs on page
  mount.
- Preserve the user's typed symbol.
- Show loading and per-analysis errors.
- Use `unknown` UI styling for missing data rather than hiding a letter.
- Label M as market context data, not a verdict.

## Testing

Backend tests:

- FMP settings and missing-key behavior.
- FMP provider parsing for profile, financials, earnings, price/volume, float,
  positions summary, and holder performance.
- C/A/S/L/I rule classification.
- M returns SPY candles, volume, and traded value without pass/watch/fail.
- Partial 13F failure makes only I `unknown`.
- Cache hit, miss, expiry, and `refresh=true`.
- Fresh schema and migration create `canslim_cache_entries`.
- API rejects blank symbols and unsupported targets.
- OpenAPI exposes `/api/canslim/analysis`.

Frontend tests:

- App shell exposes `CAN SLIM`.
- App mounts `CanslimPage`.
- Page calls `/api/canslim/analysis?symbol=...`.
- Refresh uses `refresh=true`.
- Tiles render C/A/N/S/L/I/M statuses.
- Institutional holder table renders top-performing holder fields.
- M section renders SPY candles, volume, and traded value labels.
- M section does not render pass/watch/fail verdict copy.

Verification commands:

```bash
.venv/bin/python -m pytest backend/tests/test_canslim.py backend/tests/test_api.py backend/tests/test_db.py -q
.venv/bin/python -m ruff check backend
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
git diff --check
```

## Implementation Order

1. Add backend FMP settings and provider parsing tests.
2. Add CAN SLIM rule tests and service implementation.
3. Add cache table migration and repository tests.
4. Add `/api/canslim/analysis` API tests and route.
5. Add frontend types and `CanslimPage`.
6. Add navigation and source-inspection frontend tests.
7. Run full verification.

## Risk Notes

- FMP response fields and plan access must be verified with a real key before
  relying on 13F data in production use.
- Holder performance lookup can multiply API calls, so v1 limits it to the top
  10 holders and caches the results.
- The feature must not imply investment advice. UI copy should keep the output
  as evidence and context.
- US-only target validation should be backend-owned so unsupported symbols do
  not leak into provider-specific behavior.

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/Dashboard.tsx", import.meta.url), "utf8")
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const types = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")

assert.match(types, /usd_krw_rate:\s*number\s*\|\s*null/, "PortfolioSummary should expose the USD/KRW display rate")
assert.match(
  types,
  /usd_krw_change_percent:\s*number\s*\|\s*null/,
  "PortfolioSummary should expose the USD/KRW daily change percent",
)
assert.match(types, /export type AssetAllocation/, "PortfolioSummary should type asset allocation rows")
assert.match(
  types,
  /asset_allocations:\s*AssetAllocation\[\]/,
  "PortfolioSummary should expose asset allocation rows",
)
assert.match(
  types,
  /goal_progress:\s*GoalProgress\[\]/,
  "PortfolioSummary should expose goal progress rows for the dashboard",
)

assert.ok(source.includes('type DisplayCurrency = "KRW" | "USD"'), "Dashboard should model display currency explicitly")
assert.ok(
  source.includes('useState<DisplayCurrency>("KRW")'),
  "Dashboard should default the display currency to KRW",
)
assert.ok(source.includes('aria-label="표시 통화 선택"'), "Dashboard should expose an accessible currency toggle")
assert.ok(source.includes('aria-pressed={displayCurrency === currency}'), "Currency buttons should expose pressed state")
assert.ok(source.includes("summary.usd_krw_rate"), "Dashboard should use the summary USD/KRW rate")
assert.ok(
  source.includes("summary.usd_krw_change_percent"),
  "Dashboard should show the USD/KRW daily change percent",
)
assert.ok(source.includes("전일대비"), "Dashboard should label the daily FX movement")
assert.match(source, /import \{ ArrowDown, ArrowUp \} from "lucide-react"/, "Dashboard should use lucide arrows")
assert.ok(source.includes("<ArrowDown"), "Dashboard should show a down arrow for negative FX movement")
assert.ok(source.includes("<ArrowUp"), "Dashboard should show an up arrow for positive FX movement")
assert.ok(source.includes("changePercent < 0"), "Negative FX movement should choose the down state")
assert.ok(source.includes("changePercent > 0"), "Positive FX movement should choose the up state")
assert.ok(source.includes("자동 시세 갱신 후"), "Missing FX message should refer to automatic sync")
assert.ok(!source.includes("시세 동기화 후"), "Missing FX message should not refer to manual sync")
assert.ok(source.includes("getAllocationSegments"), "Dashboard should derive allocation segments from asset mix")
assert.ok(source.includes('aria-label="주식/ETF와 현금 비중"'), "Dashboard allocation metric should be accessible")
assert.ok(source.includes("주식/ETF"), "Dashboard should label the stock/ETF allocation")
assert.ok(source.includes("현금"), "Dashboard should label the cash allocation")
assert.ok(source.includes("기타"), "Dashboard should preserve remaining allocation as other")
assert.ok(source.includes("allocationSegments"), "Dashboard should render allocation segments")
assert.ok(source.includes("summary.asset_allocations"), "Dashboard should use per-asset allocation rows")
assert.ok(source.includes("summary.goal_progress"), "Dashboard should use goal progress from the summary response")
assert.ok(!source.includes('"/api/goals/progress"'), "Dashboard should not fetch goal progress separately")
assert.ok(
  source.includes('allocation.asset_type === "stock_etf"'),
  "Dashboard should split stock/ETF allocations by holding ticker",
)
assert.ok(
  source.includes("allocation.symbol ?? allocation.name"),
  "Dashboard should prefer ticker labels for stock/ETF allocation segments",
)
assert.ok(source.includes("getPieSlicePath"), "Dashboard should render pie slices as SVG paths")
assert.ok(source.includes("getAllocationCallouts"), "Dashboard should calculate outside label callouts")
assert.ok(source.includes("allocation-slice"), "Dashboard should render visible allocation slices")
assert.ok(source.includes("allocation-label-line"), "Dashboard should draw leader lines to allocation labels")
assert.ok(source.includes("allocation-label-name"), "Dashboard should show allocation ticker labels around the pie")
assert.ok(source.includes("<svg"), "Dashboard allocation chart should use SVG for callout labels")

for (const field of [
  "summary.net_worth_krw",
  "summary.monthly_income_krw",
  "summary.gross_assets_krw",
  "summary.debt_krw",
  "row.current_amount_krw",
  "row.remaining_krw",
]) {
  assert.ok(
    source.includes(`formatCurrency(${field}, displayCurrency, summary.usd_krw_rate)`),
    `${field} should be formatted in the selected display currency`,
  )
}

assert.ok(styles.includes(".currency-toggle"), "Dashboard currency toggle should have dedicated layout styles")
assert.ok(styles.includes(".allocation-meter"), "Dashboard allocation metric should have dedicated meter styles")
assert.ok(styles.includes(".allocation-segment"), "Dashboard allocation metric should render fixed segments")
assert.ok(styles.includes(".allocation-pie-svg"), "Dashboard allocation chart should style the SVG pie")
assert.ok(styles.includes(".allocation-label-line"), "Dashboard allocation chart should style leader lines")
assert.ok(styles.includes(".allocation-label-name"), "Dashboard allocation chart should style outside ticker labels")

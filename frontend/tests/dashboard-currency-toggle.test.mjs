import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/Dashboard.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const goalsSource = readFileSync(new URL("../src/components/GoalsPage.tsx", import.meta.url), "utf8")
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const types = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const removedGoalProgressPath = "/api/goals/" + "progress"

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
assert.match(types, /export type TossBuyingPower/, "Frontend should type raw Toss buying power rows")
assert.match(
  types,
  /export type SummaryBuyingPower/,
  "Frontend should type summary buying power rows with KRW conversion",
)
assert.match(
  types,
  /buying_power:\s*SummaryBuyingPower\[\]/,
  "PortfolioSummary should expose converted buying power rows",
)
assert.match(
  types,
  /buying_power_total_krw:\s*number/,
  "PortfolioSummary should expose buying power converted to KRW",
)
assert.match(types, /export type TossAccount/, "Dashboard should type Toss brokerage accounts")
assert.match(types, /account_seq:\s*string/, "Toss accounts should expose account_seq")
assert.match(types, /asset_key:\s*string/, "Asset allocations should use Toss asset keys")
assert.match(types, /market:\s*"KR"\s*\|\s*"US"/, "Asset allocations should expose Toss market")
assert.match(types, /currency:\s*"KRW"\s*\|\s*"USD"/, "Asset allocations should expose Toss currency")
assert.match(types, /symbol:\s*string/, "Asset allocation symbols should be required strings")
assert.match(
  types,
  /goal_progress:\s*GoalProgress\[\]/,
  "PortfolioSummary should expose goal progress rows for the dashboard",
)

assert.ok(source.includes('type DisplayCurrency = "KRW" | "USD"'), "Dashboard should model display currency explicitly")
assert.ok(
  appSource.includes('hidden={active !== "dashboard"}'),
  "App should preserve the mounted dashboard while other pages are active",
)
assert.ok(
  !appSource.includes('{active === "dashboard" && <Dashboard />}'),
  "App should not remount the dashboard when navigating back from another page",
)
assert.ok(
  source.includes('useState<DisplayCurrency>("KRW")'),
  "Dashboard should default the display currency to KRW",
)
assert.ok(source.includes('aria-label="표시 통화 선택"'), "Dashboard should expose an accessible currency toggle")
assert.ok(source.includes('aria-pressed={displayCurrency === currency}'), "Currency buttons should expose pressed state")
assert.ok(source.includes("summary.usd_krw_rate"), "Dashboard should use the summary USD/KRW rate")
const usdCurrencyBranchIndex = source.indexOf('if (currency === "USD")')
const zeroUsdFallbackIndex = source.indexOf("if (valueKrw === 0)", usdCurrencyBranchIndex)
const missingUsdRateFallbackIndex = source.indexOf('return "환율 없음"', usdCurrencyBranchIndex)
assert.ok(
  usdCurrencyBranchIndex >= 0 &&
    zeroUsdFallbackIndex > usdCurrencyBranchIndex &&
    zeroUsdFallbackIndex < missingUsdRateFallbackIndex,
  "Dashboard should show zero KRW amounts as $0 in USD mode even when the FX rate is missing",
)
assert.ok(source.includes("/api/toss/accounts"), "Dashboard should load Toss brokerage accounts first")
assert.ok(
  source.includes("/api/summary?account_seq="),
  "Dashboard should fetch summary for the selected Toss account",
)
assert.ok(!source.includes("/api/toss/buying-power"), "Dashboard should not fetch buying power separately")
assert.ok(source.includes("encodeURIComponent(selectedAccountSeq)"), "Dashboard should encode account_seq")
const selectedSummaryFetchStart = source.indexOf("if (!selectedAccountSeq)")
const selectedSummaryClear = source.indexOf("setSummary(emptySummary)", selectedSummaryFetchStart)
const selectedSummaryFetchRequest = source.indexOf("apiGet<PortfolioSummary>", selectedSummaryFetchStart)
assert.ok(
  selectedSummaryFetchStart >= 0 &&
    selectedSummaryClear > selectedSummaryFetchStart &&
    selectedSummaryClear < selectedSummaryFetchRequest,
  "Dashboard should clear the previous account summary before fetching a newly selected account",
)
assert.ok(source.includes("계좌가 없어 요약을 불러오지 않았습니다."), "Dashboard should show an empty account state")
assert.ok(!source.includes("summary.usd_krw_change_percent"), "Dashboard should not render USD/KRW daily movement")
assert.ok(!source.includes("전일대비"), "Dashboard should hide daily FX movement")
assert.doesNotMatch(source, /import \{ ArrowDown, ArrowUp \} from "lucide-react"/, "Dashboard should not import FX arrows")
assert.ok(!source.includes("<ArrowDown"), "Dashboard should not show a down arrow for FX movement")
assert.ok(!source.includes("<ArrowUp"), "Dashboard should not show an up arrow for FX movement")
assert.ok(!source.includes("formatFxChange"), "Dashboard should not format hidden FX movement")
assert.ok(!source.includes("getFxChangeDirection"), "Dashboard should not calculate hidden FX direction")
assert.ok(source.includes("Toss API 인증 정보를 설정"), "Missing FX message should mention Toss credentials")
assert.ok(!source.includes("시세 동기화 후"), "Missing FX message should not refer to manual sync")
assert.ok(source.includes("getAllocationSegments"), "Dashboard should derive allocation segments from asset mix")
assert.ok(source.includes("buying_power: []"), "Empty summary should initialize buying power rows")
assert.ok(source.includes("buying_power_total_krw: 0"), "Empty summary should initialize buying power")
assert.ok(source.includes("매수 가능 금액"), "Dashboard should render buying power")
assert.ok(
  source.includes("summary.buying_power_total_krw"),
  "Dashboard should read buying power from the summary response",
)
assert.ok(
  source.includes("assetMix.cash"),
  "Dashboard allocation segments should include cash from buying power",
)
assert.ok(
  source.includes("const stockSegments = assetAllocations.map"),
  "Dashboard should derive ticker allocation segments before adding cash",
)
assert.ok(
  source.includes("value: positivePercent(assetMix.cash)"),
  "Dashboard should include cash from asset_mix in allocation segments",
)
assert.ok(
  source.includes("normalizeAllocationSegments([...stockSegments, cashSegment, otherSegment])"),
  "Dashboard should normalize ticker, cash, and other allocation segments together",
)
assert.ok(source.includes('aria-label="주식/ETF와 현금 비중"'), "Dashboard allocation metric should be accessible")
assert.ok(source.includes("주식/ETF"), "Dashboard should label the stock/ETF allocation")
assert.ok(source.includes("allocationSegments"), "Dashboard should render allocation segments")
assert.ok(source.includes("summary.asset_allocations"), "Dashboard should use per-asset allocation rows")
assert.ok(source.includes("summary.goal_progress"), "Dashboard should use goal progress from the summary response")
assert.ok(!source.includes(removedGoalProgressPath), "Dashboard should not fetch goal progress separately")
assert.ok(!goalsSource.includes(removedGoalProgressPath), "Goals page should not fetch local goal progress")
assert.ok(goalsSource.includes('apiGet<Goal[]>("/api/goals")'), "Goals page should list goals directly")
assert.ok(goalsSource.includes("useState<Goal[]>([])"), "Goals page should store goal rows, not progress rows")
assert.ok(!goalsSource.includes("current_amount_krw"), "Goals page should not render current progress amount")
assert.ok(!goalsSource.includes("remaining_krw"), "Goals page should not render remaining progress amount")
assert.ok(
  source.includes("key: allocation.asset_key"),
  "Dashboard should key allocation segments by Toss asset_key",
)
assert.ok(
  source.includes("allocation.symbol || allocation.name"),
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
  "summary.buying_power_total_krw",
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

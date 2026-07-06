import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8")
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const packageSource = readFileSync(new URL("../package.json", import.meta.url), "utf8")
const pageFile = new URL("../src/components/CanslimPage.tsx", import.meta.url)

assert.ok(existsSync(pageFile), "CAN SLIM page should exist")
assert.ok(appSource.includes("CanslimPage"), "App should import the CAN SLIM page")
assert.ok(appSource.includes('active === "canslim"'), "App should mount the CAN SLIM screen")
assert.ok(shellSource.includes('id: "canslim"'), "AppShell should expose CAN SLIM navigation")
assert.ok(shellSource.includes("CAN SLIM"), "AppShell should label the CAN SLIM screen clearly")
assert.ok(shellSource.includes("SearchCheck"), "AppShell should use a lucide icon for CAN SLIM")

for (const expectedType of [
  "CanslimAnalysis",
  "CanslimMarketRange",
  "CanslimLetter",
  "CanslimInstitutionalFlow",
  "CanslimTopPerformingHolder",
  "CanslimMarketContext",
  "generated_at",
  "cached",
  "institutional_flow",
  "top_performing_holders",
  "traded_value_usd",
  'symbol: "SPY"',
]) {
  assert.ok(typesSource.includes(expectedType), `Types should define ${expectedType}`)
}

for (const expectedApi of [
  "fetchCanslimAnalysis",
  "URLSearchParams",
  "/api/canslim/analysis",
  "market_range",
  "refresh",
  "apiGet<CanslimAnalysis>",
]) {
  assert.ok(apiSource.includes(expectedApi), `API helper should include ${expectedApi}`)
}

const pageSource = readFileSync(pageFile, "utf8")

for (const expectedText of [
  "fetchCanslimAnalysis",
  "Search",
  "RefreshCw",
  "marketRangeOptions",
  'value: "3m"',
  'value: "6m"',
  'value: "1y"',
  "FMP API 키",
  "CAN SLIM v1은 미국 상장 보통주만 지원합니다.",
  "C/A/N/S/L/I/M",
  "회사 설명",
  "무엇을 하는 회사인지",
  "status",
  "headline",
  "details",
  "metrics",
  "source",
  "as_of",
  "institutional_flow",
  "top_performing_holders",
  "holder_name",
  "shares",
  "market_value",
  "portfolio_weight_percent",
  "performance_1y_percent",
  "performance_3y_percent",
  "performance_5y_percent",
  "excess_vs_sp500_percent",
  "SPY",
  "candles",
  "volume",
  "traded_value_usd",
  "시장 컨텍스트",
  "거래대금",
]) {
  assert.ok(pageSource.includes(expectedText), `CAN SLIM page should include ${expectedText}`)
}

for (const letter of ["c", "a", "n", "s", "l", "i", "m"]) {
  assert.ok(pageSource.includes(`letters.${letter}`), `Page should render ${letter.toUpperCase()}`)
}

assert.ok(pageSource.includes("loading"), "Page should render a loading state")
assert.ok(pageSource.includes("error"), "Page should render an error state")
assert.ok(pageSource.includes("empty-state"), "Page should render an empty/help state")
assert.ok(pageSource.includes("useRef"), "Page should use a request sequence ref for async lookup guards")
assert.ok(
  pageSource.includes("requestSeqRef"),
  "Page should keep only the latest CAN SLIM lookup result",
)
assert.match(
  pageSource,
  /const requestId = requestSeqRef\.current \+ 1[\s\S]*requestSeqRef\.current = requestId/,
  "Page should assign a monotonic request id before each lookup",
)
assert.match(
  pageSource,
  /if \(requestId !== requestSeqRef\.current\) {\s*return\s*}/,
  "Page should ignore stale lookup results and errors",
)
const awaitedFetchIndex = pageSource.indexOf("const result = await fetchCanslimAnalysis")
const catchIndex = pageSource.indexOf("} catch", awaitedFetchIndex)
const awaitedFetchBlock = pageSource.slice(awaitedFetchIndex, catchIndex)
assert.ok(
  !awaitedFetchBlock.includes("setSymbol("),
  "Page should not reset ticker input after an awaited lookup resolves",
)
assert.ok(
  pageSource.includes("formatMetricValue(metric, metricValue)"),
  "Metric formatter should receive metric names",
)
assert.match(
  pageSource,
  /metric\.endsWith\("_percent"\)[\s\S]*formatPercent\(value\)/,
  "Metric formatter should render *_percent fields with percent notation",
)
assert.ok(
  pageSource.includes("const displayedCandles = [...market.candles]"),
  "M table should use an explicitly sorted displayed candle list",
)
assert.match(
  pageSource,
  /displayedCandles[\s\S]*sort\(\(left, right\) => right\.date\.localeCompare\(left\.date\)\)[\s\S]*slice\(0, 8\)/,
  "M table should display the latest SPY candles first",
)
assert.ok(
  !pageSource.includes("recommendation") &&
    !pageSource.includes("verdict") &&
    !pageSource.includes("매수 추천") &&
    !pageSource.includes("매도 추천"),
  "CAN SLIM page should not render buy/sell recommendation or market verdict copy",
)

for (const expectedStyle of [
  ".canslim-screen",
  ".canslim-search-panel",
  ".canslim-range-toggle",
  ".canslim-grid",
  ".canslim-status-pass",
  ".canslim-status-watch",
  ".canslim-status-fail",
  ".canslim-status-unknown",
  ".canslim-status-info",
  ".canslim-holder-table",
  ".canslim-market-chart",
  "@media (max-width: 720px)",
]) {
  assert.ok(stylesSource.includes(expectedStyle), `Styles should include ${expectedStyle}`)
}

assert.ok(
  packageSource.includes("node tests/canslim-page.test.mjs"),
  "npm test should include the CAN SLIM source-inspection test",
)

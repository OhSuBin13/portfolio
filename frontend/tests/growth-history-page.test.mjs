import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const pageFile = new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url)
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")

assert.ok(appSource.includes('active === "growth"'), "App should mount growth history")
assert.ok(shellSource.includes('id: "growth"'), "AppShell should use the growth nav id")
assert.ok(shellSource.includes("성장기록"), "AppShell should expose growth navigation")
assert.ok(existsSync(pageFile), "Growth history page should exist")

const pageSource = readFileSync(pageFile, "utf8")

assert.ok(pageSource.includes("/api/growth/month-history"), "Page should load month history")
assert.ok(pageSource.includes("/api/growth/annual-history"), "Page should load annual history")
assert.ok(pageSource.includes("monthly_dividend_krw"), "Page should submit monthly dividend history")
assert.ok(pageSource.includes("apiDelete"), "Page should delete month history rows")
assert.ok(!/>\s*수정\s*</.test(pageSource), "Page should not render month history edit controls")
assert.ok(
  /<button[\s\S]*?>\s*관리\s*<\/button>/.test(pageSource),
  "Page should expose a month history management control",
)
assert.ok(
  pageSource.includes("isMonthDeleteMode") &&
    pageSource.includes("setIsMonthDeleteMode"),
  "Page should track a single month history delete mode",
)
assert.ok(
  !pageSource.includes("activeMonthManagementKey") &&
    !pageSource.includes("isManagingMonthRow"),
  "Page should not track management mode per month row",
)
assert.ok(
  pageSource.includes("{isMonthDeleteMode && <th className=\"numeric-cell\">삭제</th>}"),
  "Page should hide the delete column before management mode is active",
)
assert.ok(
  pageSource.includes("{isMonthDeleteMode && (") &&
    pageSource.includes("handleDeleteMonth(row)"),
  "Page should render delete buttons only while management mode is active",
)
assert.ok(pageSource.includes("삭제"), "Page should expose month history delete controls")
assert.ok(!pageSource.includes("handleEditMonth"), "Page should not keep month history edit handlers")
assert.ok(pageSource.includes("formatReturnPercent"), "Page should format returns as percentages")
assert.ok(
  pageSource.includes("(value - 1) * 100"),
  "Page should convert stored return ratios into percent changes",
)
assert.ok(!pageSource.includes("toFixed(4)}x"), "Page should not show returns as ratio multiples")
assert.ok(
  pageSource.includes("latestMonthHistoryKey") &&
    pageSource.includes("formatLatestMonthAverageReturn(row)"),
  "Page should show average return only on the latest month row",
)
assert.ok(
  pageSource.includes("latestAnnualHistoryKey") &&
    pageSource.includes("formatLatestAnnualAverageReturn(row)"),
  "Page should show annual average return only on the latest annual row",
)
assert.ok(
  pageSource.includes("getReturnToneClass") &&
    pageSource.includes("value > 1") &&
    pageSource.includes("value < 1"),
  "Page should classify positive and negative returns from stored ratios",
)
assert.ok(
  pageSource.includes("return-tone-positive") && pageSource.includes("return-tone-negative"),
  "Page should apply return tone classes to return cells",
)
assert.ok(
  stylesSource.includes(".return-tone-positive") && stylesSource.includes(".return-tone-negative"),
  "Styles should define positive and negative return colors",
)
assert.ok(
  pageSource.includes("S&P 500 연 성장률"),
  "Page should show the S&P 500 annual growth column",
)
assert.ok(
  pageSource.includes("/api/growth/sp500-proxy-prices"),
  "Page should save S&P 500 proxy prices",
)
assert.ok(
  pageSource.includes("sp500_annual_return_ratio") &&
    pageSource.includes("formatReturnPercent(row.sp500_annual_return_ratio)"),
  "Page should render S&P 500 annual proxy returns as percentages",
)
assert.ok(
  pageSource.includes("getReturnToneClass(row.sp500_annual_return_ratio)"),
  "Page should apply return colors to S&P 500 annual proxy returns",
)
assert.ok(pageSource.includes("순자산을 입력하세요."), "Page should reject blank net worth")
assert.ok(
  pageSource.includes("selectedAccountSeqRef") &&
    pageSource.includes("requestAccountSeq !== selectedAccountSeqRef.current"),
  "Page should ignore stale selected-account async results",
)
assert.ok(
  pageSource.includes("const defaultGrowthForm = ()") &&
    pageSource.includes("useState<GrowthForm>(defaultGrowthForm)"),
  "Page should calculate the default growth form date when the component mounts",
)
assert.ok(
  pageSource.includes("const defaultSp500ProxyForm = ()") &&
    pageSource.includes("useState<Sp500ProxyForm>(defaultSp500ProxyForm)"),
  "Page should calculate the default S&P 500 proxy year when the component mounts",
)
assert.ok(
  !pageSource.includes("const initialForm") &&
    !pageSource.includes("const initialSp500ProxyForm"),
  "Page should not freeze default form values at module load time",
)

const emptyAccountGuardStart = pageSource.indexOf("if (!selectedAccountSeq)")
const emptyAccountLoadingReset = pageSource.indexOf("setHistoryLoading(false)", emptyAccountGuardStart)
const historyRequestSetup = pageSource.indexOf("let ignore = false", emptyAccountGuardStart)
assert.ok(
  emptyAccountGuardStart >= 0 &&
    emptyAccountLoadingReset > emptyAccountGuardStart &&
    emptyAccountLoadingReset < historyRequestSetup,
  "Page should clear history loading when account selection becomes empty",
)

const historyFetchStart = pageSource.indexOf("setHistoryLoading(true)")
const monthClearBeforeFetch = pageSource.indexOf("setMonthHistory([])", historyFetchStart)
const annualClearBeforeFetch = pageSource.indexOf("setAnnualHistory([])", historyFetchStart)
const historyFetchRequest = pageSource.indexOf("return loadHistory(requestAccountSeq)", historyFetchStart)

assert.ok(
  historyFetchStart >= 0 &&
    monthClearBeforeFetch > historyFetchStart &&
    annualClearBeforeFetch > historyFetchStart &&
    monthClearBeforeFetch < historyFetchRequest &&
    annualClearBeforeFetch < historyFetchRequest,
  "Page should clear stale growth rows before fetching a selected account",
)

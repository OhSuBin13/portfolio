import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const pageFile = new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url)

assert.ok(appSource.includes('active === "growth"'), "App should mount growth history")
assert.ok(shellSource.includes('id: "growth"'), "AppShell should use the growth nav id")
assert.ok(shellSource.includes("성장기록"), "AppShell should expose growth navigation")
assert.ok(existsSync(pageFile), "Growth history page should exist")

const pageSource = readFileSync(pageFile, "utf8")

assert.ok(pageSource.includes("/api/growth/month-history"), "Page should load month history")
assert.ok(pageSource.includes("/api/growth/annual-history"), "Page should load annual history")
assert.ok(pageSource.includes("monthly_dividend_krw"), "Page should submit monthly dividend history")
assert.ok(pageSource.includes("순자산을 입력하세요."), "Page should reject blank net worth")
assert.ok(
  pageSource.includes("selectedAccountSeqRef") &&
    pageSource.includes("requestAccountSeq !== selectedAccountSeqRef.current"),
  "Page should ignore stale selected-account async results",
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

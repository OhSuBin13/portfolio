import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const pagePath = new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url)
assert.ok(existsSync(pagePath), "GrowthHistoryPage.tsx should exist")
const pageSource = readFileSync(pagePath, "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const packageSource = readFileSync(new URL("../package.json", import.meta.url), "utf8")

assert.ok(typesSource.includes("export type PortfolioSnapshot"), "types should export PortfolioSnapshot")
assert.ok(typesSource.includes("export type GrowthHistoryRow"), "types should export GrowthHistoryRow")

assert.ok(
  pageSource.includes('"/api/growth/history?period=monthly"'),
  "Growth history page should load monthly history",
)
assert.ok(
  pageSource.includes('"/api/growth/history?period=annual"'),
  "Growth history page should load annual history",
)
assert.ok(
  pageSource.includes('"/api/growth/snapshots/today"'),
  "Growth history page should refresh today's snapshot",
)
assert.ok(
  pageSource.includes("apiPost<PortfolioSnapshot>"),
  "Growth history page should type manual snapshot refresh response",
)
assert.ok(pageSource.includes("formatPercent"), "Growth history page should format percentage rates")
assert.ok(pageSource.includes('rate === null ? "-"'), "Missing growth rates should render as a dash")

for (const label of ["배당/이자", "순입금", "월별 성장률", "연간 성장률"]) {
  assert.ok(pageSource.includes(label), `Growth history page should include ${label}`)
}

assert.ok(shellSource.includes("성장기록"), "AppShell should include the growth navigation label")
assert.ok(appSource.includes("<GrowthHistoryPage />"), "App should render the growth history page")

for (const className of [".growth-status", ".signed-positive", ".signed-negative"]) {
  assert.ok(stylesSource.includes(className), `styles should include ${className}`)
}

assert.ok(
  packageSource.includes("growth-history-page.test.mjs"),
  "package test script should include the growth history static test",
)

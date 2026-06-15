import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/Dashboard.tsx", import.meta.url), "utf8")
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const types = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")

assert.match(types, /usd_krw_rate:\s*number\s*\|\s*null/, "PortfolioSummary should expose the USD/KRW display rate")

assert.ok(source.includes('type DisplayCurrency = "KRW" | "USD"'), "Dashboard should model display currency explicitly")
assert.ok(
  source.includes('useState<DisplayCurrency>("KRW")'),
  "Dashboard should default the display currency to KRW",
)
assert.ok(source.includes('aria-label="표시 통화 선택"'), "Dashboard should expose an accessible currency toggle")
assert.ok(source.includes('aria-pressed={displayCurrency === currency}'), "Currency buttons should expose pressed state")
assert.ok(source.includes("summary.usd_krw_rate"), "Dashboard should use the summary USD/KRW rate")

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

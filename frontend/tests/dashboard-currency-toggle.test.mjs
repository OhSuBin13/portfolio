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

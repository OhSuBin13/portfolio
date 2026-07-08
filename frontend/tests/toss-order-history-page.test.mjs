import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/OrderHistoryPage.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

assert.ok(appSource.includes("OrderHistoryPage"), "App should mount the Toss order history page")
assert.ok(shellSource.includes("주문내역"), "Navigation should expose Toss order history")

for (const expectedText of [
  "/api/toss/accounts",
  "/api/toss/order-imports",
  "/api/toss/orders",
  "account_seq",
  "CLOSED",
  "Search",
  "periodFilter",
  "debouncedSymbolFilter",
  "ORDER_SYMBOL_FILTER_DEBOUNCE_MS",
  "order-period-toggle",
  "일",
  "월",
  "년",
]) {
  assert.ok(source.includes(expectedText), `Order history page should include ${expectedText}`)
}

assert.ok(!source.includes("/api/transactions"), "Order history page should not use local transactions")
for (const removedControl of [
  'type="date"',
  "시작일",
  "종료일",
  "value={statusFilter}",
  "<option value=\"OPEN\">",
  "<option value=\"CLOSED\">",
  "setStatusFilter",
  "handleImport",
  "onSubmit=",
  'type="submit"',
]) {
  assert.ok(
    !source.includes(removedControl),
    `Order history page should remove ${removedControl}`,
  )
}
assert.ok(
  !source.includes('params.set("order_status", statusFilter)'),
  "Saved Toss orders should not be filtered by the import OPEN/CLOSED status",
)
assert.ok(
  source.includes('status: "CLOSED"'),
  "Order history imports should always request CLOSED orders",
)
assert.ok(
  source.includes("setSymbolSearchOpen"),
  "Order history page should reveal symbol input from an interactive search button",
)
assert.match(
  source,
  /window\.setTimeout\([\s\S]*?setDebouncedSymbolFilter\(symbolFilter\)[\s\S]*?ORDER_SYMBOL_FILTER_DEBOUNCE_MS/,
  "Order history page should debounce symbol search text before API requests",
)
assert.ok(
  source.includes("window.clearTimeout(timeoutId)"),
  "Order history page should cancel pending symbol search debounce timers",
)
assert.match(
  source,
  /const currentOrderQueryKey = orderQueryKeyFrom\(\{[\s\S]*?symbolFilter: debouncedSymbolFilter/,
  "Order history visible query key should use the debounced symbol filter",
)
assert.match(
  source,
  /const requestSnapshot: OrderQuerySnapshot = \{[\s\S]*?symbolFilter: debouncedSymbolFilter/,
  "Saved order reads should use the debounced symbol filter",
)
assert.match(
  source,
  /const submittedSnapshot: OrderQuerySnapshot = \{[\s\S]*?symbolFilter: debouncedSymbolFilter/,
  "Order imports should use the debounced symbol filter",
)
assert.ok(source.includes("useRef"), "Order history page should use a stale-response guard ref")
assert.ok(
  source.includes("latestOrderQueryKeyRef"),
  "Order history page should track the latest visible order query key",
)
assert.ok(
  source.includes("isCurrentImportSnapshot"),
  "Manual import refresh should check that the submitted snapshot is still current",
)
assert.ok(
  source.includes("loadedOrderQueryKey"),
  "Order history page should track which query loaded the visible orders",
)
assert.ok(
  source.includes("loadedOrderQueryKey === currentOrderQueryKey"),
  "Order history table should only render rows for the current visible query",
)
assert.ok(
  source.includes("refreshImportRunsForSnapshot(submittedSnapshot, importRequestId)"),
  "Failed imports should refresh import-run history for the submitted account",
)

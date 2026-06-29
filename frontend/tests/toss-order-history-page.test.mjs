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
  "OPEN",
  "CLOSED",
]) {
  assert.ok(source.includes(expectedText), `Order history page should include ${expectedText}`)
}

assert.ok(!source.includes("/api/transactions"), "Order history page should not use local transactions")
assert.ok(
  !source.includes('params.set("order_status", statusFilter)'),
  "Saved Toss orders should not be filtered by the import OPEN/CLOSED status",
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

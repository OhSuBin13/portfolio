import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/OrderHistoryTable.tsx", import.meta.url),
  "utf8",
)
const pageSource = readFileSync(new URL("../src/components/OrderHistoryPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export function OrderHistoryTable"), "Order history table should be a named export")
assert.ok(source.includes("orders.map((order) =>"), "Order history table should render order rows")
assert.ok(source.includes("formatDateTime(order.ordered_at)"), "Order history table should format order timestamps")
assert.ok(source.includes("displayValue(order.price)"), "Order history table should display nullable prices")
assert.ok(source.includes("<th>주문 시각</th>"), "Order history table should own table headers")
assert.ok(source.includes('className="data-table"'), "Order history table should own table styling")
assert.ok(
  pageSource.includes('from "./OrderHistoryTable"'),
  "OrderHistoryPage should import the extracted order history table",
)
assert.ok(
  !pageSource.includes('className="data-table"'),
  "OrderHistoryPage should not keep order table markup inline",
)

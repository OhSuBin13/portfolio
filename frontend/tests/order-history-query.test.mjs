import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/orderHistoryQuery.ts", import.meta.url), "utf8")
const pageSource = readFileSync(new URL("../src/components/OrderHistoryPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export const periodOptions"), "Order period options should move with query helpers")
assert.ok(source.includes("export const ORDER_SYMBOL_FILTER_DEBOUNCE_MS"), "Symbol debounce should move with query helpers")
assert.ok(source.includes("export type PeriodFilter"), "Period filter type should move with query helpers")
assert.ok(source.includes("export type OrderQuerySnapshot"), "Order query snapshot type should move with query helpers")
assert.ok(source.includes("export const getPeriodRange"), "Period range helper should be exported")
assert.ok(source.includes("export const buildOrderQuery"), "Order query builder should be exported")
assert.ok(source.includes("export const orderQueryKeyFrom"), "Order query key helper should be exported")
assert.ok(source.includes("export const buildOrderQueryFromSnapshot"), "Snapshot query builder should be exported")
assert.ok(source.includes("export const buildImportRunsQuery"), "Import-run query builder should be exported")
assert.ok(
  pageSource.includes("../orderHistoryQuery"),
  "OrderHistoryPage should import extracted order query helpers",
)
assert.ok(
  !pageSource.includes("const buildOrderQuery ="),
  "OrderHistoryPage should not keep order query construction inline",
)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import ts from "typescript"

const source = readFileSync(new URL("../src/chartMarkers.ts", import.meta.url), "utf8")
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
})

const module = { exports: {} }
vm.runInNewContext(outputText, {
  exports: module.exports,
  module,
  require: (name) => {
    throw new Error(`Unexpected require from chartMarkers test: ${name}`)
  },
})

const { buildTradeMarkers } = module.exports

const markerLabels = (orders) =>
  Array.from(buildTradeMarkers(orders, []), (marker) => marker.label)

const order = ({ order_id, side, filled_quantity, ordered_at }) => ({
  id: Number(order_id),
  account_seq: "account-1",
  order_id,
  symbol: "ABC",
  side,
  order_type: "LIMIT",
  time_in_force: "DAY",
  order_status: "FILLED",
  price: "100",
  quantity: filled_quantity,
  order_amount: null,
  currency: "KRW",
  ordered_at,
  canceled_at: null,
  filled_quantity,
  average_filled_price: "100",
  filled_amount: null,
  commission: null,
  tax: null,
  filled_at: ordered_at,
  settlement_date: null,
  imported_at: ordered_at,
})

assert.deepEqual(
  markerLabels([
    order({ order_id: "1", side: "BUY", filled_quantity: "10", ordered_at: "2026-01-01T09:00:00Z" }),
    order({ order_id: "2", side: "SELL", filled_quantity: "10", ordered_at: "2026-01-02T09:00:00Z" }),
    order({ order_id: "3", side: "BUY", filled_quantity: "2", ordered_at: "2026-01-03T09:00:00Z" }),
  ]),
  ["매수", "Trim", "매수"],
)

assert.deepEqual(
  markerLabels([
    order({ order_id: "4", side: "BUY", filled_quantity: "10", ordered_at: "2026-01-01T09:00:00Z" }),
    order({ order_id: "5", side: "SELL", filled_quantity: "3", ordered_at: "2026-01-02T09:00:00Z" }),
    order({ order_id: "6", side: "BUY", filled_quantity: "2", ordered_at: "2026-01-03T09:00:00Z" }),
  ]),
  ["매수", "Trim", "추가매수"],
)

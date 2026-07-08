import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import ts from "typescript"

const source = readFileSync(new URL("../src/chartMarkers.ts", import.meta.url), "utf8")
const chartDatesSource = readFileSync(new URL("../src/chartDates.ts", import.meta.url), "utf8")
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
})
const { outputText: chartDatesOutputText } = ts.transpileModule(chartDatesSource, {
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
const chartDatesModule = { exports: {} }
vm.runInNewContext(chartDatesOutputText, {
  exports: chartDatesModule.exports,
  module: chartDatesModule,
  require: (name) => {
    throw new Error(`Unexpected require from chartDates test: ${name}`)
  },
})

const { buildTradeMarkers, spreadOverlappingMarkers } = module.exports
const { chartDateKey, chartPeriodGroupKey, formatChartDateLabel } = chartDatesModule.exports

const markerLabels = (orders) =>
  Array.from(buildTradeMarkers(orders, []), (marker) => marker.label)

const markerOrderKeys = (orders) =>
  Array.from(buildTradeMarkers(orders, []), (marker) => marker.key)

const marker = (key) => ({
  key,
  label: "매수",
  tone: "buy",
  timestamp: "2026-04-30T09:00:00Z",
  price: 100,
  quantity: "1",
  memo: "",
})

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

assert.deepEqual(
  markerOrderKeys([
    order({ order_id: "7", side: "BUY", filled_quantity: "1", ordered_at: "2026-01-04T09:00:00Z" }),
    order({ order_id: "8", side: "SELL", filled_quantity: "1", ordered_at: "2026-01-04T10:00:00Z" }),
    order({ order_id: "9", side: "BUY", filled_quantity: "2", ordered_at: "2026-01-05T09:00:00Z" }),
  ]),
  ["order:9"],
)

assert.deepEqual(
  markerOrderKeys([
    order({ order_id: "10", side: "BUY", filled_quantity: "3", ordered_at: "2026-01-23T09:00:00Z" }),
    order({ order_id: "11", side: "SELL", filled_quantity: "3", ordered_at: "2026-01-24T09:00:00Z" }),
    order({ order_id: "12", side: "BUY", filled_quantity: "3", ordered_at: "2026-01-24T10:00:00Z" }),
    order({ order_id: "13", side: "SELL", filled_quantity: "3", ordered_at: "2026-01-24T11:00:00Z" }),
    order({ order_id: "14", side: "BUY", filled_quantity: "3", ordered_at: "2026-01-24T12:00:00Z" }),
    order({ order_id: "15", side: "SELL", filled_quantity: "3", ordered_at: "2026-01-24T13:00:00Z" }),
  ]),
  ["order:10", "order:11"],
)

assert.deepEqual(
  markerOrderKeys([
    order({ order_id: "16", side: "BUY", filled_quantity: "0", ordered_at: "2026-01-25T09:00:00Z" }),
    order({ order_id: "17", side: "SELL", filled_quantity: "0", ordered_at: "2026-01-25T10:00:00Z" }),
    order({ order_id: "18", side: "BUY", filled_quantity: "2", ordered_at: "2026-01-26T09:00:00Z" }),
  ]),
  ["order:18"],
)

assert.deepEqual(
  spreadOverlappingMarkers([
    { marker: marker("first"), candleIndex: 3 },
    { marker: marker("second"), candleIndex: 3 },
    { marker: marker("third"), candleIndex: 5 },
  ]).map(({ marker, candleIndex, xOffset }) => ({
    key: marker.key,
    candleIndex,
    xOffset,
  })),
  [
    { key: "first", candleIndex: 3, xOffset: -8 },
    { key: "second", candleIndex: 3, xOffset: 8 },
    { key: "third", candleIndex: 5, xOffset: 0 },
  ],
)

assert.equal(
  chartDateKey("2026-03-25T00:30:00+09:00"),
  "2026-03-25",
  "Chart date keys should preserve the source calendar date instead of the runtime timezone",
)
assert.equal(
  formatChartDateLabel("2026-03-25T00:30:00+09:00", "daily"),
  "26-03-25",
)
assert.equal(
  formatChartDateLabel("2026-03-25T00:30:00+09:00", "monthly"),
  "26-03",
)
assert.equal(
  chartPeriodGroupKey("2026-03-01T00:30:00+09:00", "weekly"),
  "2026-02-23",
  "Weekly candle grouping should use the source calendar date for week boundaries",
)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import ts from "typescript"

const chartSeriesSource = readFileSync(new URL("../src/chartSeries.ts", import.meta.url), "utf8")
const chartDatesSource = readFileSync(new URL("../src/chartDates.ts", import.meta.url), "utf8")

const transpile = (source) =>
  ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText

const chartDatesModule = { exports: {} }
vm.runInNewContext(transpile(chartDatesSource), {
  exports: chartDatesModule.exports,
  module: chartDatesModule,
})

const chartSeriesModule = { exports: {} }
vm.runInNewContext(transpile(chartSeriesSource), {
  exports: chartSeriesModule.exports,
  module: chartSeriesModule,
  require: (name) => {
    if (name === "./chartDates") {
      return chartDatesModule.exports
    }
    throw new Error(`Unexpected require from chartSeries test: ${name}`)
  },
})

const {
  aggregateCandles,
  changeRateForPrice,
  changeRateTone,
  formatChangeRate,
  markerIndex,
  movingAveragePoints,
  priceBounds,
} = chartSeriesModule.exports

const candle = (timestamp, open, high, low, close, volume = 10) => ({
  symbol: "ABC",
  timestamp,
  open,
  high,
  low,
  close,
  volume,
})
const plain = (value) => JSON.parse(JSON.stringify(value))

assert.deepEqual(
  plain(
    aggregateCandles(
      [
        candle("2026-01-02T00:00:00+09:00", 11, 14, 10, 13, 2),
        candle("2026-01-01T00:00:00+09:00", 10, 12, 8, 11, 3),
        candle("2026-01-31T00:00:00+09:00", 13, 15, 9, 14, 5),
      ],
      "monthly",
    ),
  ),
  [candle("2026-01-01T00:00:00+09:00", 10, 15, 8, 14, 10)],
)

assert.deepEqual(
  plain(
    movingAveragePoints(
      [
        candle("2026-01-01", 1, 1, 1, 10),
        candle("2026-01-02", 1, 1, 1, 20),
        candle("2026-01-03", 1, 1, 1, 30),
      ],
      2,
    ),
  ),
  [
    { index: 1, value: 15 },
    { index: 2, value: 25 },
  ],
)

assert.deepEqual(
  plain(
    priceBounds(
      [candle("2026-01-01", 100, 120, 90, 110)],
      [[{ index: 0, value: 130 }]],
      [{ key: "marker", label: "매수", tone: "buy", timestamp: "2026-01-01", price: 80, quantity: "1", memo: "" }],
    ),
  ),
  { max: 134, min: 76 },
)

assert.equal(markerIndex([candle("2026-01-01", 1, 1, 1, 1)], {
  key: "marker",
  label: "매수",
  tone: "buy",
  timestamp: "2026-01-01T09:00:00+09:00",
  price: 1,
  quantity: "1",
  memo: "",
}), 0)
assert.equal(markerIndex([candle("2026-01-10", 1, 1, 1, 1)], {
  key: "marker",
  label: "매수",
  tone: "buy",
  timestamp: "2026-01-01",
  price: 1,
  quantity: "1",
  memo: "",
}), -1)

assert.equal(changeRateForPrice(110, 100), 10)
assert.equal(changeRateForPrice(110, 0), null)
assert.equal(formatChangeRate(3.125), "+3.13%")
assert.equal(formatChangeRate(-1.5), "-1.5%")
assert.equal(formatChangeRate(null), "-")
assert.equal(changeRateTone(0), "flat")
assert.equal(changeRateTone(1), "up")
assert.equal(changeRateTone(-1), "down")

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import ts from "typescript"

const source = readFileSync(new URL("../src/chartViewport.ts", import.meta.url), "utf8")
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
})

const {
  buildVisibleChartWindow,
  chartPanSteps,
  nextChartPanOffset,
  nextChartZoom,
  visibleChartWindowSize,
} = module.exports

const plain = (value) => JSON.parse(JSON.stringify(value))

assert.deepEqual(
  plain(buildVisibleChartWindow(["a", "b", "c", "d", "e"], null, 0)),
  { candles: ["a", "b", "c", "d", "e"], startIndex: 0 },
)

assert.deepEqual(
  plain(buildVisibleChartWindow(["a", "b", "c", "d", "e"], 3, 1)),
  { candles: ["b", "c", "d"], startIndex: 1 },
)

assert.deepEqual(
  plain(buildVisibleChartWindow(["a", "b", "c", "d", "e"], 2, 0)),
  { candles: ["d", "e"], startIndex: 3 },
)

assert.deepEqual(
  plain(buildVisibleChartWindow(["a", "b", "c", "d", "e"], 2, 99)),
  { candles: ["a", "b"], startIndex: 0 },
  "Visible window should clamp pan offsets that exceed available candles",
)

assert.deepEqual(
  plain(nextChartZoom(100, null, 8, false)),
  { zoomWindow: 80, panOffset: 8 },
  "Wheel-up zoom should reduce the visible window while preserving valid pan",
)

assert.deepEqual(
  plain(nextChartZoom(100, 90, 8, true)),
  { zoomWindow: null, panOffset: 0 },
  "Zooming out to the full range should reset the zoom state and pan offset",
)

assert.deepEqual(
  plain(nextChartZoom(40, 20, 30, false)),
  { zoomWindow: 20, panOffset: 20 },
  "Zooming in should not go below the minimum visible candle count and should clamp pan",
)

assert.equal(visibleChartWindowSize(50, null), 50)
assert.equal(visibleChartWindowSize(50, 20), 20)
assert.equal(visibleChartWindowSize(10, 20), 10)

assert.equal(chartPanSteps(35), 0)
assert.equal(chartPanSteps(72), 2)
assert.equal(chartPanSteps(-72), -2)

assert.equal(nextChartPanOffset(5, 2, 30, 10), 7)
assert.equal(nextChartPanOffset(5, -20, 30, 10), 0)
assert.equal(nextChartPanOffset(18, 5, 30, 10), 20)

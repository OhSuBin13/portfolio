import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/ChartsPage.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")

assert.ok(shellSource.includes('id: "charts"'), "Navigation should expose the charts screen")
assert.ok(shellSource.includes("차트"), "Navigation should label the charts screen in Korean")
assert.ok(appSource.includes("ChartsPage"), "App should mount the charts page")
assert.ok(appSource.includes('active === "charts"'), "App should route the charts screen")

for (const expectedText of [
  "/api/toss/accounts",
  "/api/toss/holdings",
  "/api/toss/candles",
  "/api/toss/orders",
  "/api/toss/chart-marker-memos",
  "limit=1000",
  "interval=1d",
  "selectedChartPeriod",
  "chartPeriodOptions",
  "일봉",
  "주봉",
  "연봉",
  "movingAverageConfigs",
  "movingAverageForm",
  "type=\"color\"",
  "lineWidth",
  "showVolume",
  "chartZoomWindow",
  "chartPanOffset",
  "visibleChartCandles",
  "handleChartWheel",
  "handleChartMouseDown",
  "handleChartMouseMove",
  "handleChartMouseUp",
  "onWheel={handleChartWheel}",
  "onMouseDown={handleChartMouseDown}",
  "onMouseMove={handleChartMouseMove}",
  "onMouseUp={handleChartMouseUp}",
  "onMouseLeave={handleChartMouseUp}",
  "event.preventDefault()",
  "event.deltaY > 0",
  "event.clientX",
  "거래량",
  "chart-markers",
  "markerMemoDraft",
  "매수",
  "추가매수",
  "Trim",
]) {
  assert.ok(source.includes(expectedText), `Charts page should include ${expectedText}`)
}

assert.ok(source.includes("TossCandle"), "Charts page should type candle data")
assert.ok(source.includes("TossOrder"), "Charts page should use Toss orders for trade markers")
assert.ok(source.includes("ChartMarkerMemo"), "Charts page should type marker memos")
assert.ok(source.includes("selectedHoldingKey"), "Charts page should select a held symbol")
assert.ok(source.includes("<svg"), "Charts page should render an SVG candlestick chart")
assert.ok(source.includes("candle-chart-svg"), "Charts page should use stable chart SVG styling")
assert.ok(source.includes("보유 종목 차트"), "Charts page should present one holdings chart panel")

assert.ok(typesSource.includes("export type TossCandle"), "Frontend types should include Toss candles")
assert.ok(
  typesSource.includes("export type ChartMarkerMemo"),
  "Frontend types should include chart marker memos",
)
assert.ok(styles.includes(".candle-chart-svg"), "Styles should size the candlestick SVG")
assert.ok(styles.includes(".candle-up"), "Styles should define rising candle color")
assert.ok(styles.includes(".candle-down"), "Styles should define falling candle color")
assert.ok(styles.includes(".moving-average-line"), "Styles should define moving-average lines")
assert.ok(styles.includes(".chart-markers"), "Styles should define trade marker layout")

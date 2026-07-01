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
  "월봉",
  "연봉",
  "monthly",
  "monthGroupKey",
  "formatChartDateLabel",
  "movingAverageConfigs",
  "movingAverageForm",
  "type=\"color\"",
  "lineWidth",
  "showVolume",
  "chartZoomWindow",
  "chartPanOffset",
  "visibleChartWindow",
  "visibleChartCandles",
  "visibleCandleStartIndex",
  "movingAverageSourceCandles",
  "handleChartWheel",
  "handleChartMouseDown",
  "handleChartMouseMove",
  "handleChartMouseUp",
  "chartHoverState",
  "hoverCandleIndex",
  "previousClose",
  "changeRates",
  "changeRateForPrice",
  "formatChangeRate",
  "changeRateTone",
  "handleChartHoverMove",
  "handleChartHoverLeave",
  "chart-hover-price-line",
  "chart-hover-price-label",
  "chart-hover-vertical-line",
  "chart-hover-date-label",
  "chart-hover-ohlc-panel",
  "chart-hover-change-rate",
  "chart-hover-ohlc-values",
  "currency === \"USD\"",
  "`$${formatted}`",
  "onWheel={handleChartWheel}",
  "onMouseDown={handleChartMouseDown}",
  "onMouseMove={handleChartMouseMove}",
  "onMouseUp={handleChartMouseUp}",
  "onMouseLeave={handleChartMouseUp}",
  "event.preventDefault()",
  "event.deltaY > 0",
  "event.clientX",
  "point.index - visibleCandleStartIndex",
  "거래량",
  "chart-markers",
  "markerMemoDraft",
  "marker-selected-header",
  "marker-detail-grid",
  "marker-note-field",
  "marker-note-actions",
  "판단 기록",
  "체결가",
  "판단 메모",
  "placeholder",
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
assert.match(
  source,
  /className="chart-hover-price-bg"[\s\S]*?width=\{104\}[\s\S]*?x=\{4\}/,
  "Hover price label background should keep tighter horizontal padding near the SVG left edge",
)
assert.match(
  source,
  /className="chart-hover-price-label"[\s\S]*?x=\{56\}/,
  "Hover price label text should stay centered in the tighter label",
)
assert.match(
  source,
  /className="chart-hover-ohlc-bg"[\s\S]*?width=\{504\}/,
  "Hover OHLC panel should use a tighter width",
)
assert.match(
  source,
  /className="chart-hover-ohlc-bg"[\s\S]*?x=\{4\}/,
  "Hover OHLC panel should align fully left",
)
assert.match(
  source,
  /className="chart-hover-ohlc-values"[\s\S]*?x=\{10\}/,
  "Hover OHLC values should use reduced horizontal padding at the left edge",
)
assert.match(
  source,
  /className="chart-hover-ohlc-bg"[\s\S]*?height=\{44\}/,
  "Hover OHLC panel should shrink after removing the title row",
)
assert.match(
  source,
  /className="chart-hover-ohlc-values"[\s\S]*?y=\{PRICE_TOP \+ 25\}/,
  "Hover OHLC values should move into the removed title row space",
)
assert.ok(
  !source.includes('className="chart-hover-ohlc-title"'),
  "Hover OHLC panel should not render a symbol/date title",
)
assert.match(
  source,
  /chart-hover-change-\$\{changeRateTone\(chartHoverState\.changeRates\.open\)\}/,
  "Hover OHLC panel should color the open change rate from the computed tone",
)
assert.ok(
  source.includes('{ value: "monthly", label: "월봉" }'),
  "Charts page should expose monthly candles",
)
assert.ok(
  source.includes('selectedChartPeriod === "monthly" ? monthGroupKey'),
  "Charts page should aggregate monthly candles with monthGroupKey",
)
for (const expectedDateFormat of [
  'selectedChartPeriod === "annual"',
  'selectedChartPeriod === "monthly"',
  "`${year}-${month}-${day}`",
  "`${year}-${month}`",
]) {
  assert.ok(source.includes(expectedDateFormat), `Charts page should format dates with ${expectedDateFormat}`)
}
for (const expectedDateUsage of [
  "formatChartDateLabel(first.timestamp, selectedChartPeriod)",
  "formatChartDateLabel(last.timestamp, selectedChartPeriod)",
  "formatChartDateLabel(chartHoverState.candle.timestamp, selectedChartPeriod)",
]) {
  assert.ok(source.includes(expectedDateUsage), `Charts page should use ${expectedDateUsage}`)
}
assert.ok(
  source.includes("selectedChartPeriod={selectedChartPeriod}"),
  "Candle chart should receive the selected period for date labels",
)
for (const expectedOhlcValue of [
  "previousCandle?.close ?? null",
  "changeRateForPrice(hoverCandle.open, previousClose)",
  "changeRateForPrice(hoverCandle.high, previousClose)",
  "changeRateForPrice(hoverCandle.low, previousClose)",
  "changeRateForPrice(hoverCandle.close, previousClose)",
  "시작 {formatPrice(chartHoverState.candle.open, currency)}",
  "formatChangeRate(chartHoverState.changeRates.open)",
  "고가{\" \"}",
  "formatPrice(chartHoverState.candle.open, currency)",
  "formatPrice(chartHoverState.candle.high, currency)",
  "formatChangeRate(chartHoverState.changeRates.high)",
  "저가{\" \"}",
  "formatPrice(chartHoverState.candle.low, currency)",
  "formatChangeRate(chartHoverState.changeRates.low)",
  "종가{\" \"}",
  "formatPrice(chartHoverState.candle.close, currency)",
  "formatChangeRate(chartHoverState.changeRates.close)",
  "formatChartDateLabel(chartHoverState.candle.timestamp, selectedChartPeriod)",
]) {
  assert.ok(source.includes(expectedOhlcValue), `Charts page should show ${expectedOhlcValue}`)
}
assert.ok(
  !source.includes("chartHoverState.candle.symbol"),
  "Hover OHLC panel should not show the selected symbol",
)
assert.ok(
  !source.includes(" · {formatChartDateLabel(chartHoverState.candle.timestamp, selectedChartPeriod)}"),
  "Hover OHLC panel should not show a title date next to the symbol",
)
assert.ok(
  !source.includes("변화율 {formatChangeRate(chartHoverState.changeRate)}"),
  "Charts page should not show a single standalone hover change rate",
)
for (const legacyOhlcLabel of ["O {", "· H", "· L", "· C"]) {
  assert.ok(!source.includes(legacyOhlcLabel), `Charts page should not show ${legacyOhlcLabel}`)
}
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
assert.ok(styles.includes(".chart-hover-price-line"), "Styles should define hover price guide")
assert.ok(styles.includes(".chart-hover-price-label"), "Styles should define hover price label")
assert.ok(styles.includes(".chart-hover-vertical-line"), "Styles should define hover date guide")
assert.ok(styles.includes(".chart-hover-date-label"), "Styles should define hover date label")
assert.ok(styles.includes(".chart-hover-ohlc-panel"), "Styles should define hover OHLC panel")
assert.ok(styles.includes(".chart-hover-change-rate"), "Styles should define hover change rate")
assert.ok(
  !styles.includes(".chart-hover-ohlc-title"),
  "Styles should not keep unused hover OHLC title styling",
)
assert.match(
  styles,
  /\.chart-hover-change-up\s*\{[\s\S]*?fill:\s*#dc2626;/,
  "Styles should color increasing hover change rates red",
)
assert.match(
  styles,
  /\.chart-hover-change-down\s*\{[\s\S]*?fill:\s*#2563eb;/,
  "Styles should color decreasing hover change rates blue",
)
assert.ok(styles.includes(".chart-hover-ohlc-values"), "Styles should define hover OHLC values")
assert.ok(styles.includes(".marker-selected-header"), "Styles should define selected marker header")
assert.ok(styles.includes(".marker-detail-grid"), "Styles should define selected marker detail layout")
assert.ok(styles.includes(".marker-note-actions"), "Styles should define marker note actions")

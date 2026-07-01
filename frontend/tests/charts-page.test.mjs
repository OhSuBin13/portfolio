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
  "chartSettingsOpen",
  "setChartSettingsOpen",
  "SettingsIcon",
  "X",
  "chart-settings-toggle",
  "chart-settings-overlay",
  "chart-settings-dialog",
  "차트 설정 열기",
  "차트 설정 닫기",
  "aria-modal=\"true\"",
  "role=\"dialog\"",
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
  "chart-symbol-summary",
  "chart-markers",
  "markerMemoDraft",
  "markerMemoOpen",
  "setMarkerMemoOpen",
  "clearSelectedMarker",
  "openMarkerMemoDialog",
  "memoMarkers",
  "memoListExpanded",
  "setMemoListExpanded",
  "chart-panel-layout",
  "memo-expanded",
  "marker-memo-drawer",
  "marker-memo-toggle",
  "marker-memo-compose-button",
  "marker-memo-overlay",
  "marker-memo-dialog",
  "marker-memo-list-panel",
  "marker-memo-list-item",
  "marker-memo-preview",
  "선택한 매매 마커 판단 메모 작성",
  "판단 메모 작성 화면 닫기",
  "작성된 판단 메모 펼치기",
  "작성된 판단 메모 접기",
  "작성된 판단 메모",
  "작성된 판단 메모가 없습니다.",
  "marker-selected-header",
  "marker-detail-grid",
  "marker-note-field",
  "marker-note-actions",
  "판단 기록",
  "체결가",
  "판단 메모",
  "placeholder",
]) {
  assert.ok(source.includes(expectedText), `Charts page should include ${expectedText}`)
}

assert.ok(source.includes("TossCandle"), "Charts page should type candle data")
assert.ok(source.includes("TossOrder"), "Charts page should use Toss orders for trade markers")
assert.ok(source.includes("ChartMarkerMemo"), "Charts page should type marker memos")
assert.ok(source.includes("selectedHoldingKey"), "Charts page should select a held symbol")
assert.ok(source.includes("<svg"), "Charts page should render an SVG candlestick chart")
assert.ok(source.includes("candle-chart-svg"), "Charts page should use stable chart SVG styling")
assert.ok(
  source.includes('className="chart-symbol-summary"'),
  "Charts page should show a compact symbol and current price summary above the chart",
)
assert.match(
  source,
  /className="chart-symbol-summary"[\s\S]*?<strong>\{selectedHolding\.name\}<\/strong>[\s\S]*?<span>\|<\/span>[\s\S]*?<strong>\{formatPrice\(latest\.close, selectedHolding\.currency\)\}<\/strong>/,
  "Charts page should display only the selected holding name and current close price above the chart",
)
assert.ok(
  !source.includes('className="candle-summary-grid"'),
  "Charts page should remove the old candle summary card grid",
)
for (const removedSummaryLabel of [
  "<span>종목</span>",
  "<span>종가</span>",
  "<span>고가 / 저가</span>",
  "<span>표시 봉</span>",
]) {
  assert.ok(!source.includes(removedSummaryLabel), `Charts page should remove ${removedSummaryLabel}`)
}
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
assert.ok(
  source.includes("[...tradeMarkers].reverse().filter((marker) => marker.memo.trim())"),
  "Charts page should build a newest-first list of markers with written memos",
)
assert.ok(
  source.includes("memoMarkers.map((marker) =>"),
  "Charts page should render the written marker memo list",
)
assert.ok(
  source.includes('onClick={() => selectMarker(marker)}'),
  "Written marker memo list items should select the marker for editing",
)
assert.ok(
  source.includes('selectedMarkerKey === marker.key ? " selected" : ""'),
  "Written marker memo list should reflect the selected marker",
)
assert.ok(
  source.includes("const [memoListExpanded, setMemoListExpanded] = useState(false)"),
  "Written marker memo list should be collapsed by default",
)
assert.ok(
  source.includes("setMemoListExpanded((current) => !current)"),
  "Written marker memo toggle should switch between expanded and collapsed",
)
assert.ok(
  source.includes('aria-expanded={memoListExpanded}'),
  "Written marker memo toggle should expose its expanded state",
)
assert.ok(
  source.includes('{memoListExpanded ? ">>" : "<<"}'),
  "Written marker memo toggle should switch from << to >> when expanded",
)
assert.ok(
  source.includes("{memoListExpanded && ("),
  "Written marker memo list should only render while expanded",
)
assert.match(
  source,
  /<div className=\{`chart-panel-layout\$\{memoListExpanded \? " memo-expanded" : ""\}`\}>[\s\S]*?<section className="panel chart-panel">[\s\S]*?<\/section>\s*\{visibleChartCandles\.length > 0 && selectedHolding && \([\s\S]*?<div className="marker-memo-drawer">[\s\S]*?<button[\s\S]*?className="marker-memo-toggle"[\s\S]*?\{memoListExpanded \? ">>" : "<<"}[\s\S]*?\{memoListExpanded && \([\s\S]*?<aside className="marker-memo-list-panel"/,
  "Written marker memo drawer should stay outside the chart panel and render the list only when expanded",
)
assert.ok(
  !source.includes('className="chart-main-grid"'),
  "Charts page should not keep the memo list inside the chart panel grid",
)
assert.ok(
  source.includes("const [markerMemoOpen, setMarkerMemoOpen] = useState(false)"),
  "Marker memo dialog should be hidden by default",
)
assert.ok(
  source.includes("const clearSelectedMarker = () =>"),
  "Charts page should centralize clearing the selected marker",
)
assert.ok(
  source.includes('setSelectedMarkerKey("")'),
  "Clearing the selected marker should remove the selected marker key",
)
assert.ok(
  source.includes('setMarkerMemoDraft("")'),
  "Clearing the selected marker should reset the memo draft",
)
assert.ok(
  source.includes("setMarkerMemoOpen(false)"),
  "Clearing or saving should close the marker memo dialog",
)
assert.ok(
  source.includes("const openMarkerMemoDialog = () =>"),
  "Charts page should open marker memo editing from the plus button",
)
assert.ok(
  source.includes("setMarkerMemoDraft(selectedMarker.memo)"),
  "Opening marker memo editing should initialize the draft from the selected marker memo",
)
assert.ok(
  source.includes("setMarkerMemoOpen(true)"),
  "Opening marker memo editing should show the floating memo dialog",
)
assert.ok(
  source.includes("const handleChartBlankClick = () =>"),
  "Charts page should clear the selected marker when the chart blank area is clicked",
)
assert.ok(
  source.includes("onClick={handleChartBlankClick}"),
  "Chart viewport should clear the selected marker on blank clicks",
)
assert.ok(
  source.includes("event.stopPropagation()"),
  "Trade marker clicks should not bubble to the chart blank-click handler",
)
assert.match(
  source,
  /\{selectedMarker && \([\s\S]*?<button[\s\S]*?aria-label="선택한 매매 마커 판단 메모 작성"[\s\S]*?className="icon-button marker-memo-compose-button"[\s\S]*?onClick=\{openMarkerMemoDialog\}[\s\S]*?<Plus size=\{17\} \/>[\s\S]*?<\/button>[\s\S]*?\)\}/,
  "Marker memo drawer should only show the plus button for a selected marker",
)
assert.ok(
  !source.includes("disabled={!selectedMarker}"),
  "Marker memo plus button should be hidden instead of rendered disabled",
)
assert.ok(
  !source.includes("매매 마커를 선택하면 판단 메모를 작성할 수 있습니다."),
  "Charts page should not keep hidden-state copy for a disabled plus button",
)
assert.match(
  source,
  /\{markerMemoOpen && selectedMarker && \([\s\S]*?<div[\s\S]*?className="marker-memo-overlay"[\s\S]*?<section[\s\S]*?aria-label="판단 메모 작성"[\s\S]*?aria-modal="true"[\s\S]*?className="panel marker-memo-dialog"[\s\S]*?role="dialog"/,
  "Marker memo editing should open in a floating dialog",
)
assert.match(
  source,
  /apiPost<ChartMarkerMemo>\("\/api\/toss\/chart-marker-memos"[\s\S]*?\.then\(\(saved\) => \{[\s\S]*?setSelectedMarkerKey\(saved\.marker_key\)[\s\S]*?setMarkerMemoOpen\(false\)/,
  "Saving a marker memo should persist it and close the dialog",
)
assert.match(
  source,
  /\{markerMemoOpen && selectedMarker && \([\s\S]*?aria-label="판단 메모 작성 화면 닫기"[\s\S]*?onClick=\{\(\) => setMarkerMemoOpen\(false\)\}[\s\S]*?<X size=\{16\} \/>/,
  "Marker memo dialog should close from the x button",
)
assert.ok(
  !source.includes("<h3>매매 마커</h3>"),
  "Charts page should not keep the old bottom marker memo panel",
)
for (const legacyOhlcLabel of ["O {", "· H", "· L", "· C"]) {
  assert.ok(!source.includes(legacyOhlcLabel), `Charts page should not show ${legacyOhlcLabel}`)
}
assert.ok(source.includes("보유 종목 차트"), "Charts page should present one holdings chart panel")
assert.ok(
  source.includes("const [chartSettingsOpen, setChartSettingsOpen] = useState(false)"),
  "Chart settings overlay should be hidden by default",
)
assert.ok(
  source.includes("onClick={() => setChartSettingsOpen(true)}"),
  "Chart heading should open settings from the gear button",
)
assert.ok(
  source.includes("onClick={() => setChartSettingsOpen(false)}"),
  "Chart settings dialog should include an explicit close control",
)
assert.ok(
  source.includes("event.target === event.currentTarget"),
  "Chart settings overlay should close when the backdrop is clicked",
)
assert.ok(
  source.includes("{chartSettingsOpen && ("),
  "Chart settings should only render while the overlay is open",
)
assert.match(
  source,
  /<div className="section-heading-actions chart-heading-actions">[\s\S]*?<button[\s\S]*?aria-label="차트 설정 열기"[\s\S]*?className="icon-button chart-settings-toggle"[\s\S]*?<SettingsIcon size=\{17\} \/>/,
  "Chart heading should expose chart settings through a gear icon button",
)
assert.match(
  source,
  /\{chartSettingsOpen && \([\s\S]*?<div[\s\S]*?className="chart-settings-overlay"[\s\S]*?<section[\s\S]*?aria-label="차트 설정"[\s\S]*?aria-modal="true"[\s\S]*?className="panel chart-settings-panel chart-settings-dialog"[\s\S]*?role="dialog"/,
  "Chart settings should open in a screen overlay dialog",
)

assert.ok(typesSource.includes("export type TossCandle"), "Frontend types should include Toss candles")
assert.ok(
  typesSource.includes("export type ChartMarkerMemo"),
  "Frontend types should include chart marker memos",
)
assert.ok(styles.includes(".candle-chart-svg"), "Styles should size the candlestick SVG")
assert.ok(styles.includes(".chart-symbol-summary"), "Styles should define compact chart symbol summary")
assert.ok(!styles.includes(".candle-summary-grid"), "Styles should not keep old candle summary grid")
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
assert.ok(styles.includes(".chart-panel-layout"), "Styles should define chart panel and memo side layout")
assert.ok(styles.includes(".chart-panel-layout.memo-expanded"), "Styles should define expanded memo drawer layout")
assert.ok(styles.includes(".chart-settings-toggle"), "Styles should define the chart settings gear button")
assert.ok(styles.includes(".chart-settings-overlay"), "Styles should define the floating settings overlay")
assert.ok(styles.includes("position: fixed"), "Styles should float chart settings above the screen")
assert.ok(styles.includes(".chart-settings-dialog"), "Styles should define the settings dialog")
assert.ok(
  !styles.includes(".chart-main-grid"),
  "Styles should not keep the old in-panel chart and memo grid",
)
assert.ok(styles.includes(".marker-memo-drawer"), "Styles should define written memo drawer")
assert.ok(styles.includes(".marker-memo-toggle"), "Styles should define written memo drawer toggle")
assert.ok(styles.includes(".marker-memo-compose-button"), "Styles should define marker memo plus button")
assert.ok(styles.includes(".marker-memo-overlay"), "Styles should define floating marker memo overlay")
assert.ok(styles.includes(".marker-memo-dialog"), "Styles should define floating marker memo dialog")
assert.ok(styles.includes(".marker-memo-list-panel"), "Styles should define written memo side panel")
assert.ok(styles.includes(".marker-memo-list-item"), "Styles should define written memo list items")
assert.ok(styles.includes(".marker-memo-preview"), "Styles should define written memo previews")
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

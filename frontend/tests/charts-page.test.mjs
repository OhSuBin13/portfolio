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

assert.ok(source.includes("/api/toss/accounts"), "Charts page should load Toss accounts")
assert.ok(source.includes("/api/toss/holdings"), "Charts page should load held symbols")
assert.ok(source.includes("/api/toss/candles"), "Charts page should load Toss candle data")
assert.ok(source.includes("TossCandle"), "Charts page should type candle data")
assert.ok(source.includes("selectedHoldingKey"), "Charts page should select a held symbol")
assert.ok(source.includes("<svg"), "Charts page should render an SVG candlestick chart")
assert.ok(source.includes("candle-chart-svg"), "Charts page should use stable chart SVG styling")
assert.ok(source.includes("보유 종목 차트"), "Charts page should present one holdings chart panel")

assert.ok(typesSource.includes("export type TossCandle"), "Frontend types should include Toss candles")
assert.ok(styles.includes(".candle-chart-svg"), "Styles should size the candlestick SVG")
assert.ok(styles.includes(".candle-up"), "Styles should define rising candle color")
assert.ok(styles.includes(".candle-down"), "Styles should define falling candle color")

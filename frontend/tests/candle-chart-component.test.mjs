import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/CandleChart.tsx", import.meta.url), "utf8")
const chartsPageSource = readFileSync(
  new URL("../src/components/ChartsPage.tsx", import.meta.url),
  "utf8",
)

assert.ok(source.includes("export function CandleChart"), "CandleChart should be a named export")
assert.ok(source.includes("export type MovingAverageConfig"), "Moving average config should move with the chart component")
assert.ok(source.includes("handleChartHoverMove"), "CandleChart should own hover tracking")
assert.ok(source.includes("spreadOverlappingMarkers"), "CandleChart should own marker placement")
assert.ok(source.includes("movingAveragePoints"), "CandleChart should own moving-average paths")
assert.ok(
  chartsPageSource.includes('from "./CandleChart"'),
  "ChartsPage should import the extracted CandleChart component",
)
assert.ok(
  !chartsPageSource.includes("function CandleChart({"),
  "ChartsPage should not define CandleChart inline",
)

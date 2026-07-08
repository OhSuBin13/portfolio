import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(
  new URL("../src/components/AllocationChart.tsx", import.meta.url),
  "utf8",
)
const dashboardSource = readFileSync(new URL("../src/components/Dashboard.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export function AllocationChart"), "Allocation chart should be a named export")
assert.ok(source.includes("allocationSegments"), "Allocation chart should receive allocation segments")
assert.ok(source.includes("getAllocationCallouts"), "Allocation chart should calculate label callouts")
assert.ok(source.includes("pieChart"), "Allocation chart should own pie viewport dimensions")
assert.ok(source.includes('className="allocation-chart"'), "Allocation chart should own the chart shell")
assert.ok(source.includes('className="allocation-pie-svg"'), "Allocation chart should render the pie SVG")
assert.ok(source.includes("allocationCallouts.map((callout) =>"), "Allocation chart should render callout paths")
assert.ok(source.includes("visibleAllocationSegments.map((segment) =>"), "Allocation chart should render meter segments")
assert.ok(source.includes("allocationSegments.map((segment) =>"), "Allocation chart should render legend rows")
assert.ok(
  dashboardSource.includes('from "./AllocationChart"'),
  "Dashboard should import the extracted allocation chart component",
)
assert.ok(
  !dashboardSource.includes('className="allocation-chart"'),
  "Dashboard should not keep allocation chart markup inline",
)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/allocationChart.ts", import.meta.url), "utf8")
const dashboardSource = readFileSync(new URL("../src/components/Dashboard.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export type AllocationSegment"), "Allocation segment type should move with chart helpers")
assert.ok(source.includes("export type AllocationCallout"), "Allocation callout type should move with chart helpers")
assert.ok(source.includes("export const pieChart"), "Pie chart dimensions should move with chart helpers")
assert.ok(source.includes("export const getAllocationSegments"), "Allocation segment builder should be exported")
assert.ok(source.includes("export const getAllocationCallouts"), "Allocation callout builder should be exported")
assert.ok(source.includes("const getPieSlicePath"), "Pie slice path calculation should move with chart helpers")
assert.ok(source.includes("const distributeCalloutY"), "Callout label distribution should move with chart helpers")
assert.ok(source.includes("key: allocation.asset_key"), "Allocation rows should still key by Toss asset key")
assert.ok(source.includes("allocation.symbol || allocation.name"), "Allocation rows should prefer ticker labels")
assert.ok(
  dashboardSource.includes("../allocationChart"),
  "Dashboard should import extracted allocation chart helpers",
)
assert.ok(
  !dashboardSource.includes("const getPieSlicePath"),
  "Dashboard should not keep pie path calculation inline",
)

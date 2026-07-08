import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/growthHistoryFormat.ts", import.meta.url), "utf8")
const pageSource = readFileSync(new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("export const formatKrw"), "KRW formatter should move with growth helpers")
assert.ok(source.includes("export const formatReturnPercent"), "Return formatter should move with growth helpers")
assert.ok(source.includes("(value - 1) * 100"), "Return formatter should preserve ratio-to-percent conversion")
assert.ok(source.includes("export const buildAccountQuery"), "Account query helper should move with growth helpers")
assert.ok(source.includes("export const monthRowKey"), "Month row key helper should be exported")
assert.ok(source.includes("export const annualRowKey"), "Annual row key helper should be exported")
assert.ok(source.includes("export const getReturnToneClass"), "Return tone helper should be exported")
assert.ok(source.includes("return-tone-positive"), "Return tone helper should preserve positive tone")
assert.ok(
  pageSource.includes("../growthHistoryFormat"),
  "GrowthHistoryPage should import extracted growth helper functions",
)
assert.ok(
  !pageSource.includes("const formatReturnPercent ="),
  "GrowthHistoryPage should not keep return formatting inline",
)

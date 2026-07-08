import assert from "node:assert/strict"

const { normalizeNumericInput, parseRequiredNumber } = await import("../src/numberInputs.ts")

assert.equal(normalizeNumericInput(" 1,234,567 "), "1234567")
assert.equal(normalizeNumericInput("\t0.25\n"), "0.25")
assert.equal(parseRequiredNumber(" 1,350.5 "), 1350.5)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/GoalsPage.tsx", import.meta.url), "utf8")

assert.ok(source.includes("목표 금액"), "Goals page should render the target amount field")
assert.ok(
  source.includes('import { normalizeNumericInput } from "../numberInputs"'),
  "Goals page should reuse the shared numeric input normalizer",
)
assert.ok(
  source.includes("Number(normalizeNumericInput(form.targetAmountKrw))"),
  "Goals page should parse the normalized target amount",
)
assert.ok(
  !source.includes("Number(form.targetAmountKrw)"),
  "Goals page should not parse the raw target amount directly",
)
assert.ok(
  source.includes("target_amount_krw: targetAmountKrw"),
  "Goals page should submit the parsed numeric target amount",
)

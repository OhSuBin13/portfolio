import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const helperPath = new URL("../src/transactionPayload.ts", import.meta.url)
assert.ok(existsSync(helperPath), "transaction payload builder should live in a shared frontend module")

const helperSource = readFileSync(helperPath, "utf8")
const transactionsPageSource = readFileSync(
  new URL("../src/components/TransactionsPage.tsx", import.meta.url),
  "utf8",
)
const holdingsPageSource = readFileSync(
  new URL("../src/components/HoldingsPage.tsx", import.meta.url),
  "utf8",
)
const packageSource = readFileSync(new URL("../package.json", import.meta.url), "utf8")

assert.ok(
  helperSource.includes("export type TransactionPayload"),
  "shared helper should type the transaction POST payload",
)
assert.ok(
  helperSource.includes("export function buildTransactionPayload"),
  "shared helper should export a payload builder",
)
assert.ok(
  helperSource.includes("occurred_on: input.occurredOn"),
  "shared helper should translate form camelCase fields to API snake_case fields",
)
assert.ok(
  helperSource.includes("currency: input.currency.trim().toUpperCase()"),
  "shared helper should normalize transaction currency",
)
assert.ok(
  helperSource.includes("memo: input.memo.trim()"),
  "shared helper should normalize transaction memo",
)

for (const [name, source] of [
  ["TransactionsPage", transactionsPageSource],
  ["HoldingsPage", holdingsPageSource],
]) {
  assert.ok(
    source.includes('import { buildTransactionPayload } from "../transactionPayload"'),
    `${name} should import the shared payload builder`,
  )
  assert.ok(
    source.includes('apiPost<Transaction>("/api/transactions", buildTransactionPayload({'),
    `${name} should post transactions through the shared payload builder`,
  )
  assert.ok(
    !source.includes("occurred_on:"),
    `${name} should not inline transaction API field names`,
  )
  assert.ok(
    !source.includes("fx_rate_to_krw:"),
    `${name} should not inline transaction API field names`,
  )
}

assert.ok(
  packageSource.includes("transaction-payload-builder.test.mjs"),
  "package test script should include transaction payload builder checks",
)

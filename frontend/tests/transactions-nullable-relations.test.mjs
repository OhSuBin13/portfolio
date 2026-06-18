import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const pageSource = readFileSync(new URL("../src/components/TransactionsPage.tsx", import.meta.url), "utf8")
const packageSource = readFileSync(new URL("../package.json", import.meta.url), "utf8")

assert.ok(
  typesSource.includes("account_id: number | null"),
  "Transaction type should allow deleted account references",
)
assert.ok(
  typesSource.includes("asset_id: number | null"),
  "Transaction type should allow deleted asset references",
)
assert.ok(
  pageSource.includes("transaction.account_id === null"),
  "Transactions page should render deleted account references explicitly",
)
assert.ok(
  pageSource.includes("transaction.asset_id === null"),
  "Transactions page should render deleted asset references explicitly",
)
assert.ok(
  packageSource.includes("transactions-nullable-relations.test.mjs"),
  "package test script should include nullable transaction relation checks",
)

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const pageSource = readFileSync(new URL("../src/components/TransactionsPage.tsx", import.meta.url), "utf8")
const holdingsSource = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
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
assert.ok(
  pageSource.includes('const requiresFxRate = form.currency.trim().toUpperCase() !== "KRW"'),
  "Transactions page should require an FX rate before posting non-KRW transactions",
)
assert.ok(
  holdingsSource.includes(
    'const requiresFxRate = balanceForm.currency.trim().toUpperCase() !== "KRW"',
  ),
  "Holdings initial-balance form should require an FX rate before posting non-KRW transactions",
)
assert.ok(
  pageSource.includes("외화 거래에는 환율을 입력하세요."),
  "Transactions page should explain the non-KRW FX requirement",
)
assert.ok(
  holdingsSource.includes("외화 거래에는 환율을 입력하세요."),
  "Holdings page should explain the non-KRW FX requirement",
)

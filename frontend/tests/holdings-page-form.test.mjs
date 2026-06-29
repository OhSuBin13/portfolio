import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

assert.ok(source.includes("/api/toss/accounts"), "Holdings page should load Toss brokerage accounts")
assert.ok(source.includes("/api/toss/holdings"), "Holdings page should load Toss holdings")
assert.ok(source.includes("Toss 보유자산"), "Holdings page should present Toss holdings")
assert.ok(source.includes("account_seq"), "Holdings page should use Toss account sequence identifiers")
assert.ok(source.includes("readOnly"), "Holdings page should not present manual ledger writes")

for (const removedEndpoint of ["/api/" + "accounts", "/api/" + "assets", "/api/" + "transactions"]) {
  assert.ok(!source.includes(removedEndpoint), `${removedEndpoint} should not be used by Toss-only holdings`)
}

for (const removedText of ["계좌 만들기", "자산 만들기", "초기 잔액/보유 반영", "초기 거래 저장"]) {
  assert.ok(!source.includes(removedText), `${removedText} should be removed from Toss-only holdings`)
}

assert.ok(!appSource.includes('active === "transactions"'), "App should not mount the local ledger page")
assert.ok(!shellSource.includes('id: "transactions"'), "Navigation should not expose local transactions")
assert.ok(!shellSource.includes('id: "growth"'), "Navigation should not expose transaction-derived growth")

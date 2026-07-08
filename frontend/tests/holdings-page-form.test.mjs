import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

assert.ok(source.includes("/api/toss/accounts"), "Holdings page should load Toss brokerage accounts")
assert.ok(source.includes("/api/toss/holdings"), "Holdings page should load Toss holdings")
assert.ok(source.includes("/api/toss/buying-power"), "Holdings page should load Toss buying power")
assert.ok(source.includes("TossBuyingPower"), "Holdings page should type Toss buying power")
assert.ok(source.includes("Toss 보유자산"), "Holdings page should present Toss holdings")
assert.ok(source.includes("매수 가능 금액"), "Holdings page should show buying power")
assert.ok(source.includes("cash_buying_power"), "Holdings page should render raw buying power amounts")
assert.ok(source.includes("account_seq"), "Holdings page should use Toss account sequence identifiers")
assert.ok(source.includes("readOnly"), "Holdings page should not present manual ledger writes")
assert.ok(
  source.includes("portfolioLoadedAccountSeq"),
  "Holdings page should track whether selected-account data has finished loading",
)
assert.ok(
  source.includes("disabled={accounts.length === 0}"),
  "Holdings page should render the account selector immediately while accounts load",
)
assert.ok(
  source.includes("buyingPowerEmptyMessage") && source.includes("holdingsEmptyMessage"),
  "Holdings page should render stable table empty/loading rows before Toss data arrives",
)
assert.ok(
  source.includes('className="empty-table-cell"') &&
    source.includes("colSpan={2}") &&
    source.includes("colSpan={7}"),
  "Holdings page should keep buying-power and holdings table structures visible while loading",
)

const selectedAccountFetchStart = source.indexOf("if (!selectedAccountSeq)")
const selectedAccountLoadingReset = source.indexOf("setHoldingsLoading(false)", selectedAccountFetchStart)
const selectedAccountHoldingsClear = source.indexOf("setHoldings([])", selectedAccountFetchStart)
const selectedAccountHoldingsErrorClear = source.indexOf('setHoldingsError("")', selectedAccountFetchStart)
const selectedAccountBuyingPowerClear = source.indexOf("setBuyingPower([])", selectedAccountFetchStart)
const selectedAccountFetchRequest = source.indexOf("Promise.allSettled([", selectedAccountFetchStart)
assert.ok(
  selectedAccountFetchStart >= 0 &&
    selectedAccountLoadingReset > selectedAccountFetchStart &&
    selectedAccountLoadingReset < selectedAccountFetchRequest,
  "Holdings page should clear loading when account selection becomes empty",
)
assert.ok(
  selectedAccountFetchStart >= 0 &&
    selectedAccountHoldingsClear > selectedAccountFetchStart &&
    selectedAccountHoldingsClear < selectedAccountFetchRequest,
  "Holdings page should clear holdings before fetching a newly selected account",
)
assert.ok(
  selectedAccountFetchStart >= 0 &&
    selectedAccountHoldingsErrorClear > selectedAccountFetchStart &&
    selectedAccountHoldingsErrorClear < selectedAccountFetchRequest,
  "Holdings page should clear holdings errors before fetching a newly selected account",
)
assert.ok(
  selectedAccountFetchStart >= 0 &&
    selectedAccountBuyingPowerClear > selectedAccountFetchStart &&
    selectedAccountBuyingPowerClear < selectedAccountFetchRequest,
  "Holdings page should clear buying power before fetching a newly selected account",
)
assert.ok(
  source.includes("buyingPowerError") && source.includes("setBuyingPowerError"),
  "Holdings page should track buying-power errors separately",
)
assert.ok(
  source.includes("Promise.allSettled(["),
  "Holdings page should isolate holdings and buying-power fetch failures",
)
assert.ok(
  source.includes("holdingResult.status") && source.includes("buyingPowerResult.status"),
  "Holdings page should handle holdings and buying-power results independently",
)

for (const removedEndpoint of ["/api/" + "accounts", "/api/" + "assets", "/api/" + "transactions"]) {
  assert.ok(!source.includes(removedEndpoint), `${removedEndpoint} should not be used by Toss-only holdings`)
}

for (const removedText of ["계좌 만들기", "자산 만들기", "초기 잔액/보유 반영", "초기 거래 저장"]) {
  assert.ok(!source.includes(removedText), `${removedText} should be removed from Toss-only holdings`)
}

assert.ok(!appSource.includes('active === "transactions"'), "App should not mount the local ledger page")
assert.ok(
  appSource.includes("holdingsMounted") && appSource.includes('hidden={active !== "holdings"}'),
  "App should keep the holdings page mounted after first visit for fast return navigation",
)
assert.ok(
  !appSource.includes('{active === "holdings" && <HoldingsPage />}'),
  "App should not remount the holdings page when navigating back from another page",
)
assert.ok(!shellSource.includes('id: "transactions"'), "Navigation should not expose local transactions")

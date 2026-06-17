import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8")

function labelBlocks(labelText) {
  const blocks = []
  let cursor = 0

  while (cursor < source.length) {
    const labelIndex = source.indexOf(labelText, cursor)
    if (labelIndex === -1) {
      break
    }

    const start = source.lastIndexOf("<label>", labelIndex)
    const end = source.indexOf("</label>", labelIndex)
    assert.notEqual(start, -1, `${labelText} label should be wrapped in a label element`)
    assert.notEqual(end, -1, `${labelText} label should close its label element`)

    blocks.push(source.slice(start, end))
    cursor = end + "</label>".length
  }

  return blocks
}

function optionValues(block) {
  return Array.from(block.matchAll(/<option\s+value="([^"]+)"/g), (match) => match[1])
}

function sourceBlock(startText, endText) {
  const start = source.indexOf(startText)
  assert.notEqual(start, -1, `${startText} block should exist`)

  const end = source.indexOf(endText, start)
  assert.notEqual(end, -1, `${endText} should appear after ${startText}`)

  return source.slice(start, end)
}

const currencyBlocks = labelBlocks("통화")
assert.equal(currencyBlocks.length, 2, "Holdings page should expose only asset and balance currency controls")

for (const block of currencyBlocks) {
  assert.match(block, /<select\b/, "currency control should be a select")
  assert.doesNotMatch(block, /<input\b/, "currency control should not be a free text input")
  assert.deepEqual(optionValues(block), ["KRW", "USD"], "currency select should offer KRW and USD")
}

const marketBlocks = labelBlocks("시장")
assert.equal(marketBlocks.length, 1, "Holdings page should expose one market control")
assert.match(marketBlocks[0], /<select\b/, "market control should be a select")
assert.doesNotMatch(marketBlocks[0], /<input\b/, "market control should not be a free text input")
assert.deepEqual(optionValues(marketBlocks[0]), ["US"], "market select should only offer US")

const assetTypesBlock = sourceBlock("const assetTypes = [", "]\n\nconst initialTransactionTypes")
assert.ok(
  !assetTypesBlock.includes('["cash", "현금"]'),
  "cash should be a built-in asset instead of a manual asset creation option",
)
assert.deepEqual(
  Array.from(assetTypesBlock.matchAll(/\["([^"]+)",/g), (match) => match[1]),
  ["stock_etf"],
  "asset creation should only expose manually tracked stock/ETF assets",
)

const accountFormBlock = sourceBlock("const [accountForm", "const [accountEditForm")
assert.ok(!accountFormBlock.includes("currency"), "account forms should not store account currency")

const balanceFormBlock = sourceBlock("const [balanceForm", "const [accountMessage")
assert.ok(balanceFormBlock.includes('currency: "KRW"'), "initial cash balances should default to KRW")

assert.ok(
  source.includes('const selectedBalanceAsset = assets.find((asset) => String(asset.id) === balanceForm.assetId)'),
  "initial balance form should derive the selected asset",
)
assert.ok(
  source.includes('const showBalanceQuantity = selectedBalanceAsset?.type === "stock_etf"'),
  "quantity should only be available for stock/ETF assets",
)

const quantityLabelMatch = source.match(/<label>\s+수량\s+<input/)
assert.ok(quantityLabelMatch, "quantity label should exist for stock/ETF assets")
const quantityLabelIndex = quantityLabelMatch.index ?? -1
assert.ok(
  source.lastIndexOf("showBalanceQuantity &&", quantityLabelIndex) !== -1,
  "quantity label should be conditionally rendered by stock/ETF asset type",
)

assert.ok(!source.includes('market: "KR"'), "market default should no longer use KR")

assert.match(source, /apiGet<Account>\(`\/api\/accounts\/\$\{accountId\}`\)/, "account detail should load through the account detail API")
assert.match(source, /apiPut<Account>\(`\/api\/accounts\/\$\{selectedAccountId\}`/, "account edits should use the account update API")
assert.match(source, /apiDelete\(`\/api\/accounts\/\$\{selectedAccountId\}`\)/, "account deletion should use the selected account delete API")
assert.ok(source.includes('type HoldingsView = "overview" | "account-detail"'), "Holdings page should model a separate account detail page")
assert.ok(source.includes('setHoldingsView("account-detail")'), "management action should navigate to the account detail page")
assert.ok(source.includes('setHoldingsView("overview")'), "account detail page should navigate back to the holdings overview")
assert.ok(source.includes("계좌 목록"), "Holdings page should include an account list section")
assert.ok(source.includes("계좌 상세"), "Holdings page should include an account detail page")
assert.ok(source.includes("list_accounts"), "account list section should identify list_accounts")
assert.ok(source.includes("get_account"), "account detail section should identify get_account")
assert.ok(source.includes("수정 저장"), "Holdings page should expose an account update action")
assert.ok(source.includes("삭제"), "Holdings page should expose an account delete action")

const accountListBlock = sourceBlock('data-view="holdings-overview"', 'className="panel form-panel compact-form"')
assert.ok(accountListBlock.includes("관리"), "account list rows should expose the management action")
assert.ok(!accountListBlock.includes("수정 저장"), "account list page should not expose update before navigation")
assert.ok(!accountListBlock.includes("삭제"), "account list page should not expose delete before navigation")

const accountDetailBlock = sourceBlock('data-view="account-detail"', "data-view=\"holdings-overview\"")
assert.ok(accountDetailBlock.includes("수정 저장"), "account detail page should expose update")
assert.ok(accountDetailBlock.includes("삭제"), "account detail page should expose delete")
assert.ok(accountDetailBlock.includes("목록으로"), "account detail page should expose a back action")

assert.match(apiSource, /export async function apiPut<T>/, "API helper should expose PUT requests")
assert.match(apiSource, /export async function apiDelete/, "API helper should expose DELETE requests")

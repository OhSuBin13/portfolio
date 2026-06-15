import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")

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

const currencyBlocks = labelBlocks("통화")
assert.equal(currencyBlocks.length, 3, "Holdings page should expose three currency controls")

for (const block of currencyBlocks) {
  assert.match(block, /<select\b/, "currency control should be a select")
  assert.doesNotMatch(block, /<input\b/, "currency control should not be a free text input")
  assert.deepEqual(optionValues(block), ["USD"], "currency select should only offer USD")
}

const marketBlocks = labelBlocks("시장")
assert.equal(marketBlocks.length, 1, "Holdings page should expose one market control")
assert.match(marketBlocks[0], /<select\b/, "market control should be a select")
assert.doesNotMatch(marketBlocks[0], /<input\b/, "market control should not be a free text input")
assert.deepEqual(optionValues(marketBlocks[0]), ["US"], "market select should only offer US")

assert.ok(!source.includes('currency: "KRW"'), "currency defaults should no longer use KRW")
assert.ok(!source.includes('market: "KR"'), "market default should no longer use KR")

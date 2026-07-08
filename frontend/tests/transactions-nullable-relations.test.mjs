import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const holdingsSource = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
const packageSource = readFileSync(new URL("../package.json", import.meta.url), "utf8")
const removedPageFile = new URL(
  "../src/components/" + ["Transactions", "Page.tsx"].join(""),
  import.meta.url,
)
const removedEndpoint = "/api/" + "transactions"

assert.ok(!typesSource.includes("export type Transaction ="), "Local transaction type should be removed")
assert.ok(!existsSync(removedPageFile), "Local transaction page should be removed")
assert.ok(!holdingsSource.includes(removedEndpoint), "Holdings should not write local transactions")
assert.ok(
  packageSource.includes("node --test tests/*.test.mjs") ||
    packageSource.includes("transactions-nullable-relations.test.mjs"),
  "package test script should include the Toss-only transaction removal guard",
)

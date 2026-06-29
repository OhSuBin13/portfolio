import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const removedPageFile = new URL(
  "../src/components/" + ["Growth", "History", "Page.tsx"].join(""),
  import.meta.url,
)

assert.ok(!appSource.includes('active === "growth"'), "Toss-only app should not mount growth history")
assert.ok(!shellSource.includes("성장기록"), "Toss-only app should remove growth navigation")
assert.ok(!existsSync(removedPageFile), "Toss-only app should delete the transaction-derived growth page")

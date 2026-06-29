import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const growthPageFile = new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url)

assert.ok(!appSource.includes("GrowthHistoryPage"), "Toss-only app should not mount transaction-derived growth history")
assert.ok(!shellSource.includes("성장기록"), "Toss-only app should remove growth navigation")
assert.ok(!existsSync(growthPageFile), "Toss-only app should delete the transaction-derived growth page")

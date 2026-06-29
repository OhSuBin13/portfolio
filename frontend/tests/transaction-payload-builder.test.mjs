import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const payloadFile = new URL("../src/" + ["transaction", "Payload.ts"].join(""), import.meta.url)

assert.ok(!appSource.includes('active === "transactions"'), "Toss-only app should remove transaction entry")
assert.ok(!existsSync(payloadFile), "Toss-only app should remove local transaction payload builder")

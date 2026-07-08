import assert from "node:assert/strict"

const { getErrorMessage } = await import("../src/errors.ts")

assert.equal(getErrorMessage(new Error("network unavailable")), "network unavailable")
assert.equal(getErrorMessage("plain failure"), "plain failure")
assert.equal(getErrorMessage(503), "503")

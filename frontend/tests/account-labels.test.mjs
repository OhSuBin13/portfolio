import assert from "node:assert/strict"

const { formatTossAccountLabel } = await import("../src/accountLabels.ts")

assert.equal(
  formatTossAccountLabel({
    account_no: "123",
    account_seq: "seq-1",
    account_type: "위탁",
    display_name: "나의 해외주식",
  }),
  "나의 해외주식 (위탁)",
)

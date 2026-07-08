import assert from "node:assert/strict"

const { apiGet } = await import("../src/api.ts")
const originalFetch = globalThis.fetch

try {
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: [
          {
            loc: ["query", "account_seq"],
            msg: "Field required",
            type: "missing",
          },
          {
            loc: ["body", "target_amount_krw"],
            msg: "Input should be greater than 0",
            type: "greater_than",
          },
        ],
      }),
      { status: 422, statusText: "Unprocessable Entity" },
    )

  await assert.rejects(
    () => apiGet("/api/test"),
    {
      message: "query.account_seq: Field required\nbody.target_amount_krw: Input should be greater than 0",
    },
  )
} finally {
  globalThis.fetch = originalFetch
}

export type TransactionPayload = {
  occurred_on: string
  type: string
  account_id: number
  asset_id: number
  quantity: number | null
  amount: number
  currency: string
  memo: string
  fx_rate_to_krw: number | null
}

export type TransactionPayloadInput = {
  occurredOn: string
  type: string
  accountId: number
  assetId: number
  quantity: number | null
  amount: number
  currency: string
  memo: string
  fxRateToKrw: number | null
}

export function buildTransactionPayload(input: TransactionPayloadInput): TransactionPayload {
  return {
    occurred_on: input.occurredOn,
    type: input.type,
    account_id: input.accountId,
    asset_id: input.assetId,
    quantity: input.quantity,
    amount: input.amount,
    currency: input.currency.trim().toUpperCase(),
    memo: input.memo.trim(),
    fx_rate_to_krw: input.fxRateToKrw,
  }
}

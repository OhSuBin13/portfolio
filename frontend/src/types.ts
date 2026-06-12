export type PortfolioSummary = {
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  asset_mix: Record<string, number>
}

export type Account = {
  id: number
  name: string
  type: string
  currency: string
}

export type Asset = {
  id: number
  symbol: string | null
  name: string
  type: string
  currency: string
  market: string
}

export type Transaction = {
  id: number
  occurred_on: string
  type: string
  account_id: number
  asset_id: number
  quantity: number | null
  amount: number
  currency: string
  memo: string
}

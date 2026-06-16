export type PortfolioSummary = {
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  usd_krw_rate: number | null
  usd_krw_change_percent: number | null
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
  market: string | null
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
  fx_rate_to_krw: number | null
  memo: string
}

export type Goal = {
  id: number
  name: string
  type: "net_worth" | "monthly_income"
  target_amount_krw: number
}

export type GoalProgress = {
  goal: Goal
  current_amount_krw: number
  percent: number
  remaining_krw: number
}

export type BackupRecord = {
  path: string
  reason: string
  created_at: string
}

export type MarketSyncRow = {
  asset_id: number
  symbol: string
  status: string
  error_message: string
}

export type MarketSyncResult = {
  results: MarketSyncRow[]
}

export type MarketDataStatus = {
  asset_id: number
  source: string
  price_krw: number | null
  status: string
  error_message: string | null
  fetched_at: string | null
}

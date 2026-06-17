export type AssetAllocation = {
  asset_id: number
  asset_type: string
  symbol: string | null
  name: string
  label: string
  value_krw: number
  percent: number
}

export type PortfolioSummary = {
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  usd_krw_rate: number | null
  usd_krw_change_percent: number | null
  asset_mix: Record<string, number>
  asset_allocations: AssetAllocation[]
}

export type PortfolioSnapshot = {
  id: number
  snapshot_date: string
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  asset_mix: Record<string, number>
  source: "scheduled" | "manual" | "market_sync" | "import"
  created_at: string
  updated_at: string
}

export type GrowthHistoryRow = {
  period: string
  start_date: string
  end_date: string
  starting_net_worth_krw: number
  ending_net_worth_krw: number
  external_cash_flow_krw: number
  dividend_interest_krw: number
  profit_krw: number
  growth_rate: number | null
  cumulative_profit_krw: number
  cumulative_growth_rate: number | null
}

export type Account = {
  id: number
  name: string
  type: string
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

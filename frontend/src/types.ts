export type AssetAllocation = {
  asset_key: string
  asset_type: "stock_etf"
  symbol: string
  name: string
  label: string
  market: "KR" | "US"
  currency: "KRW" | "USD"
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
  goal_progress: GoalProgress[]
}

export type TossAccount = {
  account_seq: string
  account_no: string
  account_type: string
  display_name: string
}

export type TossHolding = {
  symbol: string
  name: string
  market: "KR" | "US"
  currency: "KRW" | "USD"
  quantity: number
  average_purchase_price: number
  last_price: number | null
  market_value: number
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

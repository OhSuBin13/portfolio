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

export type TossBuyingPower = {
  currency: "KRW" | "USD"
  cash_buying_power: number
}

export type SummaryBuyingPower = TossBuyingPower & {
  value_krw: number
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
  buying_power: SummaryBuyingPower[]
  buying_power_total_krw: number
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

export type TossOrder = {
  id: number
  account_seq: string
  order_id: string
  symbol: string
  side: string
  order_type: string
  time_in_force: string
  order_status: string
  price: string | null
  quantity: string
  order_amount: string | null
  currency: string
  ordered_at: string
  canceled_at: string | null
  filled_quantity: string
  average_filled_price: string | null
  filled_amount: string | null
  commission: string | null
  tax: string | null
  filled_at: string | null
  settlement_date: string | null
  imported_at: string
  updated_at: string
}

export type TossOrderImportRun = {
  id: number
  account_seq: string
  status_filter: "OPEN" | "CLOSED"
  symbol_filter: string | null
  from_date: string | null
  to_date: string | null
  run_status: "running" | "success" | "failed"
  imported_count: number
  error_message: string
  started_at: string
  completed_at: string | null
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

export type GrowthMonthHistoryRow = {
  account_seq: string
  year: number
  month: number
  net_worth_krw: number
  monthly_dividend_krw: number
  monthly_return_ratio: number | null
  average_return_ratio: number | null
  cumulative_dividend_krw: number
  created_at: string
  updated_at: string
}

export type GrowthAnnualHistoryRow = {
  account_seq: string
  year: number
  display_year: string
  source_month: number
  net_worth_krw: number
  annual_return_ratio: number | null
  average_return_ratio: number | null
  sp500_annual_return_ratio: number | null
}

export type Sp500ProxyPriceRow = {
  year: number
  proxy_symbol: "VOO"
  price: number
  currency: "USD"
  created_at: string
  updated_at: string
}

export type BackupRecord = {
  path: string
  reason: string
  created_at: string
}

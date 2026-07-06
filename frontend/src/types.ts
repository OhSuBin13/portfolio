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

export type TossCandle = {
  symbol: string
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
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

export type ChartMarkerMemo = {
  id: number
  account_seq: string
  symbol: string
  marker_key: string
  memo: string
  created_at: string
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

export type CanslimLetterStatus = "pass" | "watch" | "fail" | "unknown" | "info"

export type CanslimMarketRange = "3m" | "6m" | "1y"

export type CanslimLetter = {
  status: CanslimLetterStatus
  headline: string
  details: string[]
  metrics: Record<string, unknown>
  source: string
  as_of: string | null
}

export type CanslimInstitutionalFlow = {
  holders_count_change: number | null
  shares_change_percent: number | null
  ownership_percent: number | null
  market_value_change_percent: number | null
}

export type CanslimTopPerformingHolder = {
  holder_name: string
  cik: string
  shares: number
  market_value: number
  position_change_percent: number | null
  portfolio_weight_percent: number | null
  performance_1y_percent: number | null
  performance_3y_percent: number | null
  performance_5y_percent: number | null
  excess_vs_sp500_percent: number | null
}

export type CanslimInstitutionalLetter = CanslimLetter & {
  institutional_flow: CanslimInstitutionalFlow
  top_performing_holders: CanslimTopPerformingHolder[]
}

export type CanslimMarketCandle = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  traded_value_usd: number
}

export type CanslimMarketContext = {
  status: "info"
  symbol: "SPY"
  range: CanslimMarketRange
  candles: CanslimMarketCandle[]
  source: string
  as_of: string | null
}

export type CanslimAnalysis = {
  symbol: string
  company_name: string | null
  exchange: string | null
  sector: string | null
  industry: string | null
  description: string | null
  currency: string
  provider: "fmp"
  generated_at: string
  cached: boolean
  letters: {
    c: CanslimLetter
    a: CanslimLetter
    n: CanslimLetter
    s: CanslimLetter
    l: CanslimLetter
    i: CanslimInstitutionalLetter
    m: CanslimMarketContext
  }
}

export type BackupRecord = {
  path: string
  reason: string
  created_at: string
}

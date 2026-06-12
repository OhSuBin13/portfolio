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

export type ImportMappedRow = {
  row_number: number
  asset_type: string
  name: string
  symbol?: string | null
  quantity: number
  price?: number | null
  average_cost?: number | null
  fx_rate_to_krw?: number | null
  value_krw: number
  message: string
}

export type ImportIgnoredRow = {
  row_number: number
  message: string
}

export type ImportPreview = {
  mapped_rows: ImportMappedRow[]
  ignored_rows: ImportIgnoredRow[]
}

export type ImportConfirmResult = {
  created_accounts: number
  created_assets: number
  created_holdings: number
  created_transactions: number
  backup_path: string
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

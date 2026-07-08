import type { GrowthAnnualHistoryRow, GrowthMonthHistoryRow } from "./types"

export const formatKrw = (value: number) =>
  `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원`

export const formatReturnPercent = (value: number | null) => {
  if (value === null) {
    return "-"
  }

  const percent = (value - 1) * 100
  const rounded = Number(percent.toFixed(2))
  const normalized = Object.is(rounded, -0) ? 0 : rounded
  return `${normalized.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`
}

export const buildAccountQuery = (path: string, accountSeq: string) =>
  `${path}?account_seq=${encodeURIComponent(accountSeq)}`

export const monthRowKey = (row: GrowthMonthHistoryRow) =>
  `${row.account_seq}:${row.year}:${row.month}`

export const annualRowKey = (row: GrowthAnnualHistoryRow) =>
  `${row.account_seq}:${row.year}:${row.source_month}`

export const getReturnToneClass = (value: number | null) => {
  if (value === null) {
    return ""
  }

  if (value > 1) {
    return "return-tone-positive"
  }

  if (value < 1) {
    return "return-tone-negative"
  }

  return ""
}

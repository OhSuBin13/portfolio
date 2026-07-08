export const periodOptions = [
  { value: "day", label: "일" },
  { value: "month", label: "월" },
  { value: "year", label: "년" },
] as const

export const ORDER_SYMBOL_FILTER_DEBOUNCE_MS = 400

export type PeriodFilter = (typeof periodOptions)[number]["value"]

export type OrderQuerySnapshot = {
  accountSeq: string
  symbolFilter: string
  fromDate: string
  toDate: string
}

const formatDatePart = (date: Date) => {
  const year = String(date.getFullYear())
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")

  return `${year}-${month}-${day}`
}

export const getPeriodRange = (periodFilter: PeriodFilter) => {
  const today = new Date()
  const from = new Date(today)

  if (periodFilter === "year") {
    from.setMonth(0, 1)
  } else if (periodFilter === "month") {
    from.setDate(1)
  }

  return {
    fromDate: formatDatePart(from),
    toDate: formatDatePart(today),
  }
}

export const buildOrderQuery = (
  selectedAccountSeq: string,
  symbolFilter: string,
  fromDate: string,
  toDate: string,
) => {
  const params = new URLSearchParams({ account_seq: selectedAccountSeq })

  const symbol = symbolFilter.trim()
  if (symbol) {
    params.set("symbol", symbol)
  }
  if (fromDate) {
    params.set("from", fromDate)
  }
  if (toDate) {
    params.set("to", toDate)
  }

  return `/api/toss/orders?${params.toString()}`
}

export const orderQueryKeyFrom = (snapshot: OrderQuerySnapshot) =>
  JSON.stringify([
    snapshot.accountSeq,
    snapshot.symbolFilter.trim(),
    snapshot.fromDate,
    snapshot.toDate,
  ])

export const buildOrderQueryFromSnapshot = (snapshot: OrderQuerySnapshot) =>
  buildOrderQuery(snapshot.accountSeq, snapshot.symbolFilter, snapshot.fromDate, snapshot.toDate)

export const buildImportRunsQuery = (accountSeq: string) =>
  `/api/toss/order-imports?account_seq=${encodeURIComponent(accountSeq)}`

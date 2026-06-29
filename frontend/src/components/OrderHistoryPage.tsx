import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Search, X } from "lucide-react"
import { apiGet, apiPost } from "../api"
import type { TossAccount, TossOrder, TossOrderImportRun } from "../types"

const periodOptions = [
  { value: "day", label: "일" },
  { value: "month", label: "월" },
  { value: "year", label: "년" },
] as const

type PeriodFilter = (typeof periodOptions)[number]["value"]

type OrderQuerySnapshot = {
  accountSeq: string
  symbolFilter: string
  fromDate: string
  toDate: string
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const accountLabel = (account: TossAccount) =>
  `${account.display_name} (${account.account_type})`

const displayValue = (value: string | null) => value || "-"

const formatDatePart = (date: Date) => {
  const year = String(date.getFullYear())
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")

  return `${year}-${month}-${day}`
}

const getPeriodRange = (periodFilter: PeriodFilter) => {
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

const formatDateTime = (value: string | null) => {
  if (!value) {
    return "-"
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  })
}

const buildOrderQuery = (
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

const orderQueryKeyFrom = (snapshot: OrderQuerySnapshot) =>
  JSON.stringify([
    snapshot.accountSeq,
    snapshot.symbolFilter.trim(),
    snapshot.fromDate,
    snapshot.toDate,
  ])

const buildOrderQueryFromSnapshot = (snapshot: OrderQuerySnapshot) =>
  buildOrderQuery(snapshot.accountSeq, snapshot.symbolFilter, snapshot.fromDate, snapshot.toDate)

const buildImportRunsQuery = (accountSeq: string) =>
  `/api/toss/order-imports?account_seq=${encodeURIComponent(accountSeq)}`

export function OrderHistoryPage() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("day")
  const [symbolFilter, setSymbolFilter] = useState("")
  const [symbolSearchOpen, setSymbolSearchOpen] = useState(false)
  const [orders, setOrders] = useState<TossOrder[]>([])
  const [importRuns, setImportRuns] = useState<TossOrderImportRun[]>([])
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [loadedOrderQueryKey, setLoadedOrderQueryKey] = useState("")
  const [importingQueryKey, setImportingQueryKey] = useState<string | null>(null)
  const [accountsError, setAccountsError] = useState("")
  const [ordersError, setOrdersError] = useState("")
  const [importError, setImportError] = useState("")
  const latestOrderQueryKeyRef = useRef("")
  const latestSelectedAccountSeqRef = useRef("")
  const latestImportRequestIdRef = useRef(0)
  const periodRange = useMemo(() => getPeriodRange(periodFilter), [periodFilter])

  const currentOrderQueryKey = orderQueryKeyFrom({
    accountSeq: selectedAccountSeq,
    symbolFilter,
    fromDate: periodRange.fromDate,
    toDate: periodRange.toDate,
  })

  useEffect(() => {
    latestOrderQueryKeyRef.current = currentOrderQueryKey
    latestSelectedAccountSeqRef.current = selectedAccountSeq
  }, [currentOrderQueryKey, selectedAccountSeq])

  const isCurrentImportSnapshot = useCallback(
    (snapshot: OrderQuerySnapshot, requestId: number) =>
      latestImportRequestIdRef.current === requestId &&
      latestOrderQueryKeyRef.current === orderQueryKeyFrom(snapshot),
    [],
  )

  const isCurrentImportAccount = useCallback(
    (accountSeq: string, requestId: number) =>
      latestImportRequestIdRef.current === requestId &&
      latestSelectedAccountSeqRef.current === accountSeq,
    [],
  )

  const hasCurrentOrders = loadedOrderQueryKey === currentOrderQueryKey
  const shouldShowOrdersLoading =
    ordersLoading || Boolean(selectedAccountSeq && !hasCurrentOrders && !ordersError)
  const importing = importingQueryKey === currentOrderQueryKey

  useEffect(() => {
    let ignore = false

    apiGet<TossAccount[]>("/api/toss/accounts")
      .then((accountData) => {
        if (ignore) {
          return
        }

        setAccounts(accountData)
        setAccountsLoaded(true)
        setAccountsError("")
        setSelectedAccountSeq((current) => {
          if (current && accountData.some((account) => account.account_seq === current)) {
            return current
          }
          return accountData[0]?.account_seq ?? ""
        })
        if (accountData.length === 0) {
          setOrders([])
          setImportRuns([])
          setLoadedOrderQueryKey("")
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        setOrders([])
        setImportRuns([])
        setSelectedAccountSeq("")
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
        setLoadedOrderQueryKey("")
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    let ignore = false

    if (selectedAccountSeq) {
      const requestSnapshot: OrderQuerySnapshot = {
        accountSeq: selectedAccountSeq,
        symbolFilter,
        fromDate: periodRange.fromDate,
        toDate: periodRange.toDate,
      }
      const requestQueryKey = currentOrderQueryKey
      void Promise.resolve()
        .then(() => {
          if (ignore) {
            return []
          }

          setOrdersLoading(true)
          setOrdersError("")
          return apiGet<TossOrder[]>(buildOrderQueryFromSnapshot(requestSnapshot))
        })
        .then((orderData) => {
          if (ignore) {
            return
          }

          setOrders(orderData)
          setOrdersError("")
          setLoadedOrderQueryKey(requestQueryKey)
        })
        .catch((err) => {
          if (!ignore) {
            setOrders([])
            setOrdersError(getErrorMessage(err))
            setLoadedOrderQueryKey("")
          }
        })
        .finally(() => {
          if (!ignore) {
            setOrdersLoading(false)
          }
        })
    }

    return () => {
      ignore = true
    }
  }, [
    currentOrderQueryKey,
    periodRange.fromDate,
    periodRange.toDate,
    selectedAccountSeq,
    symbolFilter,
  ])

  useEffect(() => {
    let ignore = false

    if (selectedAccountSeq) {
      apiGet<TossOrderImportRun[]>(buildImportRunsQuery(selectedAccountSeq))
        .then((runData) => {
          if (!ignore) {
            setImportRuns(runData)
            setImportError("")
          }
        })
        .catch((err) => {
          if (!ignore) {
            setImportRuns([])
            setImportError(getErrorMessage(err))
          }
        })
    }

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq])

  const latestImportRun = useMemo(
    () =>
      importRuns.reduce<TossOrderImportRun | null>(
        (latest, run) => (!latest || run.started_at > latest.started_at ? run : latest),
        null,
      ),
    [importRuns],
  )

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)

  const refreshImportRunsForSnapshot = useCallback(
    (snapshot: OrderQuerySnapshot, requestId: number, clearImportError = false) =>
      apiGet<TossOrderImportRun[]>(buildImportRunsQuery(snapshot.accountSeq)).then((runData) => {
        if (isCurrentImportAccount(snapshot.accountSeq, requestId)) {
          setImportRuns(runData)
        }
        if (clearImportError && isCurrentImportSnapshot(snapshot, requestId)) {
          setImportError("")
        }
      }),
    [isCurrentImportAccount, isCurrentImportSnapshot],
  )

  useEffect(() => {
    if (!selectedAccountSeq) {
      return undefined
    }

    const submittedSnapshot: OrderQuerySnapshot = {
      accountSeq: selectedAccountSeq,
      symbolFilter,
      fromDate: periodRange.fromDate,
      toDate: periodRange.toDate,
    }
    const submittedQueryKey = orderQueryKeyFrom(submittedSnapshot)
    const importRequestId = latestImportRequestIdRef.current + 1
    latestImportRequestIdRef.current = importRequestId

    const symbol = submittedSnapshot.symbolFilter.trim()

    void Promise.resolve()
      .then(() => {
        if (!isCurrentImportSnapshot(submittedSnapshot, importRequestId)) {
          return null
        }

        setImportingQueryKey(submittedQueryKey)
        setImportError("")
        return apiPost<TossOrderImportRun>("/api/toss/order-imports", {
          account_seq: submittedSnapshot.accountSeq,
          status: "CLOSED",
          symbol: symbol || null,
          from_date: submittedSnapshot.fromDate || null,
          to_date: submittedSnapshot.toDate || null,
        })
      })
      .then((run) => {
        if (!run) {
          return undefined
        }

        if (isCurrentImportAccount(submittedSnapshot.accountSeq, importRequestId)) {
          setImportRuns((current) => [run, ...current.filter((item) => item.id !== run.id)])
        }
        return Promise.all([
          apiGet<TossOrder[]>(buildOrderQueryFromSnapshot(submittedSnapshot)).then((orderData) => {
            if (isCurrentImportSnapshot(submittedSnapshot, importRequestId)) {
              setOrders(orderData)
              setOrdersError("")
              setLoadedOrderQueryKey(orderQueryKeyFrom(submittedSnapshot))
            }
          }),
          refreshImportRunsForSnapshot(submittedSnapshot, importRequestId, true),
        ])
      })
      .catch((err) => {
        if (isCurrentImportSnapshot(submittedSnapshot, importRequestId)) {
          setImportError(getErrorMessage(err))
        }
        return refreshImportRunsForSnapshot(submittedSnapshot, importRequestId).catch(
          () => undefined,
        )
      })
      .finally(() => {
        if (latestImportRequestIdRef.current === importRequestId) {
          setImportingQueryKey((current) => (current === submittedQueryKey ? null : current))
        }
      })

    return () => {
      if (latestImportRequestIdRef.current === importRequestId) {
        latestImportRequestIdRef.current += 1
      }
    }
  }, [
    currentOrderQueryKey,
    isCurrentImportAccount,
    isCurrentImportSnapshot,
    periodRange.fromDate,
    periodRange.toDate,
    refreshImportRunsForSnapshot,
    selectedAccountSeq,
    symbolFilter,
  ])

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>Toss 주문내역</h2>
        <p>토스증권 계좌의 주문내역 가져오기 이력과 저장된 주문을 조회합니다.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {ordersError && <div className="error">{ordersError}</div>}
      {importError && <div className="error">{importError}</div>}

      <section className="panel form-panel order-query-panel">
        <div className="order-toolbar">
          <div className="currency-toggle order-period-toggle" aria-label="주문 기간 선택">
            {periodOptions.map((option) => (
              <button
                aria-pressed={periodFilter === option.value}
                className={periodFilter === option.value ? "active" : ""}
                key={option.value}
                onClick={() => setPeriodFilter(option.value)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="order-search">
            {symbolSearchOpen && (
              <input
                aria-label="종목"
                autoFocus
                className="order-symbol-input"
                onChange={(event) => setSymbolFilter(event.target.value)}
                placeholder="AAPL"
                value={symbolFilter}
              />
            )}
            <button
              aria-label="종목 검색"
              aria-pressed={symbolSearchOpen}
              className="icon-button"
              onClick={() => setSymbolSearchOpen((current) => !current)}
              title="종목 검색"
              type="button"
            >
              <Search size={18} />
            </button>
            {(symbolSearchOpen || symbolFilter) && (
              <button
                aria-label="종목 검색 초기화"
                className="icon-button"
                onClick={() => {
                  setSymbolFilter("")
                  setSymbolSearchOpen(false)
                }}
                title="종목 검색 초기화"
                type="button"
              >
                <X size={18} />
              </button>
            )}
          </div>
        </div>
        <div className="section-heading">
          <h3>주문내역 조회</h3>
          <span>{accounts.length.toLocaleString("ko-KR")}개 계좌</span>
        </div>
        {accounts.length > 0 ? (
          <>
            <div className="form-grid single-column-form">
              <label>
                Toss 계좌
                <select
                  value={selectedAccountSeq}
                  onChange={(event) => setSelectedAccountSeq(event.target.value)}
                >
                  {accounts.map((account) => (
                    <option key={account.account_seq} value={account.account_seq}>
                      {accountLabel(account)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="form-message">
              Toss Open API 1.1.5 문서상 CLOSED 목록은 현재 지원되지 않을 수 있습니다.
            </p>
            <div className="mix-list">
              <div className="mix-row">
                <span>account_seq</span>
                <strong>{selectedAccountSeq}</strong>
              </div>
              <div className="mix-row">
                <span>계좌번호</span>
                <strong>{selectedAccount?.account_no ?? "-"}</strong>
              </div>
            </div>
            {importing && <p className="form-message">현재 조건으로 주문내역을 조회하는 중입니다.</p>}
          </>
        ) : (
          <p className="empty-state">
            {accountsLoaded
              ? "Toss 계좌가 없습니다. 서버의 Toss API 인증 정보를 확인하세요."
              : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>최근 가져오기</h3>
          <span>{importRuns.length.toLocaleString("ko-KR")}회</span>
        </div>
        {latestImportRun ? (
          <div className="mix-list">
            <div className="mix-row">
              <span>상태</span>
              <strong>{latestImportRun.run_status}</strong>
            </div>
            <div className="mix-row">
              <span>필터</span>
              <strong>
                {latestImportRun.status_filter}
                {latestImportRun.symbol_filter ? ` / ${latestImportRun.symbol_filter}` : ""}
              </strong>
            </div>
            <div className="mix-row">
              <span>가져온 주문</span>
              <strong>{latestImportRun.imported_count.toLocaleString("ko-KR")}건</strong>
            </div>
            <div className="mix-row">
              <span>시작 시각</span>
              <strong>{formatDateTime(latestImportRun.started_at)}</strong>
            </div>
            <div className="mix-row">
              <span>완료 시각</span>
              <strong>{formatDateTime(latestImportRun.completed_at)}</strong>
            </div>
            {latestImportRun.error_message && (
              <div className="mix-row">
                <span>오류</span>
                <strong>{latestImportRun.error_message}</strong>
              </div>
            )}
          </div>
        ) : (
          <p className="empty-state">가져오기 이력이 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>저장된 주문</h3>
          <span>{orders.length.toLocaleString("ko-KR")}건</span>
        </div>
        {hasCurrentOrders && orders.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>주문 시각</th>
                  <th>종목</th>
                  <th>매매</th>
                  <th>상태</th>
                  <th className="numeric-cell">수량</th>
                  <th className="numeric-cell">가격</th>
                  <th className="numeric-cell">체결 수량</th>
                  <th className="numeric-cell">체결 금액</th>
                  <th className="numeric-cell">수수료</th>
                  <th className="numeric-cell">세금</th>
                  <th>결제일</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>{formatDateTime(order.ordered_at)}</td>
                    <td>
                      <strong>{order.symbol}</strong>
                      <br />
                      <span>{order.currency}</span>
                    </td>
                    <td>{order.side}</td>
                    <td>{order.order_status}</td>
                    <td className="numeric-cell">{order.quantity}</td>
                    <td className="numeric-cell">{displayValue(order.price)}</td>
                    <td className="numeric-cell">{order.filled_quantity}</td>
                    <td className="numeric-cell">{displayValue(order.filled_amount)}</td>
                    <td className="numeric-cell">{displayValue(order.commission)}</td>
                    <td className="numeric-cell">{displayValue(order.tax)}</td>
                    <td>{displayValue(order.settlement_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">
            {shouldShowOrdersLoading
              ? "저장된 주문내역을 불러오는 중입니다."
              : "저장된 주문내역이 없습니다."}
          </p>
        )}
      </section>
    </section>
  )
}

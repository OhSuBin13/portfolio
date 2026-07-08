import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Search, X } from "lucide-react"
import { formatTossAccountLabel } from "../accountLabels"
import { apiGet, apiPost } from "../api"
import { getErrorMessage } from "../errors"
import {
  buildImportRunsQuery,
  buildOrderQueryFromSnapshot,
  ORDER_SYMBOL_FILTER_DEBOUNCE_MS,
  orderQueryKeyFrom,
  periodOptions,
  getPeriodRange,
  type OrderQuerySnapshot,
  type PeriodFilter,
} from "../orderHistoryQuery"
import type { TossAccount, TossOrder, TossOrderImportRun } from "../types"
import { OrderHistoryTable } from "./OrderHistoryTable"
import { OrderImportRunSummary } from "./OrderImportRunSummary"

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

export function OrderHistoryPage() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("day")
  const [symbolFilter, setSymbolFilter] = useState("")
  const [debouncedSymbolFilter, setDebouncedSymbolFilter] = useState("")
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

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSymbolFilter(symbolFilter)
    }, ORDER_SYMBOL_FILTER_DEBOUNCE_MS)

    return () => window.clearTimeout(timeoutId)
  }, [symbolFilter])

  const currentOrderQueryKey = orderQueryKeyFrom({
    accountSeq: selectedAccountSeq,
    symbolFilter: debouncedSymbolFilter,
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

    if (!selectedAccountSeq) {
      void Promise.resolve().then(() => {
        if (ignore || latestSelectedAccountSeqRef.current) {
          return
        }

        setOrdersLoading(false)
        setOrders([])
        setOrdersError("")
        setLoadedOrderQueryKey("")
      })
      return () => {
        ignore = true
      }
    }

    const requestSnapshot: OrderQuerySnapshot = {
      accountSeq: selectedAccountSeq,
      symbolFilter: debouncedSymbolFilter,
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

    return () => {
      ignore = true
    }
  }, [
    currentOrderQueryKey,
    periodRange.fromDate,
    periodRange.toDate,
    debouncedSymbolFilter,
    selectedAccountSeq,
  ])

  useEffect(() => {
    let ignore = false

    if (!selectedAccountSeq) {
      void Promise.resolve().then(() => {
        if (ignore || latestSelectedAccountSeqRef.current) {
          return
        }

        setImportRuns([])
        setImportError("")
      })
      return () => {
        ignore = true
      }
    }

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
      symbolFilter: debouncedSymbolFilter,
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
    debouncedSymbolFilter,
    selectedAccountSeq,
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
                      {formatTossAccountLabel(account)}
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
        <OrderImportRunSummary
          latestImportRun={latestImportRun}
          formatDateTime={formatDateTime}
        />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>저장된 주문</h3>
          <span>{orders.length.toLocaleString("ko-KR")}건</span>
        </div>
        {hasCurrentOrders && orders.length > 0 ? (
          <OrderHistoryTable orders={orders} formatDateTime={formatDateTime} />
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

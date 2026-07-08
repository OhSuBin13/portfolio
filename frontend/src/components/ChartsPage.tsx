import {
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type WheelEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  Plus,
  Settings as SettingsIcon,
  X,
} from "lucide-react"
import { apiDelete, apiGet, apiPost } from "../api"
import { formatTossAccountLabel } from "../accountLabels"
import { formatChartDateTime, type ChartPeriod } from "../chartDates"
import { buildTradeMarkers, type TradeMarker } from "../chartMarkers"
import { aggregateCandles } from "../chartSeries"
import {
  buildVisibleChartWindow,
  chartPanSteps,
  DRAG_PAN_STEP_PIXELS,
  nextChartPanOffset,
  nextChartZoom,
  visibleChartWindowSize,
} from "../chartViewport"
import { getErrorMessage } from "../errors"
import type { ChartMarkerMemo, TossAccount, TossCandle, TossHolding, TossOrder } from "../types"
import {
  CandleChart,
  CHART_HEIGHT,
  CHART_WIDTH,
  type MovingAverageConfig,
  PLOT_LEFT,
  PLOT_RIGHT,
  PRICE_BOTTOM_WITH_VOLUME,
} from "./CandleChart"
import { ChartSettingsDialog, type MovingAverageForm } from "./ChartSettingsDialog"
import { MarkerMemoDialog } from "./MarkerMemoDialog"

const chartPeriodOptions: ReadonlyArray<{
  value: ChartPeriod
  label: string
  shortLabel: string
}> = [
  { value: "daily", label: "일봉", shortLabel: "일" },
  { value: "weekly", label: "주봉", shortLabel: "주" },
  { value: "monthly", label: "월봉", shortLabel: "월" },
  { value: "annual", label: "연봉", shortLabel: "연" },
]

type ChartDragState = {
  lastX: number
}

const holdingKey = (holding: TossHolding) => `${holding.market}:${holding.symbol}`

const holdingLabel = (holding: TossHolding) =>
  `${holding.symbol} · ${holding.name} · ${holding.market}`

const chartMemoScopeKey = (accountSeq: string, symbol: string) =>
  JSON.stringify([accountSeq, symbol])

const formatPrice = (value: number, currency: TossHolding["currency"] | undefined) => {
  const formatted = value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })
  if (currency === "USD") {
    return `$${formatted}`
  }
  return `${formatted}${currency ? ` ${currency}` : ""}`
}

export function ChartsPage() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [holdings, setHoldings] = useState<TossHolding[]>([])
  const [selectedHoldingKey, setSelectedHoldingKey] = useState("")
  const [candles, setCandles] = useState<TossCandle[]>([])
  const [orders, setOrders] = useState<TossOrder[]>([])
  const [markerMemos, setMarkerMemos] = useState<ChartMarkerMemo[]>([])
  const [selectedChartPeriod, setSelectedChartPeriod] = useState<ChartPeriod>("daily")
  const [chartZoomWindow, setChartZoomWindow] = useState<number | null>(null)
  const [chartPanOffset, setChartPanOffset] = useState(0)
  const [chartDragState, setChartDragState] = useState<ChartDragState | null>(null)
  const [movingAverageConfigs, setMovingAverageConfigs] = useState<MovingAverageConfig[]>([
    { id: "ma-20", days: 20, color: "#2563eb", lineWidth: 2 },
  ])
  const [movingAverageForm, setMovingAverageForm] = useState<MovingAverageForm>({
    days: "60",
    color: "#7c3aed",
    lineWidth: "2",
  })
  const [showVolume, setShowVolume] = useState(true)
  const [chartSettingsOpen, setChartSettingsOpen] = useState(false)
  const [selectedMarkerKey, setSelectedMarkerKey] = useState("")
  const [markerMemoDraft, setMarkerMemoDraft] = useState("")
  const [markerMemoOpen, setMarkerMemoOpen] = useState(false)
  const [memoListExpanded, setMemoListExpanded] = useState(false)
  const [memoManageMode, setMemoManageMode] = useState(false)
  const [accountsError, setAccountsError] = useState("")
  const [holdingsError, setHoldingsError] = useState("")
  const [candlesError, setCandlesError] = useState("")
  const [ordersError, setOrdersError] = useState("")
  const [memoError, setMemoError] = useState("")
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [candlesLoading, setCandlesLoading] = useState(false)
  const [memoSaving, setMemoSaving] = useState(false)
  const currentMemoScopeKeyRef = useRef("")
  const memoSaveRequestIdRef = useRef(0)

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
          setHoldings([])
          setSelectedHoldingKey("")
          setCandles([])
          setOrders([])
          setMarkerMemos([])
          setChartZoomWindow(null)
          setChartPanOffset(0)
          setChartDragState(null)
          setMarkerMemoOpen(false)
          setMemoManageMode(false)
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        setHoldings([])
        setCandles([])
        setOrders([])
        setMarkerMemos([])
        setSelectedAccountSeq("")
        setSelectedHoldingKey("")
        setChartZoomWindow(null)
        setChartPanOffset(0)
        setChartDragState(null)
        setMarkerMemoOpen(false)
        setMemoManageMode(false)
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      void Promise.resolve().then(() => {
        setHoldingsLoading(false)
        setHoldings([])
        setSelectedHoldingKey("")
        setCandles([])
        setOrders([])
        setMarkerMemos([])
        setChartZoomWindow(null)
        setChartPanOffset(0)
        setChartDragState(null)
        setSelectedMarkerKey("")
        setMarkerMemoDraft("")
        setMarkerMemoOpen(false)
        setMemoManageMode(false)
        setHoldingsError("")
        setCandlesError("")
        setOrdersError("")
        setMemoError("")
      })
      return undefined
    }

    let ignore = false

    void Promise.resolve().then(() => {
      if (ignore) {
        return
      }

      setHoldingsLoading(true)
      setHoldings([])
      setSelectedHoldingKey("")
      setCandles([])
      setOrders([])
      setMarkerMemos([])
      setChartZoomWindow(null)
      setChartPanOffset(0)
      setChartDragState(null)
      setSelectedMarkerKey("")
      setMarkerMemoDraft("")
      setMarkerMemoOpen(false)
      setMemoManageMode(false)
      setHoldingsError("")
      setCandlesError("")
      setOrdersError("")
      setMemoError("")

      apiGet<TossHolding[]>(
        `/api/toss/holdings?account_seq=${encodeURIComponent(selectedAccountSeq)}`,
      )
        .then((holdingData) => {
          if (ignore) {
            return
          }

          setHoldings(holdingData)
          setHoldingsError("")
          setSelectedHoldingKey((current) => {
            if (current && holdingData.some((holding) => holdingKey(holding) === current)) {
              return current
            }
            return holdingData[0] ? holdingKey(holdingData[0]) : ""
          })
        })
        .catch((err) => {
          if (ignore) {
            return
          }

          setHoldings([])
          setSelectedHoldingKey("")
          setCandles([])
          setOrders([])
          setMarkerMemos([])
          setChartZoomWindow(null)
          setChartPanOffset(0)
          setChartDragState(null)
          setMarkerMemoOpen(false)
          setMemoManageMode(false)
          setHoldingsError(getErrorMessage(err))
        })
        .finally(() => {
          if (!ignore) {
            setHoldingsLoading(false)
          }
        })
    })

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq])

  const selectedHolding = holdings.find((holding) => holdingKey(holding) === selectedHoldingKey)

  useEffect(() => {
    currentMemoScopeKeyRef.current =
      selectedHolding && selectedAccountSeq
        ? chartMemoScopeKey(selectedAccountSeq, selectedHolding.symbol)
        : ""
  }, [selectedAccountSeq, selectedHolding])

  useEffect(() => {
    if (!selectedHolding || !selectedAccountSeq) {
      void Promise.resolve().then(() => {
        setCandlesLoading(false)
        setCandles([])
        setOrders([])
        setMarkerMemos([])
        setChartZoomWindow(null)
        setChartPanOffset(0)
        setChartDragState(null)
        setSelectedMarkerKey("")
        setMarkerMemoDraft("")
        setMarkerMemoOpen(false)
        setMemoManageMode(false)
        setCandlesError("")
        setOrdersError("")
        setMemoError("")
      })
      return undefined
    }

    let ignore = false
    const symbol = selectedHolding.symbol
    const candlePath = `/api/toss/candles?symbol=${encodeURIComponent(symbol)}&interval=1d&limit=1000`
    const orderPath = `/api/toss/orders?account_seq=${encodeURIComponent(selectedAccountSeq)}&symbol=${encodeURIComponent(symbol)}`
    const memoPath = `/api/toss/chart-marker-memos?account_seq=${encodeURIComponent(selectedAccountSeq)}&symbol=${encodeURIComponent(symbol)}`

    void Promise.resolve().then(() => {
      if (ignore) {
        return
      }

      setCandlesLoading(true)
      setCandles([])
      setOrders([])
      setMarkerMemos([])
      setChartZoomWindow(null)
      setChartPanOffset(0)
      setChartDragState(null)
      setSelectedMarkerKey("")
      setMarkerMemoDraft("")
      setMarkerMemoOpen(false)
      setMemoManageMode(false)
      setCandlesError("")
      setOrdersError("")
      setMemoError("")

      Promise.allSettled([
        apiGet<TossCandle[]>(candlePath),
        apiGet<TossOrder[]>(orderPath),
        apiGet<ChartMarkerMemo[]>(memoPath),
      ])
        .then(([candleResult, orderResult, memoResult]) => {
          if (ignore) {
            return
          }

          if (candleResult.status === "fulfilled") {
            setCandles(candleResult.value)
            setCandlesError("")
          } else {
            setCandles([])
            setCandlesError(getErrorMessage(candleResult.reason))
          }

          if (orderResult.status === "fulfilled") {
            setOrders(orderResult.value)
            setOrdersError("")
          } else {
            setOrders([])
            setOrdersError(getErrorMessage(orderResult.reason))
          }

          if (memoResult.status === "fulfilled") {
            setMarkerMemos(memoResult.value)
            setMemoError("")
          } else {
            setMarkerMemos([])
            setMemoError(getErrorMessage(memoResult.reason))
          }
        })
        .finally(() => {
          if (!ignore) {
            setCandlesLoading(false)
          }
        })
    })

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq, selectedHolding])

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)
  const chartCandles = useMemo(
    () => aggregateCandles(candles, selectedChartPeriod),
    [candles, selectedChartPeriod],
  )
  const visibleChartWindow = useMemo(() => {
    return buildVisibleChartWindow(chartCandles, chartZoomWindow, chartPanOffset)
  }, [chartCandles, chartPanOffset, chartZoomWindow])
  const visibleChartCandles = visibleChartWindow.candles
  const visibleCandleStartIndex = visibleChartWindow.startIndex
  const tradeMarkers = useMemo(
    () => buildTradeMarkers(orders, markerMemos),
    [markerMemos, orders],
  )
  const memoMarkers = useMemo(
    () => [...tradeMarkers].reverse().filter((marker) => marker.memo.trim()),
    [tradeMarkers],
  )
  const selectedMarker = tradeMarkers.find((marker) => marker.key === selectedMarkerKey)
  const latest = visibleChartCandles[visibleChartCandles.length - 1]
  const accountsLoading = !accountsLoaded && !accountsError
  const chartFrameLoading = accountsLoading || holdingsLoading || candlesLoading
  const chartEmptyMessage = holdingsLoading
    ? "보유 종목을 불러오는 중입니다."
    : candlesLoading
      ? "캔들 데이터를 불러오는 중입니다."
      : holdings.length === 0
        ? "선택한 Toss 계좌의 보유 종목이 없습니다."
        : "선택한 종목의 캔들 데이터가 없습니다."
  const chartFrameStatusMessage = accountsLoading
    ? "Toss 계좌를 불러오는 중입니다."
    : accounts.length === 0 && accountsLoaded
      ? "Toss 계좌가 없습니다. 서버의 Toss API 인증 정보를 확인하세요."
      : chartEmptyMessage
  const chartSummaryName = selectedHolding?.name ?? "차트 준비 중"
  const chartSummaryPrice =
    latest && selectedHolding
      ? formatPrice(latest.close, selectedHolding.currency)
      : chartFrameStatusMessage
  const chartSummaryLabel =
    latest && selectedHolding
      ? `${selectedHolding.name} 현재 가격 ${formatPrice(latest.close, selectedHolding.currency)}`
      : chartFrameStatusMessage

  const handleChartWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (chartCandles.length === 0) {
      return
    }
    event.preventDefault()

    const totalCandles = chartCandles.length
    const nextZoom = nextChartZoom(totalCandles, chartZoomWindow, chartPanOffset, event.deltaY > 0)
    setChartZoomWindow(nextZoom.zoomWindow)
    setChartPanOffset(nextZoom.panOffset)
  }

  const handleChartMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (chartCandles.length === 0 || event.button !== 0) {
      return
    }
    event.preventDefault()
    setChartDragState({ lastX: event.clientX })
  }

  const handleChartMouseMove = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!chartDragState || chartCandles.length === 0) {
      return
    }
    event.preventDefault()

    const totalCandles = chartCandles.length
    const visibleWindow = visibleChartWindowSize(totalCandles, chartZoomWindow)
    const maxPanOffset = Math.max(totalCandles - visibleWindow, 0)
    if (maxPanOffset === 0) {
      setChartDragState({ lastX: event.clientX })
      return
    }

    const deltaX = event.clientX - chartDragState.lastX
    const steps = chartPanSteps(deltaX)
    if (steps === 0) {
      return
    }

    setChartPanOffset((current) =>
      nextChartPanOffset(current, steps, totalCandles, visibleWindow),
    )
    setChartDragState({ lastX: chartDragState.lastX + steps * DRAG_PAN_STEP_PIXELS })
  }

  const handleChartMouseUp = () => {
    setChartDragState(null)
  }

  const clearSelectedMarker = () => {
    setSelectedMarkerKey("")
    setMarkerMemoDraft("")
    setMarkerMemoOpen(false)
    setMemoError("")
  }

  const handleChartBlankClick = () => {
    clearSelectedMarker()
  }

  const toggleMemoListExpanded = () => {
    if (memoListExpanded) {
      setMemoManageMode(false)
    }
    setMemoListExpanded((current) => !current)
  }

  const addMovingAverage = () => {
    const days = Number(movingAverageForm.days)
    const lineWidth = Number(movingAverageForm.lineWidth)
    if (!Number.isInteger(days) || days < 2 || days > 400) {
      return
    }
    if (!Number.isFinite(lineWidth) || lineWidth < 1 || lineWidth > 6) {
      return
    }
    setMovingAverageConfigs((current) => [
      ...current,
      {
        id: `ma-${days}-${movingAverageForm.color}-${lineWidth}-${current.length}`,
        days,
        color: movingAverageForm.color,
        lineWidth,
      },
    ])
  }

  const removeMovingAverage = (id: string) => {
    setMovingAverageConfigs((current) => current.filter((item) => item.id !== id))
  }

  const selectMarker = (marker: TradeMarker) => {
    setSelectedMarkerKey(marker.key)
    setMarkerMemoDraft(marker.memo)
    setMarkerMemoOpen(false)
    setMemoError("")
  }

  const openMarkerMemoDialog = () => {
    if (!selectedMarker) {
      return
    }
    setMarkerMemoDraft(selectedMarker.memo)
    setMemoError("")
    setMarkerMemoOpen(true)
  }

  const openMarkerMemoDetail = (marker: TradeMarker) => {
    setSelectedMarkerKey(marker.key)
    setMarkerMemoDraft(marker.memo)
    setMemoError("")
    setMarkerMemoOpen(true)
  }

  const handleMemoListItemKeyDown = (event: KeyboardEvent<HTMLDivElement>, marker: TradeMarker) => {
    if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) {
      return
    }
    event.preventDefault()
    openMarkerMemoDetail(marker)
  }

  const deleteMarkerMemo = (event: ReactMouseEvent<HTMLButtonElement>, marker: TradeMarker) => {
    event.stopPropagation()
    if (!selectedHolding || !selectedAccountSeq) {
      return
    }
    setMemoError("")
    const requestScopeKey = chartMemoScopeKey(selectedAccountSeq, selectedHolding.symbol)
    const path = `/api/toss/chart-marker-memos?account_seq=${encodeURIComponent(
      selectedAccountSeq,
    )}&symbol=${encodeURIComponent(selectedHolding.symbol)}&marker_key=${encodeURIComponent(
      marker.key,
    )}`
    apiDelete(path)
      .then(() => {
        if (currentMemoScopeKeyRef.current !== requestScopeKey) {
          return
        }
        setMarkerMemos((current) => current.filter((memo) => memo.marker_key !== marker.key))
        if (selectedMarkerKey === marker.key) {
          setSelectedMarkerKey("")
          setMarkerMemoDraft("")
          setMarkerMemoOpen(false)
        }
      })
      .catch((err) => {
        if (currentMemoScopeKeyRef.current === requestScopeKey) {
          setMemoError(getErrorMessage(err))
        }
      })
  }

  const saveMarkerMemo = () => {
    if (!selectedMarker || !selectedHolding || !selectedAccountSeq) {
      return
    }
    const requestScopeKey = chartMemoScopeKey(selectedAccountSeq, selectedHolding.symbol)
    const requestId = memoSaveRequestIdRef.current + 1
    memoSaveRequestIdRef.current = requestId
    setMemoSaving(true)
    setMemoError("")
    apiPost<ChartMarkerMemo>("/api/toss/chart-marker-memos", {
      account_seq: selectedAccountSeq,
      symbol: selectedHolding.symbol,
      marker_key: selectedMarker.key,
      memo: markerMemoDraft,
    })
      .then((saved) => {
        if (
          currentMemoScopeKeyRef.current !== requestScopeKey ||
          memoSaveRequestIdRef.current !== requestId
        ) {
          return
        }
        setMarkerMemos((current) => [
          saved,
          ...current.filter((memo) => memo.marker_key !== saved.marker_key),
        ])
        setSelectedMarkerKey(saved.marker_key)
        setMarkerMemoOpen(false)
      })
      .catch((err) => {
        if (
          currentMemoScopeKeyRef.current === requestScopeKey &&
          memoSaveRequestIdRef.current === requestId
        ) {
          setMemoError(getErrorMessage(err))
        }
      })
      .finally(() => {
        if (memoSaveRequestIdRef.current === requestId) {
          setMemoSaving(false)
        }
      })
  }

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>차트</h2>
        <p>Toss 보유 주식/ETF의 캔들, 거래량, 매매 판단 기록을 함께 봅니다.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {holdingsError && <div className="error">{holdingsError}</div>}
      {candlesError && <div className="error">{candlesError}</div>}
      {ordersError && <div className="error">{ordersError}</div>}
      {memoError && <div className="error">{memoError}</div>}

      <div className={`chart-panel-layout${memoListExpanded ? " memo-expanded" : ""}`}>
        <section className="panel chart-panel">
          <div className="section-heading chart-heading">
            <div>
              <h3>보유 종목 차트</h3>
              <span>{selectedAccount ? formatTossAccountLabel(selectedAccount) : "Toss 계좌"}</span>
            </div>
            <div className="section-heading-actions chart-heading-actions">
              <div aria-label="봉 선택" className="chart-period-toggle" role="group">
                {chartPeriodOptions.map((option) => (
                  <button
                    aria-label={option.label}
                    aria-pressed={selectedChartPeriod === option.value}
                    key={option.value}
                    onClick={() => setSelectedChartPeriod(option.value)}
                    title={option.label}
                    type="button"
                  >
                    {option.shortLabel}
                  </button>
                ))}
              </div>
              <label className="chart-symbol-select">
                <span>보유 종목</span>
                <select
                  value={selectedHoldingKey}
                  disabled={holdings.length === 0}
                  onChange={(event) => setSelectedHoldingKey(event.target.value)}
                >
                  {holdings.map((holding) => (
                    <option key={holdingKey(holding)} value={holdingKey(holding)}>
                      {holdingLabel(holding)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                aria-label="차트 설정 열기"
                className="icon-button chart-settings-toggle"
                onClick={() => setChartSettingsOpen(true)}
                title="차트 설정 열기"
                type="button"
              >
                <SettingsIcon size={17} />
              </button>
            </div>
          </div>

          <div className="candle-chart-area" aria-busy={chartFrameLoading}>
            <div aria-label={chartSummaryLabel} className="chart-symbol-summary">
              {latest && selectedHolding ? (
                <>
                  <strong>{selectedHolding.name}</strong>
                  <span>|</span>
                  <strong>{formatPrice(latest.close, selectedHolding.currency)}</strong>
                </>
              ) : (
                <>
                  <strong>{chartSummaryName}</strong>
                  <span>|</span>
                  <strong>{chartSummaryPrice}</strong>
                </>
              )}
            </div>
            <div
              className={`candle-chart-viewport${chartDragState ? " dragging" : ""}`}
              onClick={handleChartBlankClick}
              onMouseDown={handleChartMouseDown}
              onMouseLeave={handleChartMouseUp}
              onMouseMove={handleChartMouseMove}
              onMouseUp={handleChartMouseUp}
              onWheel={handleChartWheel}
            >
              {visibleChartCandles.length > 0 && selectedHolding ? (
                <CandleChart
                  candles={visibleChartCandles}
                  currency={selectedHolding.currency}
                  movingAverageSourceCandles={chartCandles}
                  movingAverageConfigs={movingAverageConfigs}
                  visibleCandleStartIndex={visibleCandleStartIndex}
                  markers={tradeMarkers}
                  selectedChartPeriod={selectedChartPeriod}
                  selectedMarkerKey={selectedMarkerKey}
                  showVolume={showVolume}
                  formatPrice={formatPrice}
                  onSelectMarker={selectMarker}
                />
              ) : (
                <svg
                  aria-label={chartFrameStatusMessage}
                  className="candle-chart-placeholder"
                  role="img"
                  viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                >
                  {[80, 180, 280, 380].map((y) => (
                    <line
                      className="candle-placeholder-line"
                      key={y}
                      x1={PLOT_LEFT}
                      x2={CHART_WIDTH - PLOT_RIGHT}
                      y1={y}
                      y2={y}
                    />
                  ))}
                  {Array.from({ length: 26 }, (_, index) => {
                    const x = PLOT_LEFT + index * 36
                    const height = 36 + (index % 5) * 18
                    return (
                      <rect
                        className="candle-placeholder-bar"
                        height={height}
                        key={index}
                        rx={2}
                        width={14}
                        x={x}
                        y={PRICE_BOTTOM_WITH_VOLUME - height}
                      />
                    )
                  })}
                </svg>
              )}
            </div>
            {visibleChartCandles.length === 0 && (
              <p className="chart-frame-status">{chartFrameStatusMessage}</p>
            )}
          </div>
        </section>

        <div className="marker-memo-drawer">
          <button
            aria-expanded={memoListExpanded}
            aria-label={memoListExpanded ? "작성된 판단 메모 접기" : "작성된 판단 메모 펼치기"}
            className="marker-memo-toggle"
            onClick={toggleMemoListExpanded}
            title={memoListExpanded ? "작성된 판단 메모 접기" : "작성된 판단 메모 펼치기"}
            type="button"
          >
            {memoListExpanded ? ">>" : "<<"}
          </button>
          {selectedMarker && (
            <button
              aria-label="선택한 매매 마커 판단 메모 작성"
              className="icon-button marker-memo-compose-button"
              onClick={openMarkerMemoDialog}
              title="선택한 매매 마커 판단 메모 작성"
              type="button"
            >
              <Plus size={17} />
            </button>
          )}
          {memoListExpanded && (
            <aside className="marker-memo-list-panel" aria-label="작성된 판단 메모">
              <div className="marker-memo-list-heading">
                <div>
                  <h4>작성된 판단 메모</h4>
                  <span>{memoMarkers.length.toLocaleString("ko-KR")}건</span>
                </div>
                <button
                  aria-label="작성된 판단 메모 관리"
                  aria-pressed={memoManageMode}
                  className={`secondary-button marker-memo-manage-button${memoManageMode ? " active" : ""}`}
                  onClick={() => setMemoManageMode((current) => !current)}
                  title={memoManageMode ? "삭제 모드 끄기" : "삭제 모드 켜기"}
                  type="button"
                >
                  관리
                </button>
              </div>
              {memoMarkers.length > 0 && selectedHolding ? (
                <div className="marker-memo-list">
                  {memoMarkers.map((marker) => (
                    <div
                      className={`marker-memo-list-item marker-memo-list-item-${marker.tone}${
                        selectedMarkerKey === marker.key ? " selected" : ""
                      }${memoManageMode ? " manage-mode" : ""}`}
                      key={marker.key}
                      onClick={() => openMarkerMemoDetail(marker)}
                      onKeyDown={(event) => handleMemoListItemKeyDown(event, marker)}
                      role="button"
                      tabIndex={0}
                    >
                      <span className="marker-memo-list-item-body">
                        <span className="marker-memo-list-item-header">
                          <span className={`marker-memo-list-badge marker-memo-list-badge-${marker.tone}`}>
                            {marker.label}
                          </span>
                          <time>{formatChartDateTime(marker.timestamp)}</time>
                        </span>
                        <strong>{formatPrice(marker.price, selectedHolding.currency)}</strong>
                        <span className="marker-memo-preview">{marker.memo.trim()}</span>
                      </span>
                      {memoManageMode && (
                        <button
                          aria-label={`${marker.label} 판단 메모 삭제`}
                          className="icon-button marker-memo-delete-button"
                          onClick={(event) => deleteMarkerMemo(event, marker)}
                          title="판단 메모 삭제"
                          type="button"
                        >
                          <X size={15} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-state compact-empty">작성된 판단 메모가 없습니다.</p>
              )}
            </aside>
          )}
        </div>
      </div>

      {chartSettingsOpen && (
        <ChartSettingsDialog
          movingAverageConfigs={movingAverageConfigs}
          movingAverageForm={movingAverageForm}
          showVolume={showVolume}
          onAddMovingAverage={addMovingAverage}
          onClose={() => setChartSettingsOpen(false)}
          onMovingAverageFormChange={setMovingAverageForm}
          onRemoveMovingAverage={removeMovingAverage}
          onShowVolumeChange={setShowVolume}
        />
      )}

      {markerMemoOpen && selectedMarker && (
        <MarkerMemoDialog
          selectedMarker={selectedMarker}
          currency={selectedHolding?.currency}
          markerMemoDraft={markerMemoDraft}
          memoSaving={memoSaving}
          formatPrice={formatPrice}
          onClose={() => setMarkerMemoOpen(false)}
          onDraftChange={setMarkerMemoDraft}
          onSave={saveMarkerMemo}
        />
      )}
    </section>
  )
}

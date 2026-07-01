import {
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type WheelEvent,
  useEffect,
  useMemo,
  useState,
} from "react"
import { Calendar, DollarSign, Hash, Plus, Save, StickyNote, Trash2 } from "lucide-react"
import { apiGet, apiPost } from "../api"
import { buildTradeMarkers, type TradeMarker } from "../chartMarkers"
import type { ChartMarkerMemo, TossAccount, TossCandle, TossHolding, TossOrder } from "../types"

const CHART_WIDTH = 1040
const CHART_HEIGHT = 500
const PRICE_TOP = 24
const PRICE_BOTTOM_WITH_VOLUME = 318
const PRICE_BOTTOM_WITHOUT_VOLUME = 442
const VOLUME_TOP = 360
const VOLUME_BOTTOM = 452
const PLOT_LEFT = 62
const PLOT_RIGHT = 28
const MIN_VISIBLE_CANDLES = 20
const ZOOM_IN_RATIO = 0.8
const ZOOM_OUT_RATIO = 1.25
const DRAG_PAN_STEP_PIXELS = 36

const chartPeriodOptions = [
  { value: "daily", label: "일봉" },
  { value: "weekly", label: "주봉" },
  { value: "annual", label: "연봉" },
] as const

type ChartPeriod = (typeof chartPeriodOptions)[number]["value"]

type MovingAverageConfig = {
  id: string
  days: number
  color: string
  lineWidth: number
}

type MovingAverageForm = {
  days: string
  color: string
  lineWidth: string
}

type ChartDragState = {
  lastX: number
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const accountLabel = (account: TossAccount) =>
  `${account.display_name} (${account.account_type})`

const holdingKey = (holding: TossHolding) => `${holding.market}:${holding.symbol}`

const holdingLabel = (holding: TossHolding) =>
  `${holding.symbol} · ${holding.name} · ${holding.market}`

const formatPrice = (value: number, currency: TossHolding["currency"] | undefined) =>
  `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}${currency ? ` ${currency}` : ""}`

const formatVolume = (value: number) =>
  value.toLocaleString("ko-KR", { maximumFractionDigits: 0 })

const parseDate = (value: string) => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const dateKey = (value: string) => {
  const parsed = parseDate(value)
  if (!parsed) {
    return value.slice(0, 10)
  }
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, "0")}-${String(
    parsed.getDate(),
  ).padStart(2, "0")}`
}

const formatDateLabel = (value: string) => {
  const parsed = parseDate(value)
  if (!parsed) {
    return value.slice(0, 10)
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
  }).format(parsed)
}

const formatDateTime = (value: string) => {
  const parsed = parseDate(value)
  if (!parsed) {
    return value
  }
  return parsed.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  })
}

const sortCandlesAscending = (candles: TossCandle[]) =>
  [...candles].sort((left, right) => {
    const leftDate = parseDate(left.timestamp)?.getTime() ?? 0
    const rightDate = parseDate(right.timestamp)?.getTime() ?? 0
    return leftDate - rightDate
  })

const weekGroupKey = (timestamp: string) => {
  const parsed = parseDate(timestamp)
  if (!parsed) {
    return timestamp.slice(0, 10)
  }
  const day = parsed.getDay() || 7
  const monday = new Date(parsed)
  monday.setDate(parsed.getDate() - day + 1)
  return dateKey(monday.toISOString())
}

const yearGroupKey = (timestamp: string) => {
  const parsed = parseDate(timestamp)
  return parsed ? String(parsed.getFullYear()) : timestamp.slice(0, 4)
}

const aggregateGroup = (group: TossCandle[]): TossCandle => {
  const first = group[0]
  const last = group[group.length - 1]
  return {
    symbol: first.symbol,
    timestamp: first.timestamp,
    open: first.open,
    high: Math.max(...group.map((candle) => candle.high)),
    low: Math.min(...group.map((candle) => candle.low)),
    close: last.close,
    volume: group.reduce((total, candle) => total + candle.volume, 0),
  }
}

const aggregateCandles = (candles: TossCandle[], selectedChartPeriod: ChartPeriod) => {
  const sorted = sortCandlesAscending(candles)
  if (selectedChartPeriod === "daily") {
    return sorted
  }

  const grouped = new Map<string, TossCandle[]>()
  for (const candle of sorted) {
    const key =
      selectedChartPeriod === "weekly" ? weekGroupKey(candle.timestamp) : yearGroupKey(candle.timestamp)
    const group = grouped.get(key)
    if (group) {
      group.push(candle)
    } else {
      grouped.set(key, [candle])
    }
  }
  return Array.from(grouped.values()).map(aggregateGroup)
}

const priceBounds = (
  candles: TossCandle[],
  movingAverageSeries: { value: number }[][],
  markers: TradeMarker[],
) => {
  const prices = [
    ...candles.flatMap((candle) => [candle.low, candle.high]),
    ...movingAverageSeries.flatMap((series) => series.map((point) => point.value)),
    ...markers.map((marker) => marker.price),
  ]
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const padding = Math.max((max - min) * 0.08, max * 0.01, 1)
  return { max: max + padding, min: Math.max(0, min - padding) }
}

const movingAveragePoints = (candles: TossCandle[], days: number) => {
  const points: { index: number; value: number }[] = []
  for (let index = days - 1; index < candles.length; index += 1) {
    const window = candles.slice(index - days + 1, index + 1)
    const value = window.reduce((total, candle) => total + candle.close, 0) / days
    points.push({ index, value })
  }
  return points
}

const markerIndex = (candles: TossCandle[], marker: TradeMarker) => {
  const markerTime = parseDate(marker.timestamp)?.getTime()
  const firstTime = parseDate(candles[0]?.timestamp ?? "")?.getTime()
  const lastTime = parseDate(candles[candles.length - 1]?.timestamp ?? "")?.getTime()
  if (
    markerTime !== undefined &&
    firstTime !== undefined &&
    lastTime !== undefined &&
    (markerTime < Math.min(firstTime, lastTime) || markerTime > Math.max(firstTime, lastTime))
  ) {
    return -1
  }

  const key = dateKey(marker.timestamp)
  const exact = candles.findIndex((candle) => dateKey(candle.timestamp) === key)
  if (exact >= 0) {
    return exact
  }
  if (markerTime === undefined) {
    return -1
  }
  let closestIndex = -1
  let closestDistance = Number.POSITIVE_INFINITY
  candles.forEach((candle, index) => {
    const candleTime = parseDate(candle.timestamp)?.getTime()
    if (candleTime === undefined) {
      return
    }
    const distance = Math.abs(candleTime - markerTime)
    if (distance < closestDistance) {
      closestDistance = distance
      closestIndex = index
    }
  })
  return closestIndex
}

function CandleChart({
  candles,
  currency,
  movingAverageSourceCandles,
  movingAverageConfigs,
  visibleCandleStartIndex,
  markers,
  selectedMarkerKey,
  showVolume,
  onSelectMarker,
}: {
  candles: TossCandle[]
  currency: TossHolding["currency"] | undefined
  movingAverageSourceCandles: TossCandle[]
  movingAverageConfigs: MovingAverageConfig[]
  visibleCandleStartIndex: number
  markers: TradeMarker[]
  selectedMarkerKey: string
  showVolume: boolean
  onSelectMarker: (marker: TradeMarker) => void
}) {
  const visibleCandleEndIndex = visibleCandleStartIndex + candles.length - 1
  const movingAverageSeries = movingAverageConfigs.map((config) =>
    movingAveragePoints(movingAverageSourceCandles, config.days)
      .filter(
        (point) =>
          point.index >= visibleCandleStartIndex && point.index <= visibleCandleEndIndex,
      )
      .map((point) => ({ ...point, index: point.index - visibleCandleStartIndex })),
  )
  const bounds = priceBounds(candles, movingAverageSeries, markers)
  const priceBottom = showVolume ? PRICE_BOTTOM_WITH_VOLUME : PRICE_BOTTOM_WITHOUT_VOLUME
  const priceRange = bounds.max - bounds.min || 1
  const plotWidth = CHART_WIDTH - PLOT_LEFT - PLOT_RIGHT
  const step = plotWidth / Math.max(candles.length, 1)
  const candleWidth = Math.max(1.2, Math.min(14, step * 0.55))
  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 1)
  const first = candles[0]
  const last = candles[candles.length - 1]
  const midPrice = (bounds.max + bounds.min) / 2

  const xForIndex = (index: number) => PLOT_LEFT + index * step + step / 2
  const yForPrice = (price: number) =>
    PRICE_TOP + ((bounds.max - price) / priceRange) * (priceBottom - PRICE_TOP)
  const volumeHeight = (volume: number) =>
    (volume / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP)
  const movingAveragePath = (series: { index: number; value: number }[]) =>
    series
      .map((point, index) => {
        const command = index === 0 ? "M" : "L"
        return `${command}${xForIndex(point.index).toFixed(2)},${yForPrice(point.value).toFixed(2)}`
      })
      .join(" ")

  const handleMarkerKeyDown = (event: KeyboardEvent<SVGGElement>, marker: TradeMarker) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onSelectMarker(marker)
    }
  }

  return (
    <svg className="candle-chart-svg" viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img">
      <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={PRICE_TOP} y2={PRICE_TOP} />
      <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={priceBottom} y2={priceBottom} />
      <line className="candle-axis muted" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={yForPrice(midPrice)} y2={yForPrice(midPrice)} />
      {showVolume && (
        <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={VOLUME_BOTTOM} y2={VOLUME_BOTTOM} />
      )}
      <text className="candle-axis-label" x={8} y={PRICE_TOP + 4}>
        {formatPrice(bounds.max, currency)}
      </text>
      <text className="candle-axis-label" x={8} y={yForPrice(midPrice) + 4}>
        {formatPrice(midPrice, currency)}
      </text>
      <text className="candle-axis-label" x={8} y={priceBottom + 4}>
        {formatPrice(bounds.min, currency)}
      </text>
      <text className="candle-date-label" x={PLOT_LEFT} y={CHART_HEIGHT - 10}>
        {formatDateLabel(first.timestamp)}
      </text>
      <text className="candle-date-label end" x={CHART_WIDTH - PLOT_RIGHT} y={CHART_HEIGHT - 10}>
        {formatDateLabel(last.timestamp)}
      </text>

      {candles.map((candle, index) => {
        const rising = candle.close >= candle.open
        const toneClass = rising ? "candle-up" : "candle-down"
        const x = xForIndex(index)
        const yOpen = yForPrice(candle.open)
        const yClose = yForPrice(candle.close)
        const yHigh = yForPrice(candle.high)
        const yLow = yForPrice(candle.low)
        const bodyTop = Math.min(yOpen, yClose)
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1)
        const barHeight = volumeHeight(candle.volume)

        return (
          <g key={`${candle.timestamp}:${index}`}>
            <line className={`candle-wick ${toneClass}`} x1={x} x2={x} y1={yHigh} y2={yLow} />
            <rect
              className={`candle-body ${toneClass}`}
              x={x - candleWidth / 2}
              y={bodyTop}
              width={candleWidth}
              height={bodyHeight}
              rx={1}
            />
            {showVolume && (
              <rect
                className={`candle-volume ${toneClass}`}
                x={x - candleWidth / 2}
                y={VOLUME_BOTTOM - barHeight}
                width={candleWidth}
                height={barHeight}
              />
            )}
          </g>
        )
      })}

      {movingAverageConfigs.map((config, index) => (
        <path
          className="moving-average-line"
          d={movingAveragePath(movingAverageSeries[index])}
          key={config.id}
          style={{ stroke: config.color, strokeWidth: config.lineWidth }}
        />
      ))}

      <g className="chart-markers">
        {markers.map((marker) => {
          const index = markerIndex(candles, marker)
          if (index < 0) {
            return null
          }
          const x = xForIndex(index)
          const y = yForPrice(marker.price)
          return (
            <g
              aria-label={`${marker.label} ${formatDateTime(marker.timestamp)} ${formatPrice(marker.price, currency)}`}
              className={`chart-marker chart-marker-${marker.tone} ${selectedMarkerKey === marker.key ? "selected" : ""}`}
              key={marker.key}
              onClick={() => onSelectMarker(marker)}
              onKeyDown={(event) => handleMarkerKeyDown(event, marker)}
              role="button"
              tabIndex={0}
            >
              <circle cx={x} cy={y} r={7} />
              <text x={x} y={y - 12}>
                {marker.label}
              </text>
              <title>
                {marker.label} · {formatDateTime(marker.timestamp)} · {formatPrice(marker.price, currency)}
              </title>
            </g>
          )
        })}
      </g>
    </svg>
  )
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
  const [selectedMarkerKey, setSelectedMarkerKey] = useState("")
  const [markerMemoDraft, setMarkerMemoDraft] = useState("")
  const [accountsError, setAccountsError] = useState("")
  const [holdingsError, setHoldingsError] = useState("")
  const [candlesError, setCandlesError] = useState("")
  const [ordersError, setOrdersError] = useState("")
  const [memoError, setMemoError] = useState("")
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [candlesLoading, setCandlesLoading] = useState(false)
  const [memoSaving, setMemoSaving] = useState(false)

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
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
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
    if (!selectedHolding || !selectedAccountSeq) {
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
    const totalCandles = chartCandles.length
    if (totalCandles === 0) {
      return { candles: chartCandles, startIndex: 0 }
    }

    const visibleCount =
      chartZoomWindow === null ? totalCandles : Math.min(chartZoomWindow, totalCandles)
    if (visibleCount >= totalCandles) {
      return { candles: chartCandles, startIndex: 0 }
    }

    const maxPanOffset = Math.max(totalCandles - visibleCount, 0)
    const clampedPanOffset = Math.min(Math.max(chartPanOffset, 0), maxPanOffset)
    const end = totalCandles - clampedPanOffset
    const start = Math.max(0, end - visibleCount)
    return { candles: chartCandles.slice(start, end), startIndex: start }
  }, [chartCandles, chartPanOffset, chartZoomWindow])
  const visibleChartCandles = visibleChartWindow.candles
  const visibleCandleStartIndex = visibleChartWindow.startIndex
  const tradeMarkers = useMemo(
    () => buildTradeMarkers(orders, markerMemos),
    [markerMemos, orders],
  )
  const selectedMarker = tradeMarkers.find((marker) => marker.key === selectedMarkerKey)
  const latest = visibleChartCandles[visibleChartCandles.length - 1]
  const chartEmptyMessage = holdingsLoading
    ? "보유 종목을 불러오는 중입니다."
    : candlesLoading
      ? "캔들 데이터를 불러오는 중입니다."
      : holdings.length === 0
        ? "선택한 Toss 계좌의 보유 종목이 없습니다."
        : "선택한 종목의 캔들 데이터가 없습니다."

  const handleChartWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (chartCandles.length === 0) {
      return
    }
    event.preventDefault()

    const totalCandles = chartCandles.length
    const currentWindow = chartZoomWindow ?? totalCandles
    const minWindow = Math.min(MIN_VISIBLE_CANDLES, totalCandles)
    const nextWindow =
      event.deltaY > 0
        ? Math.min(totalCandles, Math.ceil(currentWindow * ZOOM_OUT_RATIO))
        : Math.max(minWindow, Math.floor(currentWindow * ZOOM_IN_RATIO))

    if (nextWindow >= totalCandles) {
      setChartZoomWindow(null)
      setChartPanOffset(0)
      return
    }

    setChartZoomWindow(nextWindow)
    setChartPanOffset((current) => Math.min(current, Math.max(totalCandles - nextWindow, 0)))
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
    const visibleWindow = Math.min(chartZoomWindow ?? totalCandles, totalCandles)
    const maxPanOffset = Math.max(totalCandles - visibleWindow, 0)
    if (maxPanOffset === 0) {
      setChartDragState({ lastX: event.clientX })
      return
    }

    const deltaX = event.clientX - chartDragState.lastX
    const steps = Math.trunc(deltaX / DRAG_PAN_STEP_PIXELS)
    if (steps === 0) {
      return
    }

    setChartPanOffset((current) => Math.min(maxPanOffset, Math.max(0, current + steps)))
    setChartDragState({ lastX: chartDragState.lastX + steps * DRAG_PAN_STEP_PIXELS })
  }

  const handleChartMouseUp = () => {
    setChartDragState(null)
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

  const selectMarker = (marker: TradeMarker) => {
    setSelectedMarkerKey(marker.key)
    setMarkerMemoDraft(marker.memo)
    setMemoError("")
  }

  const saveMarkerMemo = () => {
    if (!selectedMarker || !selectedHolding || !selectedAccountSeq) {
      return
    }
    setMemoSaving(true)
    setMemoError("")
    apiPost<ChartMarkerMemo>("/api/toss/chart-marker-memos", {
      account_seq: selectedAccountSeq,
      symbol: selectedHolding.symbol,
      marker_key: selectedMarker.key,
      memo: markerMemoDraft,
    })
      .then((saved) => {
        setMarkerMemos((current) => [
          saved,
          ...current.filter((memo) => memo.marker_key !== saved.marker_key),
        ])
        setSelectedMarkerKey(saved.marker_key)
      })
      .catch((err) => setMemoError(getErrorMessage(err)))
      .finally(() => setMemoSaving(false))
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

      <section className="panel chart-panel">
        <div className="section-heading chart-heading">
          <div>
            <h3>보유 종목 차트</h3>
            <span>{selectedAccount ? accountLabel(selectedAccount) : "Toss 계좌"}</span>
          </div>
          <div className="section-heading-actions chart-heading-actions">
            <label className="chart-period-select">
              <span>봉</span>
              <select
                value={selectedChartPeriod}
                onChange={(event) => setSelectedChartPeriod(event.target.value as ChartPeriod)}
              >
                {chartPeriodOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
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
          </div>
        </div>

        {accounts.length === 0 && accountsLoaded ? (
          <p className="empty-state">Toss 계좌가 없습니다. 서버의 Toss API 인증 정보를 확인하세요.</p>
        ) : visibleChartCandles.length > 0 && selectedHolding ? (
          <div className="candle-chart-area">
            <div className="candle-summary-grid">
              <div>
                <span>종목</span>
                <strong>{holdingLabel(selectedHolding)}</strong>
              </div>
              <div>
                <span>종가</span>
                <strong>{formatPrice(latest.close, selectedHolding.currency)}</strong>
              </div>
              <div>
                <span>고가 / 저가</span>
                <strong>
                  {formatPrice(latest.high, selectedHolding.currency)} /{" "}
                  {formatPrice(latest.low, selectedHolding.currency)}
                </strong>
              </div>
              <div>
                <span>거래량</span>
                <strong>{formatVolume(latest.volume)}</strong>
              </div>
              <div>
                <span>표시 봉</span>
                <strong>{visibleChartCandles.length.toLocaleString("ko-KR")}개</strong>
              </div>
            </div>
            <div
              className={`candle-chart-viewport${chartDragState ? " dragging" : ""}`}
              onMouseDown={handleChartMouseDown}
              onMouseLeave={handleChartMouseUp}
              onMouseMove={handleChartMouseMove}
              onMouseUp={handleChartMouseUp}
              onWheel={handleChartWheel}
            >
              <CandleChart
                candles={visibleChartCandles}
                currency={selectedHolding.currency}
                movingAverageSourceCandles={chartCandles}
                movingAverageConfigs={movingAverageConfigs}
                visibleCandleStartIndex={visibleCandleStartIndex}
                markers={tradeMarkers}
                selectedMarkerKey={selectedMarkerKey}
                showVolume={showVolume}
                onSelectMarker={selectMarker}
              />
            </div>
          </div>
        ) : (
          <p className="empty-state">
            {accountsLoaded ? chartEmptyMessage : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
      </section>

      <section className="panel chart-settings-panel">
        <div className="section-heading">
          <h3>설정</h3>
          <span>{movingAverageConfigs.length.toLocaleString("ko-KR")}개 이동평균</span>
        </div>
        <div className="chart-settings-grid">
          <label className="checkbox-label">
            <input
              checked={showVolume}
              onChange={(event) => setShowVolume(event.target.checked)}
              type="checkbox"
            />
            거래량
          </label>
          <div className="moving-average-form">
            <label>
              일 수
              <input
                min={2}
                max={400}
                onChange={(event) =>
                  setMovingAverageForm((current) => ({ ...current, days: event.target.value }))
                }
                type="number"
                value={movingAverageForm.days}
              />
            </label>
            <label>
              색깔
              <input
                onChange={(event) =>
                  setMovingAverageForm((current) => ({ ...current, color: event.target.value }))
                }
                type="color"
                value={movingAverageForm.color}
              />
            </label>
            <label>
              선 굵기
              <input
                min={1}
                max={6}
                onChange={(event) =>
                  setMovingAverageForm((current) => ({
                    ...current,
                    lineWidth: event.target.value,
                  }))
                }
                type="number"
                value={movingAverageForm.lineWidth}
              />
            </label>
            <button className="secondary-button compact-button" onClick={addMovingAverage} type="button">
              <Plus size={16} />
              추가
            </button>
          </div>
        </div>
        {movingAverageConfigs.length > 0 && (
          <div className="moving-average-list">
            {movingAverageConfigs.map((config) => (
              <div className="moving-average-row" key={config.id}>
                <span className="moving-average-swatch" style={{ backgroundColor: config.color }} />
                <strong>{config.days}일 종가</strong>
                <span>{config.lineWidth}px</span>
                <button
                  aria-label={`${config.days}일 이동평균 삭제`}
                  className="icon-button"
                  onClick={() =>
                    setMovingAverageConfigs((current) =>
                      current.filter((item) => item.id !== config.id),
                    )
                  }
                  title={`${config.days}일 이동평균 삭제`}
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>매매 마커</h3>
          <span>{tradeMarkers.length.toLocaleString("ko-KR")}건</span>
        </div>
        {selectedMarker ? (
          <div className="marker-memo-panel">
            <div className={`marker-selected-header marker-selected-header-${selectedMarker.tone}`}>
              <div>
                <span className="marker-selected-badge">{selectedMarker.label}</span>
                <h4>{selectedMarker.label} 판단 기록</h4>
                <p>{formatDateTime(selectedMarker.timestamp)}</p>
              </div>
              <div className="marker-selected-price">
                <span>체결가</span>
                <strong>{formatPrice(selectedMarker.price, selectedHolding?.currency)}</strong>
              </div>
            </div>

            <div className="marker-detail-grid">
              <div className="marker-detail-item">
                <Calendar size={18} />
                <div>
                  <span>시점</span>
                  <strong>{formatDateTime(selectedMarker.timestamp)}</strong>
                </div>
              </div>
              <div className="marker-detail-item">
                <DollarSign size={18} />
                <div>
                  <span>가격</span>
                  <strong>{formatPrice(selectedMarker.price, selectedHolding?.currency)}</strong>
                </div>
              </div>
              <div className="marker-detail-item">
                <Hash size={18} />
                <div>
                  <span>수량</span>
                  <strong>{selectedMarker.quantity}</strong>
                </div>
              </div>
            </div>

            <label className="marker-note-field">
              <span>
                <StickyNote size={16} />
                판단 메모
              </span>
              <textarea
                onChange={(event) => setMarkerMemoDraft(event.target.value)}
                placeholder={`${selectedMarker.label} 판단 근거, 리스크, 다음 행동을 적어두세요.`}
                rows={4}
                value={markerMemoDraft}
              />
            </label>
            <div className="marker-note-actions">
              <span className="marker-note-state">
                {markerMemoDraft.trim() ? "메모 작성 중" : "메모 없음"}
              </span>
              <button
                className="primary-button compact-button"
                disabled={memoSaving}
                onClick={saveMarkerMemo}
                type="button"
              >
                <Save size={16} />
                저장
              </button>
            </div>
          </div>
        ) : (
          <p className="empty-state">
            {tradeMarkers.length > 0
              ? "차트의 매수, 추가매수, Trim 표시를 선택하세요."
              : "저장된 Toss 주문내역이 있으면 매수, 추가매수, Trim 표시가 나타납니다."}
          </p>
        )}
      </section>
    </section>
  )
}

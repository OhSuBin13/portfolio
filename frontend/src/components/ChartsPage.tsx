import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { TossAccount, TossCandle, TossHolding } from "../types"

const CHART_WIDTH = 960
const CHART_HEIGHT = 430
const PRICE_TOP = 22
const PRICE_BOTTOM = 288
const VOLUME_TOP = 328
const VOLUME_BOTTOM = 406
const PLOT_LEFT = 56
const PLOT_RIGHT = 24

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

const formatDateLabel = (value: string) => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value.slice(0, 10)
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
  }).format(parsed)
}

function priceBounds(candles: TossCandle[]) {
  const lows = candles.map((candle) => candle.low)
  const highs = candles.map((candle) => candle.high)
  const min = Math.min(...lows)
  const max = Math.max(...highs)
  const padding = Math.max((max - min) * 0.08, max * 0.01, 1)
  return { max: max + padding, min: Math.max(0, min - padding) }
}

function CandleChart({
  candles,
  currency,
}: {
  candles: TossCandle[]
  currency: TossHolding["currency"] | undefined
}) {
  const bounds = priceBounds(candles)
  const priceRange = bounds.max - bounds.min || 1
  const plotWidth = CHART_WIDTH - PLOT_LEFT - PLOT_RIGHT
  const step = plotWidth / Math.max(candles.length, 1)
  const candleWidth = Math.max(4, Math.min(18, step * 0.48))
  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 1)
  const first = candles[0]
  const last = candles[candles.length - 1]
  const midPrice = (bounds.max + bounds.min) / 2

  const xForIndex = (index: number) => PLOT_LEFT + index * step + step / 2
  const yForPrice = (price: number) =>
    PRICE_TOP + ((bounds.max - price) / priceRange) * (PRICE_BOTTOM - PRICE_TOP)
  const volumeHeight = (volume: number) =>
    (volume / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP)

  return (
    <svg className="candle-chart-svg" viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img">
      <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={PRICE_TOP} y2={PRICE_TOP} />
      <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={PRICE_BOTTOM} y2={PRICE_BOTTOM} />
      <line className="candle-axis muted" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={yForPrice(midPrice)} y2={yForPrice(midPrice)} />
      <line className="candle-axis" x1={PLOT_LEFT} x2={CHART_WIDTH - PLOT_RIGHT} y1={VOLUME_BOTTOM} y2={VOLUME_BOTTOM} />
      <text className="candle-axis-label" x={8} y={PRICE_TOP + 4}>
        {formatPrice(bounds.max, currency)}
      </text>
      <text className="candle-axis-label" x={8} y={yForPrice(midPrice) + 4}>
        {formatPrice(midPrice, currency)}
      </text>
      <text className="candle-axis-label" x={8} y={PRICE_BOTTOM + 4}>
        {formatPrice(bounds.min, currency)}
      </text>
      <text className="candle-date-label" x={PLOT_LEFT} y={CHART_HEIGHT - 8}>
        {formatDateLabel(first.timestamp)}
      </text>
      <text className="candle-date-label end" x={CHART_WIDTH - PLOT_RIGHT} y={CHART_HEIGHT - 8}>
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
            <rect
              className={`candle-volume ${toneClass}`}
              x={x - candleWidth / 2}
              y={VOLUME_BOTTOM - barHeight}
              width={candleWidth}
              height={barHeight}
            />
          </g>
        )
      })}
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
  const [accountsError, setAccountsError] = useState("")
  const [holdingsError, setHoldingsError] = useState("")
  const [candlesError, setCandlesError] = useState("")
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [candlesLoading, setCandlesLoading] = useState(false)

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
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        setHoldings([])
        setCandles([])
        setSelectedAccountSeq("")
        setSelectedHoldingKey("")
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      return
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
      setHoldingsError("")
      setCandlesError("")

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
    if (!selectedHolding) {
      return
    }

    let ignore = false

    void Promise.resolve().then(() => {
      if (ignore) {
        return
      }

      setCandlesLoading(true)
      setCandles([])
      setCandlesError("")

      apiGet<TossCandle[]>(
        `/api/toss/candles?symbol=${encodeURIComponent(selectedHolding.symbol)}&interval=1d&limit=120`,
      )
        .then((candleData) => {
          if (ignore) {
            return
          }

          setCandles(candleData)
          setCandlesError("")
        })
        .catch((err) => {
          if (ignore) {
            return
          }

          setCandles([])
          setCandlesError(getErrorMessage(err))
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
  }, [selectedHolding])

  const latest = candles[candles.length - 1]
  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)
  const chartEmptyMessage = holdingsLoading
    ? "보유 종목을 불러오는 중입니다."
    : candlesLoading
      ? "캔들 데이터를 불러오는 중입니다."
      : holdings.length === 0
        ? "선택한 Toss 계좌의 보유 종목이 없습니다."
        : "선택한 종목의 캔들 데이터가 없습니다."

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>차트</h2>
        <p>Toss 보유 주식/ETF의 일봉 OHLCV를 확인합니다.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {holdingsError && <div className="error">{holdingsError}</div>}
      {candlesError && <div className="error">{candlesError}</div>}

      <section className="panel chart-panel">
        <div className="section-heading chart-heading">
          <div>
            <h3>보유 종목 차트</h3>
            <span>{selectedAccount ? accountLabel(selectedAccount) : "Toss 계좌"}</span>
          </div>
          <div className="section-heading-actions chart-heading-actions">
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
        ) : candles.length > 0 && selectedHolding ? (
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
            </div>
            <CandleChart candles={candles} currency={selectedHolding.currency} />
          </div>
        ) : (
          <p className="empty-state">
            {accountsLoaded ? chartEmptyMessage : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
      </section>
    </section>
  )
}

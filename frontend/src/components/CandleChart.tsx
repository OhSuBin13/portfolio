import {
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  useState,
} from "react"
import {
  formatChartDateLabel,
  formatChartDateTime,
  type ChartPeriod,
} from "../chartDates"
import { spreadOverlappingMarkers, type TradeMarker } from "../chartMarkers"
import {
  changeRateForPrice,
  changeRateTone,
  formatChangeRate,
  markerIndex,
  movingAveragePoints,
  priceBounds,
} from "../chartSeries"
import type { TossCandle, TossHolding } from "../types"

export const CHART_WIDTH = 1040
export const CHART_HEIGHT = 500
export const PRICE_TOP = 24
export const PRICE_BOTTOM_WITH_VOLUME = 318
export const PRICE_BOTTOM_WITHOUT_VOLUME = 442
export const VOLUME_TOP = 360
export const VOLUME_BOTTOM = 452
export const PLOT_LEFT = 62
export const PLOT_RIGHT = 28

type OhlcChangeRates = {
  open: number | null
  high: number | null
  low: number | null
  close: number | null
}

export type MovingAverageConfig = {
  id: string
  days: number
  color: string
  lineWidth: number
}

type ChartHoverState = {
  x: number
  y: number
  price: number
  candle: TossCandle
  previousClose: number | null
  changeRates: OhlcChangeRates
}

type ChartPriceFormatter = (
  value: number,
  currency: TossHolding["currency"] | undefined,
) => string

type CandleChartProps = {
  candles: TossCandle[]
  currency: TossHolding["currency"] | undefined
  movingAverageSourceCandles: TossCandle[]
  movingAverageConfigs: MovingAverageConfig[]
  visibleCandleStartIndex: number
  markers: TradeMarker[]
  selectedChartPeriod: ChartPeriod
  selectedMarkerKey: string
  showVolume: boolean
  formatPrice: ChartPriceFormatter
  onSelectMarker: (marker: TradeMarker) => void
}

export function CandleChart({
  candles,
  currency,
  movingAverageSourceCandles,
  movingAverageConfigs,
  visibleCandleStartIndex,
  markers,
  selectedChartPeriod,
  selectedMarkerKey,
  showVolume,
  formatPrice,
  onSelectMarker,
}: CandleChartProps) {
  const visibleCandleEndIndex = visibleCandleStartIndex + candles.length - 1
  const movingAverageSeries = movingAverageConfigs.map((config) =>
    movingAveragePoints(movingAverageSourceCandles, config.days)
      .filter(
        (point) =>
          point.index >= visibleCandleStartIndex && point.index <= visibleCandleEndIndex,
      )
      .map((point) => ({ ...point, index: point.index - visibleCandleStartIndex })),
  )
  const markerPlacementInputs = markers.flatMap((marker) => {
    const candleIndex = markerIndex(candles, marker)
    return candleIndex >= 0 ? [{ marker, candleIndex }] : []
  })
  const visibleMarkers = markerPlacementInputs.map(({ marker }) => marker)
  const bounds = priceBounds(candles, movingAverageSeries, visibleMarkers)
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
  const markerPlacements = spreadOverlappingMarkers(markerPlacementInputs)
  const [chartHoverState, setChartHoverState] = useState<ChartHoverState | null>(null)

  const handleChartHoverMove = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (candles.length === 0) {
      return
    }
    const boundsRect = event.currentTarget.getBoundingClientRect()
    const svgX = ((event.clientX - boundsRect.left) / boundsRect.width) * CHART_WIDTH
    const svgY = ((event.clientY - boundsRect.top) / boundsRect.height) * CHART_HEIGHT
    const clampedX = Math.min(Math.max(svgX, PLOT_LEFT), CHART_WIDTH - PLOT_RIGHT)
    const hoverCandleIndex = Math.min(
      candles.length - 1,
      Math.max(0, Math.round((clampedX - PLOT_LEFT - step / 2) / step)),
    )
    const hoverCandle = candles[hoverCandleIndex]
    const previousCandle = candles[hoverCandleIndex - 1]
    const previousClose = previousCandle?.close ?? null
    const changeRates = {
      open: changeRateForPrice(hoverCandle.open, previousClose),
      high: changeRateForPrice(hoverCandle.high, previousClose),
      low: changeRateForPrice(hoverCandle.low, previousClose),
      close: changeRateForPrice(hoverCandle.close, previousClose),
    }
    const y = Math.min(Math.max(svgY, PRICE_TOP), priceBottom)
    const price = bounds.max - ((y - PRICE_TOP) / (priceBottom - PRICE_TOP)) * priceRange
    setChartHoverState({
      x: xForIndex(hoverCandleIndex),
      y,
      price,
      candle: hoverCandle,
      previousClose,
      changeRates,
    })
  }

  const handleChartHoverLeave = () => {
    setChartHoverState(null)
  }

  const handleMarkerKeyDown = (event: KeyboardEvent<SVGGElement>, marker: TradeMarker) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onSelectMarker(marker)
    }
  }

  return (
    <svg
      className="candle-chart-svg"
      onMouseLeave={handleChartHoverLeave}
      onMouseMove={handleChartHoverMove}
      role="img"
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
    >
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
        {formatChartDateLabel(first.timestamp, selectedChartPeriod)}
      </text>
      <text className="candle-date-label end" x={CHART_WIDTH - PLOT_RIGHT} y={CHART_HEIGHT - 10}>
        {formatChartDateLabel(last.timestamp, selectedChartPeriod)}
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

      {chartHoverState && (
        <g className="chart-hover-guides">
          <line
            className="chart-hover-price-line"
            x1={PLOT_LEFT}
            x2={CHART_WIDTH - PLOT_RIGHT}
            y1={chartHoverState.y}
            y2={chartHoverState.y}
          />
          <line
            className="chart-hover-vertical-line"
            x1={chartHoverState.x}
            x2={chartHoverState.x}
            y1={PRICE_TOP}
            y2={showVolume ? VOLUME_BOTTOM : priceBottom}
          />
          <rect
            className="chart-hover-price-bg"
            height={22}
            rx={4}
            width={104}
            x={4}
            y={chartHoverState.y - 11}
          />
          <text
            className="chart-hover-price-label"
            x={56}
            y={chartHoverState.y + 4}
          >
            {formatPrice(chartHoverState.price, currency)}
          </text>
          <rect
            className="chart-hover-date-bg"
            height={20}
            rx={4}
            width={74}
            x={chartHoverState.x - 37}
            y={(showVolume ? VOLUME_BOTTOM : priceBottom) + 5}
          />
          <text
            className="chart-hover-date-label"
            x={chartHoverState.x}
            y={(showVolume ? VOLUME_BOTTOM : priceBottom) + 19}
          >
            {formatChartDateLabel(chartHoverState.candle.timestamp, selectedChartPeriod)}
          </text>
          <g className="chart-hover-ohlc-panel">
            <rect
              className="chart-hover-ohlc-bg"
              height={44}
              rx={6}
              width={504}
              x={4}
              y={PRICE_TOP + 8}
            />
            <text className="chart-hover-ohlc-values" x={10} y={PRICE_TOP + 25}>
              <tspan>시작 {formatPrice(chartHoverState.candle.open, currency)} </tspan>
              <tspan className={`chart-hover-change-rate chart-hover-change-${changeRateTone(chartHoverState.changeRates.open)}`}>
                ({formatChangeRate(chartHoverState.changeRates.open)})
              </tspan>
              <tspan> · 고가{" "}</tspan>
              <tspan>{formatPrice(chartHoverState.candle.high, currency)} </tspan>
              <tspan className={`chart-hover-change-rate chart-hover-change-${changeRateTone(chartHoverState.changeRates.high)}`}>
                ({formatChangeRate(chartHoverState.changeRates.high)})
              </tspan>
            </text>
            <text className="chart-hover-ohlc-values" x={10} y={PRICE_TOP + 43}>
              <tspan>저가{" "}</tspan>
              <tspan>{formatPrice(chartHoverState.candle.low, currency)} </tspan>
              <tspan className={`chart-hover-change-rate chart-hover-change-${changeRateTone(chartHoverState.changeRates.low)}`}>
                ({formatChangeRate(chartHoverState.changeRates.low)})
              </tspan>
              <tspan> · 종가{" "}</tspan>
              <tspan>{formatPrice(chartHoverState.candle.close, currency)} </tspan>
              <tspan className={`chart-hover-change-rate chart-hover-change-${changeRateTone(chartHoverState.changeRates.close)}`}>
                ({formatChangeRate(chartHoverState.changeRates.close)})
              </tspan>
            </text>
          </g>
        </g>
      )}

      <g className="chart-markers">
        {markerPlacements.map(({ marker, candleIndex, xOffset }) => {
          const x = xForIndex(candleIndex) + xOffset
          const y = yForPrice(marker.price)
          return (
            <g
              aria-label={`${marker.label} ${formatChartDateTime(marker.timestamp)} ${formatPrice(marker.price, currency)}`}
              className={`chart-marker chart-marker-${marker.tone} ${selectedMarkerKey === marker.key ? "selected" : ""}`}
              key={marker.key}
              onClick={(event) => {
                event.stopPropagation()
                onSelectMarker(marker)
              }}
              onKeyDown={(event) => handleMarkerKeyDown(event, marker)}
              role="button"
              tabIndex={0}
            >
              <circle cx={x} cy={y} r={7} />
              <text x={x} y={y - 12}>
                {marker.label}
              </text>
              <title>
                {marker.label} · {formatChartDateTime(marker.timestamp)} · {formatPrice(marker.price, currency)}
              </title>
            </g>
          )
        })}
      </g>
    </svg>
  )
}

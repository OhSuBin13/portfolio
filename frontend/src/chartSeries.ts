import {
  chartDateKey,
  chartPeriodGroupKey,
  parseChartDate,
  type ChartPeriod,
} from "./chartDates"
import type { TradeMarker } from "./chartMarkers"
import type { TossCandle } from "./types"

export type ChangeRateTone = "up" | "down" | "flat"

export const formatChangeRate = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) {
    return "-"
  }
  const formatted = Math.abs(value).toLocaleString("ko-KR", {
    maximumFractionDigits: 2,
  })
  if (value > 0) {
    return `+${formatted}%`
  }
  if (value < 0) {
    return `-${formatted}%`
  }
  return "0%"
}

export const changeRateTone = (value: number | null): ChangeRateTone => {
  if (value === null || !Number.isFinite(value) || value === 0) {
    return "flat"
  }
  return value > 0 ? "up" : "down"
}

export const changeRateForPrice = (value: number, previousClose: number | null) =>
  previousClose !== null && previousClose > 0 ? ((value - previousClose) / previousClose) * 100 : null

export const sortCandlesAscending = (candles: TossCandle[]) =>
  [...candles].sort((left, right) => {
    const leftDate = parseChartDate(left.timestamp)?.getTime() ?? 0
    const rightDate = parseChartDate(right.timestamp)?.getTime() ?? 0
    return leftDate - rightDate
  })

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

export const aggregateCandles = (candles: TossCandle[], selectedChartPeriod: ChartPeriod) => {
  const sorted = sortCandlesAscending(candles)
  if (selectedChartPeriod === "daily") {
    return sorted
  }

  const grouped = new Map<string, TossCandle[]>()
  for (const candle of sorted) {
    const key = chartPeriodGroupKey(candle.timestamp, selectedChartPeriod)
    const group = grouped.get(key)
    if (group) {
      group.push(candle)
    } else {
      grouped.set(key, [candle])
    }
  }
  return Array.from(grouped.values()).map(aggregateGroup)
}

export const priceBounds = (
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

export const movingAveragePoints = (candles: TossCandle[], days: number) => {
  const points: { index: number; value: number }[] = []
  for (let index = days - 1; index < candles.length; index += 1) {
    const window = candles.slice(index - days + 1, index + 1)
    const value = window.reduce((total, candle) => total + candle.close, 0) / days
    points.push({ index, value })
  }
  return points
}

export const markerIndex = (candles: TossCandle[], marker: TradeMarker) => {
  const key = chartDateKey(marker.timestamp)
  const exact = candles.findIndex((candle) => chartDateKey(candle.timestamp) === key)
  if (exact >= 0) {
    return exact
  }

  const markerTime = parseChartDate(marker.timestamp)?.getTime()
  const firstTime = parseChartDate(candles[0]?.timestamp ?? "")?.getTime()
  const lastTime = parseChartDate(candles[candles.length - 1]?.timestamp ?? "")?.getTime()
  if (
    markerTime !== undefined &&
    firstTime !== undefined &&
    lastTime !== undefined &&
    (markerTime < Math.min(firstTime, lastTime) || markerTime > Math.max(firstTime, lastTime))
  ) {
    return -1
  }

  if (markerTime === undefined) {
    return -1
  }
  let closestIndex = -1
  let closestDistance = Number.POSITIVE_INFINITY
  candles.forEach((candle, index) => {
    const candleTime = parseChartDate(candle.timestamp)?.getTime()
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

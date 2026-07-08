export const MIN_VISIBLE_CANDLES = 20
export const ZOOM_IN_RATIO = 0.8
export const ZOOM_OUT_RATIO = 1.25
export const DRAG_PAN_STEP_PIXELS = 36

export type VisibleChartWindow<T> = {
  candles: T[]
  startIndex: number
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max)

export const visibleChartWindowSize = (
  totalCandles: number,
  chartZoomWindow: number | null,
) => Math.min(chartZoomWindow ?? totalCandles, totalCandles)

export const maxChartPanOffset = (totalCandles: number, visibleWindow: number) =>
  Math.max(totalCandles - visibleWindow, 0)

export function buildVisibleChartWindow<T>(
  chartCandles: T[],
  chartZoomWindow: number | null,
  chartPanOffset: number,
): VisibleChartWindow<T> {
  const totalCandles = chartCandles.length
  if (totalCandles === 0) {
    return { candles: chartCandles, startIndex: 0 }
  }

  const visibleCount = visibleChartWindowSize(totalCandles, chartZoomWindow)
  if (visibleCount >= totalCandles) {
    return { candles: chartCandles, startIndex: 0 }
  }

  const clampedPanOffset = clamp(
    chartPanOffset,
    0,
    maxChartPanOffset(totalCandles, visibleCount),
  )
  const end = totalCandles - clampedPanOffset
  const start = Math.max(0, end - visibleCount)
  return { candles: chartCandles.slice(start, end), startIndex: start }
}

export function nextChartZoom(
  totalCandles: number,
  currentZoomWindow: number | null,
  currentPanOffset: number,
  zoomOut: boolean,
) {
  if (totalCandles <= 0) {
    return { zoomWindow: currentZoomWindow, panOffset: currentPanOffset }
  }

  const currentWindow = currentZoomWindow ?? totalCandles
  const minWindow = Math.min(MIN_VISIBLE_CANDLES, totalCandles)
  const nextWindow = zoomOut
    ? Math.min(totalCandles, Math.ceil(currentWindow * ZOOM_OUT_RATIO))
    : Math.max(minWindow, Math.floor(currentWindow * ZOOM_IN_RATIO))

  if (nextWindow >= totalCandles) {
    return { zoomWindow: null, panOffset: 0 }
  }

  return {
    zoomWindow: nextWindow,
    panOffset: clamp(currentPanOffset, 0, maxChartPanOffset(totalCandles, nextWindow)),
  }
}

export const chartPanSteps = (deltaX: number) =>
  Math.trunc(deltaX / DRAG_PAN_STEP_PIXELS)

export const nextChartPanOffset = (
  currentPanOffset: number,
  steps: number,
  totalCandles: number,
  visibleWindow: number,
) => clamp(
  currentPanOffset + steps,
  0,
  maxChartPanOffset(totalCandles, visibleWindow),
)

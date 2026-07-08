import type { AssetAllocation } from "./types"

export type AllocationSegment = {
  color: string
  key: string
  label: string
  value: number
}

export type AllocationCallout = AllocationSegment & {
  linePoints: string
  path: string
  percentY: number
  textAnchor: "start" | "end"
  textX: number
  textY: number
}

const allocationColors = {
  cash: "#10b981",
  other: "#f59e0b",
  stock_etf: "#2563eb",
}
const stockAllocationColors = ["#2563eb", "#0f766e", "#7c3aed", "#dc2626", "#9333ea", "#0891b2"]
const cashLikeAssetTypes = new Set(["cash", "savings"])

export const pieChart = {
  centerX: 180,
  centerY: 132,
  height: 264,
  labelInset: 18,
  labelMaxY: 238,
  labelMinY: 26,
  radius: 92,
  width: 360,
}

const positivePercent = (value: number | undefined) => {
  if (value === undefined || !Number.isFinite(value) || value <= 0) {
    return 0
  }

  return value
}

const roundPercent = (value: number) => Math.round(value * 100) / 100
const svgNumber = (value: number) => Number(value.toFixed(2))
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const normalizeAllocationSegments = (segments: AllocationSegment[]) => {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  if (total <= 0) {
    return []
  }

  return segments
    .map((segment) => ({
      ...segment,
      value: roundPercent((segment.value / total) * 100),
    }))
    .filter((segment) => segment.key !== "other" || segment.value > 0)
}

const getFallbackAllocationSegments = (assetMix: Record<string, number>) => {
  const stockEtf = positivePercent(assetMix.stock_etf)
  let cash = 0
  let other = 0

  for (const [type, value] of Object.entries(assetMix)) {
    if (type === "stock_etf") {
      continue
    }

    if (cashLikeAssetTypes.has(type)) {
      cash += positivePercent(value)
      continue
    }

    other += positivePercent(value)
  }

  return normalizeAllocationSegments([
    { color: allocationColors.stock_etf, key: "stock_etf", label: "주식/ETF", value: stockEtf },
    { color: allocationColors.cash, key: "cash", label: "현금", value: cash },
    { color: allocationColors.other, key: "other", label: "기타", value: other },
  ])
}

export const getAllocationSegments = (
  assetMix: Record<string, number>,
  assetAllocations: AssetAllocation[],
) => {
  if (assetAllocations.length === 0) {
    return getFallbackAllocationSegments(assetMix)
  }

  const stockSegments = assetAllocations.map((allocation, index) => ({
    color: stockAllocationColors[index % stockAllocationColors.length],
    key: allocation.asset_key,
    label: allocation.symbol || allocation.name,
    value: positivePercent(allocation.percent),
  }))
  const cashSegment = {
    color: allocationColors.cash,
    key: "cash",
    label: "현금",
    value: positivePercent(assetMix.cash),
  }
  const otherSegment = {
    color: allocationColors.other,
    key: "other",
    label: "기타",
    value: Object.entries(assetMix)
      .filter(([type]) => type !== "stock_etf" && type !== "cash")
      .reduce((sum, [, value]) => sum + positivePercent(value), 0),
  }

  return normalizeAllocationSegments([...stockSegments, cashSegment, otherSegment])
}

const pointOnPie = (percent: number, radius: number) => {
  const angle = (percent * 3.6 - 90) * (Math.PI / 180)
  return {
    x: svgNumber(pieChart.centerX + radius * Math.cos(angle)),
    y: svgNumber(pieChart.centerY + radius * Math.sin(angle)),
  }
}

const getPieSlicePath = (startPercent: number, endPercent: number) => {
  const span = Math.max(0, endPercent - startPercent)
  if (span >= 99.999) {
    return [
      `M ${pieChart.centerX} ${pieChart.centerY}`,
      `m -${pieChart.radius} 0`,
      `a ${pieChart.radius} ${pieChart.radius} 0 1 0 ${pieChart.radius * 2} 0`,
      `a ${pieChart.radius} ${pieChart.radius} 0 1 0 -${pieChart.radius * 2} 0`,
    ].join(" ")
  }

  const start = pointOnPie(startPercent, pieChart.radius)
  const end = pointOnPie(endPercent, pieChart.radius)
  const largeArcFlag = span > 50 ? 1 : 0
  return [
    `M ${pieChart.centerX} ${pieChart.centerY}`,
    `L ${start.x} ${start.y}`,
    `A ${pieChart.radius} ${pieChart.radius} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`,
    "Z",
  ].join(" ")
}

const distributeCalloutY = (values: Array<{ key: string; rawY: number }>) => {
  const minGap = 21
  const sorted = [...values].sort((first, second) => first.rawY - second.rawY)
  let previousY = pieChart.labelMinY - minGap
  const rows = sorted.map((row) => {
    const textY = Math.max(row.rawY, previousY + minGap)
    previousY = textY
    return { ...row, textY }
  })
  const overflow = rows.length > 0 ? rows[rows.length - 1].textY - pieChart.labelMaxY : 0
  const shift = Math.max(0, overflow)
  const positions = new Map<string, number>()

  for (const row of rows) {
    positions.set(row.key, clamp(row.textY - shift, pieChart.labelMinY, pieChart.labelMaxY))
  }

  return positions
}

export const getAllocationCallouts = (segments: AllocationSegment[]) => {
  let cursor = 0
  const rawCallouts = segments.map((segment) => {
    const start = cursor
    const end = Math.min(100, cursor + positivePercent(segment.value))
    cursor = end
    const middle = start + (end - start) / 2
    const anchor = pointOnPie(middle, pieChart.radius * 0.95)
    const side = anchor.x >= pieChart.centerX ? "right" : "left"
    const rawY = clamp(pointOnPie(middle, pieChart.radius + 32).y, pieChart.labelMinY, pieChart.labelMaxY)

    return {
      ...segment,
      anchor,
      end,
      path: getPieSlicePath(start, end),
      rawY,
      side,
      start,
    }
  })
  const rightY = distributeCalloutY(
    rawCallouts.filter((callout) => callout.side === "right").map((callout) => callout),
  )
  const leftY = distributeCalloutY(
    rawCallouts.filter((callout) => callout.side === "left").map((callout) => callout),
  )

  return rawCallouts.map((callout): AllocationCallout => {
    const isRight = callout.side === "right"
    const textX = isRight ? pieChart.width - pieChart.labelInset : pieChart.labelInset
    const textY = (isRight ? rightY : leftY).get(callout.key) ?? callout.rawY
    const lineEndX = isRight ? textX - 6 : textX + 6
    const elbowX = isRight
      ? Math.max(pieChart.centerX + pieChart.radius + 8, lineEndX - 46)
      : Math.min(pieChart.centerX - pieChart.radius - 8, lineEndX + 46)
    const linePoints = [
      `${callout.anchor.x},${callout.anchor.y}`,
      `${svgNumber(elbowX)},${svgNumber(textY)}`,
      `${svgNumber(lineEndX)},${svgNumber(textY)}`,
    ].join(" ")

    return {
      color: callout.color,
      key: callout.key,
      label: callout.label,
      linePoints,
      path: callout.path,
      percentY: svgNumber(textY + 13),
      textAnchor: isRight ? "end" : "start",
      textX,
      textY: svgNumber(textY),
      value: callout.value,
    }
  })
}

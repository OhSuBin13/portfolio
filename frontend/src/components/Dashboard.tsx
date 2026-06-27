import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { AssetAllocation, PortfolioSummary } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  usd_krw_rate: null,
  usd_krw_change_percent: null,
  asset_mix: {},
  asset_allocations: [],
  goal_progress: [],
}

type DisplayCurrency = "KRW" | "USD"
type AllocationSegment = {
  color: string
  key: string
  label: string
  value: number
}
type AllocationCallout = AllocationSegment & {
  linePoints: string
  path: string
  percentY: number
  textAnchor: "start" | "end"
  textX: number
  textY: number
}

const displayCurrencies: DisplayCurrency[] = ["KRW", "USD"]
const allocationColors = {
  cash: "#10b981",
  other: "#f59e0b",
  stock_etf: "#2563eb",
}
const stockAllocationColors = ["#2563eb", "#0f766e", "#7c3aed", "#dc2626", "#9333ea", "#0891b2"]
const cashLikeAssetTypes = new Set(["cash", "savings"])
const pieChart = {
  centerX: 180,
  centerY: 132,
  height: 264,
  labelInset: 18,
  labelMaxY: 238,
  labelMinY: 26,
  radius: 92,
  width: 360,
}
const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))
const formatCurrency = (valueKrw: number, currency: DisplayCurrency, usdKrwRate: number | null) => {
  if (currency === "USD") {
    if (usdKrwRate === null || !Number.isFinite(usdKrwRate) || usdKrwRate <= 0) {
      return "환율 없음"
    }
    return (valueKrw / usdKrwRate).toLocaleString("en-US", {
      currency: "USD",
      maximumFractionDigits: 2,
      style: "currency",
    })
  }

  return `${valueKrw.toLocaleString("ko-KR", { maximumFractionDigits: 0 })} 원`
}
const goalTypeLabel = (type: string) => (type === "monthly_income" ? "월 배당/소득" : "순자산")
const assetTypeLabel = (type: string) =>
  (
    {
      cash: "현금",
      debt: "부채",
      savings: "예금",
      stock_etf: "주식/ETF",
    } as Record<string, string>
  )[type] ?? type
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
const getAllocationSegments = (assetMix: Record<string, number>, assetAllocations: AssetAllocation[]) => {
  if (assetAllocations.length === 0) {
    return getFallbackAllocationSegments(assetMix)
  }

  const stockSegments = assetAllocations
    .filter((allocation) => allocation.asset_type === "stock_etf")
    .map((allocation, index) => ({
      color: stockAllocationColors[index % stockAllocationColors.length],
      key: `stock_etf:${allocation.asset_id}`,
      label: allocation.symbol ?? allocation.name,
      value: positivePercent(allocation.percent),
    }))
  const cash = assetAllocations
    .filter((allocation) => cashLikeAssetTypes.has(allocation.asset_type))
    .reduce((sum, allocation) => sum + positivePercent(allocation.percent), 0)
  const other = assetAllocations
    .filter(
      (allocation) =>
        allocation.asset_type !== "stock_etf" && !cashLikeAssetTypes.has(allocation.asset_type),
    )
    .reduce((sum, allocation) => sum + positivePercent(allocation.percent), 0)

  return normalizeAllocationSegments([
    ...stockSegments,
    { color: allocationColors.cash, key: "cash", label: "현금", value: cash },
    { color: allocationColors.other, key: "other", label: "기타", value: other },
  ])
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
const getAllocationCallouts = (segments: AllocationSegment[]) => {
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

export function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [error, setError] = useState("")
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>("KRW")

  useEffect(() => {
    apiGet<PortfolioSummary>("/api/summary")
      .then((summaryData) => {
        setSummary(summaryData)
        setError("")
      })
      .catch((err) => setError(getErrorMessage(err)))
  }, [])

  const goalProgress = summary.goal_progress
  const assetMixEntries = Object.entries(summary.asset_mix)
  const allocationSegments = getAllocationSegments(summary.asset_mix, summary.asset_allocations)
  const visibleAllocationSegments = allocationSegments.filter((segment) => segment.value > 0)
  const allocationCallouts = getAllocationCallouts(visibleAllocationSegments)

  return (
    <section className="screen-stack">
      <header className="page-header dashboard-header">
        <div>
          <h2>오늘의 자산</h2>
          <p>순자산, 목표, 자산 비중, 최근 변화를 확인합니다.</p>
          {summary.usd_krw_rate !== null && (
            <p className="fx-rate-line">
              <span>USD/KRW {summary.usd_krw_rate.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원</span>
            </p>
          )}
        </div>
        <div className="currency-toggle" aria-label="표시 통화 선택">
          {displayCurrencies.map((currency) => (
            <button
              aria-pressed={displayCurrency === currency}
              className={displayCurrency === currency ? "active" : ""}
              key={currency}
              onClick={() => setDisplayCurrency(currency)}
              type="button"
            >
              {currency}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="error">{error}</div>}
      {displayCurrency === "USD" && summary.usd_krw_rate === null && (
        <p className="form-message error-text">
          USD 환산 환율이 없습니다. Toss API 인증 정보를 설정한 뒤 자동 갱신 상태를 확인하세요.
        </p>
      )}

      <div className="summary-grid">
        <article className="panel hero-panel">
          <span>순자산</span>
          <strong>{formatCurrency(summary.net_worth_krw, displayCurrency, summary.usd_krw_rate)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>월 배당/소득</span>
          <strong>{formatCurrency(summary.monthly_income_krw, displayCurrency, summary.usd_krw_rate)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>총자산</span>
          <strong>{formatCurrency(summary.gross_assets_krw, displayCurrency, summary.usd_krw_rate)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>부채</span>
          <strong>{formatCurrency(summary.debt_krw, displayCurrency, summary.usd_krw_rate)}</strong>
        </article>
      </div>

      <section className="panel">
        <div className="section-heading">
          <h3>목표 진행</h3>
          <span>{goalProgress.length.toLocaleString("ko-KR")}개 목표</span>
        </div>
        {goalProgress.length > 0 ? (
          <div className="progress-list">
            {goalProgress.map((row) => (
              <div className="progress-row" key={row.goal.id}>
                <div className="progress-row-main">
                  <div>
                    <strong>{row.goal.name}</strong>
                    <span>{goalTypeLabel(row.goal.type)}</span>
                  </div>
                  <b>{row.percent.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %</b>
                </div>
                <div className="progress-track" aria-label={`${row.goal.name} 진행률`}>
                  <div className="progress-fill" style={{ width: `${row.percent}%` }} />
                </div>
                <div className="progress-row-meta">
                  <span>{formatCurrency(row.current_amount_krw, displayCurrency, summary.usd_krw_rate)}</span>
                  <span>
                    남은 금액 {formatCurrency(row.remaining_krw, displayCurrency, summary.usd_krw_rate)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">등록된 목표가 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>자산 비중</h3>
          <span>{assetMixEntries.length.toLocaleString("ko-KR")}개 분류</span>
        </div>
        {assetMixEntries.length > 0 ? (
          <div className="asset-mix-stack">
            <div className="allocation-chart">
              <svg
                aria-label="주식/ETF와 현금 비중"
                className="allocation-pie-svg"
                role="img"
                viewBox={`0 0 ${pieChart.width} ${pieChart.height}`}
              >
                {allocationCallouts.map((callout) => (
                  <path
                    className="allocation-slice"
                    d={callout.path}
                    fill={callout.color}
                    key={callout.key}
                  />
                ))}
                {allocationCallouts.map((callout) => (
                  <g className="allocation-callout" key={`label-${callout.key}`}>
                    <polyline className="allocation-label-line" points={callout.linePoints} />
                    <text textAnchor={callout.textAnchor} x={callout.textX} y={callout.textY}>
                      <tspan className="allocation-label-name">{callout.label}</tspan>
                      <tspan className="allocation-label-percent" x={callout.textX} y={callout.percentY}>
                        {callout.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%
                      </tspan>
                    </text>
                  </g>
                ))}
              </svg>
              <div className="allocation-details">
                <div className="allocation-meter" aria-hidden="true">
                  {visibleAllocationSegments.map((segment) => (
                    <span
                      className="allocation-segment"
                      key={segment.key}
                      style={{ backgroundColor: segment.color, width: `${segment.value}%` }}
                    />
                  ))}
                </div>
                <div className="allocation-legend">
                  {allocationSegments.map((segment) => (
                    <div className="allocation-legend-row" key={segment.key}>
                      <span className="allocation-swatch" style={{ backgroundColor: segment.color }} />
                      <span>{segment.label}</span>
                      <strong>{segment.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mix-list">
              {assetMixEntries.map(([type, value]) => (
                <div className="mix-row" key={type}>
                  <span>{assetTypeLabel(type)}</span>
                  <strong>{value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %</strong>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="empty-state">등록된 자산 비중이 없습니다.</p>
        )}
      </section>
    </section>
  )
}

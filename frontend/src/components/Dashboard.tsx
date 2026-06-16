import { ArrowDown, ArrowUp } from "lucide-react"
import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { GoalProgress, PortfolioSummary } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  usd_krw_rate: null,
  usd_krw_change_percent: null,
  asset_mix: {},
}

type DisplayCurrency = "KRW" | "USD"

const displayCurrencies: DisplayCurrency[] = ["KRW", "USD"]
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
const formatFxChange = (changePercent: number | null) => {
  if (changePercent === null || !Number.isFinite(changePercent)) {
    return null
  }

  const sign = changePercent > 0 ? "+" : ""
  return `${sign}${changePercent.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`
}
const getFxChangeDirection = (changePercent: number | null) => {
  if (changePercent === null || !Number.isFinite(changePercent) || changePercent === 0) {
    return null
  }

  return changePercent < 0 ? "down" : changePercent > 0 ? "up" : null
}

export function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [goalProgress, setGoalProgress] = useState<GoalProgress[]>([])
  const [error, setError] = useState("")
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>("KRW")

  useEffect(() => {
    Promise.all([apiGet<PortfolioSummary>("/api/summary"), apiGet<GoalProgress[]>("/api/goals/progress")])
      .then(([summaryData, progressData]) => {
        setSummary(summaryData)
        setGoalProgress(progressData)
        setError("")
      })
      .catch((err) => setError(getErrorMessage(err)))
  }, [])

  const assetMixEntries = Object.entries(summary.asset_mix)
  const fxChange = formatFxChange(summary.usd_krw_change_percent)
  const fxDirection = getFxChangeDirection(summary.usd_krw_change_percent)

  return (
    <section className="screen-stack">
      <header className="page-header dashboard-header">
        <div>
          <h2>오늘의 자산</h2>
          <p>순자산, 목표, 자산 비중, 최근 변화를 확인합니다.</p>
          {summary.usd_krw_rate !== null && (
            <p className="fx-rate-line">
              <span>USD/KRW {summary.usd_krw_rate.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원</span>
              {fxChange !== null && (
                <span className={fxDirection ?? "flat"}>
                  {fxDirection === "down" && <ArrowDown aria-hidden="true" className="fx-change-icon" size={14} />}
                  {fxDirection === "up" && <ArrowUp aria-hidden="true" className="fx-change-icon" size={14} />}
                  전일대비 {fxChange}
                </span>
              )}
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
        <p className="form-message error-text">USD 환산 환율이 없습니다. 자동 시세 갱신 후 다시 확인하세요.</p>
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
          <div className="mix-list">
            {assetMixEntries.map(([type, value]) => (
              <div className="mix-row" key={type}>
                <span>{type}</span>
                <strong>{value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %</strong>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">등록된 자산 비중이 없습니다.</p>
        )}
      </section>
    </section>
  )
}

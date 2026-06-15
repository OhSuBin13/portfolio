import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { GoalProgress, PortfolioSummary } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  asset_mix: {},
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))
const formatKrw = (value: number) => `${value.toLocaleString("ko-KR", {maximumFractionDigits: 0})} 원`
const goalTypeLabel = (type: string) => (type === "monthly_income" ? "월 배당/소득" : "순자산")

export function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [goalProgress, setGoalProgress] = useState<GoalProgress[]>([])
  const [error, setError] = useState("")

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

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>오늘의 자산</h2>
        <p>순자산, 목표, 자산 비중, 최근 변화를 확인합니다.</p>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="summary-grid">
        <article className="panel hero-panel">
          <span>순자산</span>
          <strong>{formatKrw(summary.net_worth_krw)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>월 배당/소득</span>
          <strong>{formatKrw(summary.monthly_income_krw)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>총자산</span>
          <strong>{formatKrw(summary.gross_assets_krw)}</strong>
        </article>
        <article className="panel metric-panel">
          <span>부채</span>
          <strong>{formatKrw(summary.debt_krw)}</strong>
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
                  <span>{formatKrw(row.current_amount_krw)}</span>
                  <span>남은 금액 {formatKrw(row.remaining_krw)}</span>
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

import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { PortfolioSummary } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  asset_mix: {},
}

export function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [error, setError] = useState("")

  useEffect(() => {
    apiGet<PortfolioSummary>("/api/summary")
      .then((data) => {
        setSummary(data)
        setError("")
      })
      .catch((err) => setError(String(err)))
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
          <strong>{summary.net_worth_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
        <article className="panel metric-panel">
          <span>월 배당/소득</span>
          <strong>{summary.monthly_income_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
        <article className="panel metric-panel">
          <span>총자산</span>
          <strong>{summary.gross_assets_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
        <article className="panel metric-panel">
          <span>부채</span>
          <strong>{summary.debt_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
      </div>

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
                <strong>{value.toLocaleString("ko-KR")} 원</strong>
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

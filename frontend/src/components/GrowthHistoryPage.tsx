import { RefreshCw } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { apiGet, apiPost } from "../api"
import type { GrowthHistoryRow, PortfolioSnapshot } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatKrw = (value: number) =>
  `${value.toLocaleString("ko-KR", { maximumFractionDigits: 0 })} 원`

const formatPercent = (rate: number | null) =>
  rate === null ? "-" : `${(rate * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`

const signedClass = (value: number | null) => {
  if (value === null || value === 0) {
    return "signed-flat"
  }

  return value > 0 ? "signed-positive" : "signed-negative"
}

type GrowthTableProps = {
  rows: GrowthHistoryRow[]
  title: string
}

function GrowthTable({ rows, title }: GrowthTableProps) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h3>{title}</h3>
        <span>{rows.length.toLocaleString("ko-KR")}개 구간</span>
      </div>
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table growth-table">
            <thead>
              <tr>
                <th>구간</th>
                <th className="numeric-cell">시작 순자산</th>
                <th className="numeric-cell">종료 순자산</th>
                <th className="numeric-cell">순입금</th>
                <th className="numeric-cell">수익금</th>
                <th className="numeric-cell">성장률</th>
                <th className="numeric-cell">누적 수익률</th>
                <th className="numeric-cell">배당/이자</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${title}-${row.period}`}>
                  <td>{row.period}</td>
                  <td className="numeric-cell">{formatKrw(row.starting_net_worth_krw)}</td>
                  <td className="numeric-cell">{formatKrw(row.ending_net_worth_krw)}</td>
                  <td className={`numeric-cell ${signedClass(row.external_cash_flow_krw)}`}>
                    {formatKrw(row.external_cash_flow_krw)}
                  </td>
                  <td className={`numeric-cell ${signedClass(row.profit_krw)}`}>
                    {formatKrw(row.profit_krw)}
                  </td>
                  <td className={`numeric-cell ${signedClass(row.growth_rate)}`}>
                    {formatPercent(row.growth_rate)}
                  </td>
                  <td className={`numeric-cell ${signedClass(row.cumulative_growth_rate)}`}>
                    {formatPercent(row.cumulative_growth_rate)}
                  </td>
                  <td className="numeric-cell">{formatKrw(row.dividend_interest_krw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-state">성장 기록이 없습니다.</p>
      )}
    </section>
  )
}

export function GrowthHistoryPage() {
  const [monthlyRows, setMonthlyRows] = useState<GrowthHistoryRow[]>([])
  const [annualRows, setAnnualRows] = useState<GrowthHistoryRow[]>([])
  const [latestSnapshot, setLatestSnapshot] = useState<PortfolioSnapshot | null>(null)
  const [error, setError] = useState("")
  const [refreshMessage, setRefreshMessage] = useState("")
  const [isRefreshing, setIsRefreshing] = useState(false)
  const growthHistoryRequestSeq = useRef(0)

  const loadGrowthHistory = useCallback(async () => {
    const requestSeq = growthHistoryRequestSeq.current + 1
    growthHistoryRequestSeq.current = requestSeq

    try {
      const [monthly, annual] = await Promise.all([
        apiGet<GrowthHistoryRow[]>("/api/growth/history?period=monthly"),
        apiGet<GrowthHistoryRow[]>("/api/growth/history?period=annual"),
      ])

      if (requestSeq === growthHistoryRequestSeq.current) {
        setMonthlyRows(monthly)
        setAnnualRows(annual)
        setError("")
        return true
      }
    } catch (err) {
      if (requestSeq === growthHistoryRequestSeq.current) {
        setError(getErrorMessage(err))
      }
    }

    return false
  }, [])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadGrowthHistory()
    }, 0)

    return () => {
      window.clearTimeout(loadTimer)
      growthHistoryRequestSeq.current += 1
    }
  }, [loadGrowthHistory])

  const handleRefreshToday = async () => {
    setIsRefreshing(true)
    setRefreshMessage("")

    try {
      const snapshot = await apiPost<PortfolioSnapshot>("/api/growth/snapshots/today", {
        source: "manual",
      })
      setLatestSnapshot(snapshot)
      const didApplyRows = await loadGrowthHistory()
      if (didApplyRows) {
        setRefreshMessage(`${snapshot.snapshot_date} 스냅샷을 갱신했습니다.`)
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsRefreshing(false)
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header growth-header">
        <div>
          <h2>성장기록</h2>
          <p>입출금 흐름과 투자 성과를 분리해 월별/연간 성장률을 확인합니다.</p>
        </div>
        <button
          className="secondary-button refresh-button"
          disabled={isRefreshing}
          onClick={handleRefreshToday}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={16} />
          오늘 스냅샷 갱신
        </button>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="panel growth-status">
        <span>{refreshMessage || "오늘 스냅샷을 수동으로 갱신할 수 있습니다."}</span>
        {latestSnapshot ? (
          <strong>{formatKrw(latestSnapshot.net_worth_krw)}</strong>
        ) : (
          <strong>최근 갱신 없음</strong>
        )}
      </div>

      <GrowthTable rows={monthlyRows} title="월별 성장률" />
      <GrowthTable rows={annualRows} title="연간 성장률" />
    </section>
  )
}

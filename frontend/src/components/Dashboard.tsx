import { useEffect, useState } from "react"
import { getAllocationCallouts, getAllocationSegments, pieChart } from "../allocationChart"
import { apiGet } from "../api"
import { getErrorMessage } from "../errors"
import type { PortfolioSummary, TossAccount } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  usd_krw_rate: null,
  usd_krw_change_percent: null,
  asset_mix: {},
  asset_allocations: [],
  buying_power: [],
  buying_power_total_krw: 0,
  goal_progress: [],
}

type DisplayCurrency = "KRW" | "USD"

const displayCurrencies: DisplayCurrency[] = ["KRW", "USD"]
const formatUsdCurrency = (valueUsd: number) =>
  valueUsd.toLocaleString("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  })
const formatCurrency = (valueKrw: number, currency: DisplayCurrency, usdKrwRate: number | null) => {
  if (currency === "USD") {
    if (valueKrw === 0) {
      return formatUsdCurrency(0)
    }
    if (usdKrwRate === null || !Number.isFinite(usdKrwRate) || usdKrwRate <= 0) {
      return "환율 없음"
    }
    return formatUsdCurrency(valueKrw / usdKrwRate)
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

export function Dashboard() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [error, setError] = useState("")
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>("KRW")

  useEffect(() => {
    let ignore = false

    apiGet<TossAccount[]>("/api/toss/accounts")
      .then((accountData) => {
        if (ignore) {
          return
        }

        setAccounts(accountData)
        setAccountsLoaded(true)
        setError("")
        setSelectedAccountSeq((current) => {
          if (current && accountData.some((account) => account.account_seq === current)) {
            return current
          }
          return accountData[0]?.account_seq ?? ""
        })
        if (accountData.length === 0) {
          setSummary(emptySummary)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setAccounts([])
          setSelectedAccountSeq("")
          setSummary(emptySummary)
          setAccountsLoaded(true)
          setError(getErrorMessage(err))
        }
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    let ignore = false

    if (!selectedAccountSeq) {
      void Promise.resolve().then(() => {
        if (ignore) {
          return
        }

        setSummaryLoading(false)
        setSummary(emptySummary)
      })
      return () => {
        ignore = true
      }
    }

    void Promise.resolve().then(() => {
      if (ignore) {
        return
      }

      setSummaryLoading(true)
      setSummary(emptySummary)
      apiGet<PortfolioSummary>(`/api/summary?account_seq=${encodeURIComponent(selectedAccountSeq)}`)
        .then((summaryData) => {
          if (ignore) {
            return
          }

          setSummary(summaryData)
          setError("")
        })
        .catch((err) => {
          if (!ignore) {
            setSummary(emptySummary)
            setError(getErrorMessage(err))
          }
        })
        .finally(() => {
          if (!ignore) {
            setSummaryLoading(false)
          }
        })
    })

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq])

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)
  const hasNoAccounts = accountsLoaded && accounts.length === 0
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
      <section className="panel form-panel">
        <div className="section-heading">
          <h3>Toss 계좌</h3>
          <span>{accounts.length.toLocaleString("ko-KR")}개</span>
        </div>
        {accounts.length > 0 ? (
          <>
            <label>
              계좌
              <select
                value={selectedAccountSeq}
                onChange={(event) => setSelectedAccountSeq(event.target.value)}
              >
                {accounts.map((account) => (
                  <option key={account.account_seq} value={account.account_seq}>
                    {account.display_name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mix-list">
              <div className="mix-row">
                <span>account_seq</span>
                <strong>{selectedAccountSeq}</strong>
              </div>
              <div className="mix-row">
                <span>계좌 유형</span>
                <strong>{selectedAccount?.account_type ?? "-"}</strong>
              </div>
            </div>
          </>
        ) : (
          <p className="empty-state">
            {accountsLoaded
              ? "Toss 계좌가 없습니다. 설정에서 Toss API 인증 정보를 확인하세요."
              : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
        {summaryLoading && <p className="form-message">선택한 Toss 계좌 요약을 불러오는 중입니다.</p>}
      </section>

      {hasNoAccounts ? (
        <section className="panel">
          <p className="empty-state">계좌가 없어 요약을 불러오지 않았습니다.</p>
        </section>
      ) : (
        <>
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
              <span>매수 가능 금액</span>
              <strong>
                {formatCurrency(summary.buying_power_total_krw, displayCurrency, summary.usd_krw_rate)}
              </strong>
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
                          <strong>
                            {segment.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %
                          </strong>
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
        </>
      )}
    </section>
  )
}

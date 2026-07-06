import { useState } from "react"
import { RefreshCw, Search } from "lucide-react"
import { fetchCanslimAnalysis } from "../api"
import type {
  CanslimAnalysis,
  CanslimInstitutionalFlow,
  CanslimLetter,
  CanslimLetterStatus,
  CanslimMarketCandle,
  CanslimMarketContext,
  CanslimMarketRange,
  CanslimTopPerformingHolder,
} from "../types"

const marketRangeOptions = [
  { value: "3m", label: "3m" },
  { value: "6m", label: "6m" },
  { value: "1y", label: "1y" },
] as const

const statusLabels: Record<CanslimLetterStatus, string> = {
  pass: "충족",
  watch: "관찰",
  fail: "미충족",
  unknown: "데이터 없음",
  info: "정보",
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatNumber = (value: number | null | undefined, maximumFractionDigits = 2) => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-"
  }
  return value.toLocaleString("ko-KR", { maximumFractionDigits })
}

const formatUsd = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-"
  }
  return `$${value.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}`
}

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-"
  }
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`
}

const formatMetricValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "-"
  }
  if (typeof value === "number") {
    return formatNumber(value)
  }
  if (typeof value === "string") {
    return value
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false"
  }
  if (Array.isArray(value)) {
    return value.map(formatMetricValue).join(", ")
  }

  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const formatMetricName = (name: string) => name.replaceAll("_", " ")

function LetterSection({
  letter,
  name,
  value,
}: {
  letter: string
  name: string
  value: CanslimLetter
}) {
  const metrics = Object.entries(value.metrics)

  return (
    <article className={`canslim-letter-card canslim-status-${value.status}`}>
      <div className="canslim-letter-heading">
        <span>{letter}</span>
        <div>
          <h3>{name}</h3>
          <small>
            status · {statusLabels[value.status]} · source {value.source} · as_of {value.as_of ?? "-"}
          </small>
        </div>
      </div>
      <strong>{value.headline}</strong>
      {value.details.length > 0 ? (
        <ul className="canslim-detail-list">
          {value.details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">details 없음</p>
      )}
      {metrics.length > 0 ? (
        <dl className="canslim-metric-list">
          {metrics.map(([metric, metricValue]) => (
            <div key={metric}>
              <dt>{formatMetricName(metric)}</dt>
              <dd>{formatMetricValue(metricValue)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="empty-state">metrics 없음</p>
      )}
    </article>
  )
}

function InstitutionalFlow({ flow }: { flow: CanslimInstitutionalFlow }) {
  return (
    <dl className="canslim-flow-grid" aria-label="institutional_flow">
      <div>
        <dt>기관 수 변화</dt>
        <dd>{formatNumber(flow.holders_count_change)}</dd>
      </div>
      <div>
        <dt>보유 주식 변화</dt>
        <dd>{formatPercent(flow.shares_change_percent)}</dd>
      </div>
      <div>
        <dt>보유 비중</dt>
        <dd>{formatPercent(flow.ownership_percent)}</dd>
      </div>
      <div>
        <dt>시장가치 변화</dt>
        <dd>{formatPercent(flow.market_value_change_percent)}</dd>
      </div>
    </dl>
  )
}

function HolderRow({ holder }: { holder: CanslimTopPerformingHolder }) {
  return (
    <tr>
      <th scope="row">{holder.holder_name || "-"}</th>
      <td className="numeric-cell">{formatNumber(holder.shares, 0)}</td>
      <td className="numeric-cell">{formatUsd(holder.market_value)}</td>
      <td className="numeric-cell">{formatPercent(holder.portfolio_weight_percent)}</td>
      <td className="numeric-cell">{formatPercent(holder.performance_1y_percent)}</td>
      <td className="numeric-cell">{formatPercent(holder.performance_3y_percent)}</td>
      <td className="numeric-cell">{formatPercent(holder.performance_5y_percent)}</td>
      <td className="numeric-cell">{formatPercent(holder.excess_vs_sp500_percent)}</td>
    </tr>
  )
}

function CanslimMarketChart({ candles }: { candles: CanslimMarketCandle[] }) {
  const chartCandles = [...candles]
    .sort((left, right) => left.date.localeCompare(right.date))
    .slice(-60)

  if (chartCandles.length === 0) {
    return <p className="empty-state">SPY candles 데이터가 없습니다.</p>
  }

  const closes = chartCandles.map((candle) => candle.close)
  const minClose = Math.min(...closes)
  const maxClose = Math.max(...closes)
  const closeRange = Math.max(maxClose - minClose, 1)
  const pointStep = chartCandles.length > 1 ? 100 / (chartCandles.length - 1) : 100
  const points = chartCandles
    .map((candle, index) => {
      const x = chartCandles.length === 1 ? 50 : index * pointStep
      const y = 38 - ((candle.close - minClose) / closeRange) * 28
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(" ")
  const maxTradedValue = Math.max(...chartCandles.map((candle) => candle.traded_value_usd), 1)
  const barWidth = Math.max(100 / chartCandles.length - 0.5, 1)

  return (
    <svg className="canslim-market-chart" role="img" viewBox="0 0 100 52" aria-label="SPY chart">
      <polyline className="canslim-market-line" fill="none" points={points} />
      {chartCandles.map((candle, index) => {
        const height = Math.max((candle.traded_value_usd / maxTradedValue) * 10, 1)
        const x = chartCandles.length === 1 ? 50 - barWidth / 2 : index * (100 / chartCandles.length)
        return (
          <rect
            key={candle.date}
            className="canslim-market-volume"
            height={height}
            width={barWidth}
            x={x}
            y={50 - height}
          />
        )
      })}
    </svg>
  )
}

function MarketContext({ market }: { market: CanslimMarketContext }) {
  const latest = [...market.candles].sort((left, right) => right.date.localeCompare(left.date))[0]

  return (
    <section className="panel canslim-market-panel">
      <div className="section-heading">
        <div>
          <h3>M · 시장 컨텍스트 · SPY</h3>
          <span>
            status · {statusLabels[market.status]} · source {market.source} · as_of {market.as_of ?? "-"}
          </span>
        </div>
        <span>{market.range}</span>
      </div>
      <CanslimMarketChart candles={market.candles} />
      <dl className="canslim-flow-grid">
        <div>
          <dt>SPY 종가</dt>
          <dd>{latest ? formatUsd(latest.close) : "-"}</dd>
        </div>
        <div>
          <dt>volume</dt>
          <dd>{latest ? formatNumber(latest.volume, 0) : "-"}</dd>
        </div>
        <div>
          <dt>거래대금 (traded_value_usd)</dt>
          <dd>{latest ? formatUsd(latest.traded_value_usd) : "-"}</dd>
        </div>
      </dl>
      {market.candles.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table canslim-market-table">
            <thead>
              <tr>
                <th>일자</th>
                <th className="numeric-cell">종가</th>
                <th className="numeric-cell">volume</th>
                <th className="numeric-cell">traded_value_usd</th>
              </tr>
            </thead>
            <tbody>
              {market.candles.slice(0, 8).map((candle) => (
                <tr key={candle.date}>
                  <th scope="row">{candle.date}</th>
                  <td className="numeric-cell">{formatUsd(candle.close)}</td>
                  <td className="numeric-cell">{formatNumber(candle.volume, 0)}</td>
                  <td className="numeric-cell">{formatUsd(candle.traded_value_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

function CompanySummary({ analysis }: { analysis: CanslimAnalysis }) {
  return (
    <section className="panel canslim-company-panel">
      <div className="section-heading">
        <div>
          <h3>{analysis.company_name ?? analysis.symbol}</h3>
          <span>
            {analysis.symbol} · {analysis.exchange ?? "-"} · {analysis.currency}
          </span>
        </div>
        <span>{analysis.cached ? "캐시" : "신규"}</span>
      </div>
      <dl className="canslim-company-meta">
        <div>
          <dt>섹터</dt>
          <dd>{analysis.sector ?? "-"}</dd>
        </div>
        <div>
          <dt>산업</dt>
          <dd>{analysis.industry ?? "-"}</dd>
        </div>
        <div>
          <dt>provider</dt>
          <dd>{analysis.provider.toUpperCase()}</dd>
        </div>
        <div>
          <dt>generated_at</dt>
          <dd>{analysis.generated_at}</dd>
        </div>
      </dl>
      <div className="canslim-description">
        <span>회사 설명 · 무엇을 하는 회사인지</span>
        <p>{analysis.description || String(analysis.letters.n.metrics.description ?? "설명이 없습니다.")}</p>
      </div>
    </section>
  )
}

export function CanslimPage() {
  const [symbol, setSymbol] = useState("")
  const [marketRange, setMarketRange] = useState<CanslimMarketRange>("6m")
  const [analysis, setAnalysis] = useState<CanslimAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const runAnalysis = async (refresh = false) => {
    const normalizedSymbol = symbol.trim().toUpperCase()
    if (!normalizedSymbol) {
      setError("미국 상장 보통주 티커를 입력하세요.")
      return
    }

    setLoading(true)
    setError("")
    try {
      const result = await fetchCanslimAnalysis({
        symbol: normalizedSymbol,
        marketRange,
        refresh,
      })
      setAnalysis(result)
      setSymbol(normalizedSymbol)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const letterSections = analysis
    ? [
        { letter: "C", name: "Current earnings", value: analysis.letters.c },
        { letter: "A", name: "Annual earnings", value: analysis.letters.a },
        { letter: "N", name: "New product/profile", value: analysis.letters.n },
        { letter: "S", name: "Supply and demand", value: analysis.letters.s },
        { letter: "L", name: "Leader or laggard", value: analysis.letters.l },
      ]
    : []

  return (
    <div className="screen-stack canslim-screen">
      <section className="page-header canslim-header">
        <div>
          <h2>CAN SLIM</h2>
          <p>C/A/N/S/L/I/M 근거를 한 화면에서 확인합니다.</p>
        </div>
      </section>

      <form
        className="panel canslim-search-panel"
        onSubmit={(event) => {
          event.preventDefault()
          void runAnalysis(false)
        }}
      >
        <label>
          미국 티커
          <input
            autoCapitalize="characters"
            autoComplete="off"
            inputMode="text"
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="NVDA"
            value={symbol}
          />
        </label>
        <div className="canslim-range-toggle" role="group" aria-label="시장 범위">
          {marketRangeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={marketRange === option.value}
              onClick={() => setMarketRange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button className="primary-button" disabled={loading} type="submit">
          <Search size={18} />
          <span>{loading ? "조회 중" : "조회"}</span>
        </button>
        <button
          className="secondary-button"
          disabled={loading}
          onClick={() => void runAnalysis(true)}
          type="button"
        >
          <RefreshCw size={18} />
          <span>새로고침</span>
        </button>
      </form>

      {error && <div className="error">{error}</div>}
      {loading && <p className="empty-state">CAN SLIM 데이터를 불러오는 중입니다.</p>}
      {!analysis && !loading && (
        <section className="panel canslim-help-panel">
          <p className="empty-state">
            FMP API 키를 backend 환경에 설정해 주세요. CAN SLIM v1은 미국 상장 보통주만 지원합니다.
          </p>
        </section>
      )}

      {analysis && (
        <>
          <CompanySummary analysis={analysis} />
          <section className="canslim-grid" aria-label="CAN SLIM letter sections">
            {letterSections.map((item) => (
              <LetterSection
                key={item.letter}
                letter={item.letter}
                name={item.name}
                value={item.value}
              />
            ))}
            <LetterSection letter="I" name="Institutional sponsorship" value={analysis.letters.i} />
          </section>

          <section className="panel canslim-institution-panel">
            <div className="section-heading">
              <div>
                <h3>I · 기관 수급</h3>
                <span>institutional_flow · top_performing_holders</span>
              </div>
              <span>{statusLabels[analysis.letters.i.status]}</span>
            </div>
            <InstitutionalFlow flow={analysis.letters.i.institutional_flow} />
            {analysis.letters.i.top_performing_holders.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table canslim-holder-table">
                  <thead>
                    <tr>
                      <th>holder_name</th>
                      <th className="numeric-cell">shares</th>
                      <th className="numeric-cell">market_value</th>
                      <th className="numeric-cell">portfolio_weight_percent</th>
                      <th className="numeric-cell">performance_1y_percent</th>
                      <th className="numeric-cell">performance_3y_percent</th>
                      <th className="numeric-cell">performance_5y_percent</th>
                      <th className="numeric-cell">excess_vs_sp500_percent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.letters.i.top_performing_holders.map((holder) => (
                      <HolderRow key={`${holder.cik}:${holder.holder_name}`} holder={holder} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-state">top_performing_holders 데이터가 없습니다.</p>
            )}
          </section>

          <MarketContext market={analysis.letters.m} />
        </>
      )}
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from "react"
import { apiDelete, apiGet, apiPut } from "../api"
import type {
  GrowthAnnualHistoryRow,
  GrowthMonthHistoryRow,
  PortfolioSummary,
  TossAccount,
} from "../types"

type GrowthForm = {
  year: string
  month: string
  netWorthKrw: string
  monthlyDividendKrw: string
}

const today = new Date()
const initialForm: GrowthForm = {
  year: String(today.getFullYear()),
  month: String(today.getMonth() + 1),
  netWorthKrw: "",
  monthlyDividendKrw: "",
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))
const accountLabel = (account: TossAccount) => `${account.display_name} (${account.account_type})`
const formatKrw = (value: number) =>
  `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원`
const formatRatio = (value: number | null) => (value === null ? "-" : `${value.toFixed(4)}x`)
const normalizeNumericInput = (value: string) => value.replaceAll(",", "").trim()
const parseRequiredNumber = (value: string) => Number(normalizeNumericInput(value))

const buildAccountQuery = (path: string, accountSeq: string) =>
  `${path}?account_seq=${encodeURIComponent(accountSeq)}`
const monthRowKey = (row: GrowthMonthHistoryRow) => `${row.account_seq}:${row.year}:${row.month}`

export function GrowthHistoryPage() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [monthHistory, setMonthHistory] = useState<GrowthMonthHistoryRow[]>([])
  const [annualHistory, setAnnualHistory] = useState<GrowthAnnualHistoryRow[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [deletingKey, setDeletingKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [fillingSummary, setFillingSummary] = useState(false)
  const [form, setForm] = useState<GrowthForm>(initialForm)
  const [message, setMessage] = useState("")
  const [accountsError, setAccountsError] = useState("")
  const [historyError, setHistoryError] = useState("")
  const selectedAccountSeqRef = useRef("")

  const loadHistory = useCallback(async (accountSeq: string) => {
    const [monthRows, annualRows] = await Promise.all([
      apiGet<GrowthMonthHistoryRow[]>(buildAccountQuery("/api/growth/month-history", accountSeq)),
      apiGet<GrowthAnnualHistoryRow[]>(buildAccountQuery("/api/growth/annual-history", accountSeq)),
    ])

    return { annualRows, monthRows }
  }, [])

  useEffect(() => {
    let ignore = false

    apiGet<TossAccount[]>("/api/toss/accounts")
      .then((accountData) => {
        if (ignore) {
          return
        }

        setAccounts(accountData)
        setAccountsLoaded(true)
        setAccountsError("")
        setSelectedAccountSeq((current) => {
          const next = current && accountData.some((account) => account.account_seq === current)
            ? current
            : (accountData[0]?.account_seq ?? "")
          selectedAccountSeqRef.current = next
          return next
        })
        if (accountData.length === 0) {
          setMonthHistory([])
          setAnnualHistory([])
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        selectedAccountSeqRef.current = ""
        setSelectedAccountSeq("")
        setMonthHistory([])
        setAnnualHistory([])
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    selectedAccountSeqRef.current = selectedAccountSeq
  }, [selectedAccountSeq])

  useEffect(() => {
    if (!selectedAccountSeq) {
      return undefined
    }

    let ignore = false
    const requestAccountSeq = selectedAccountSeq

    void Promise.resolve()
      .then(() => {
        if (ignore || requestAccountSeq !== selectedAccountSeqRef.current) {
          return undefined
        }

        setHistoryLoading(true)
        setHistoryError("")
        setMonthHistory([])
        setAnnualHistory([])
        return loadHistory(requestAccountSeq)
      })
      .then((history) => {
        if (!history || ignore || requestAccountSeq !== selectedAccountSeqRef.current) {
          return
        }

        setMonthHistory(history.monthRows)
        setAnnualHistory(history.annualRows)
      })
      .catch((err) => {
        if (!ignore && requestAccountSeq === selectedAccountSeqRef.current) {
          setMonthHistory([])
          setAnnualHistory([])
          setHistoryError(getErrorMessage(err))
        }
      })
      .finally(() => {
        if (!ignore && requestAccountSeq === selectedAccountSeqRef.current) {
          setHistoryLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [loadHistory, selectedAccountSeq])

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)
  const hasNoAccounts = accountsLoaded && accounts.length === 0

  const handleFillCurrentNetWorth = async () => {
    const requestAccountSeq = selectedAccountSeq
    if (!requestAccountSeq) {
      return
    }

    setMessage("")
    setHistoryError("")
    setFillingSummary(true)

    try {
      const summary = await apiGet<PortfolioSummary>(
        buildAccountQuery("/api/summary", requestAccountSeq),
      )
      if (requestAccountSeq !== selectedAccountSeqRef.current) {
        return
      }
      setForm((prev) => ({ ...prev, netWorthKrw: String(summary.net_worth_krw) }))
      setMessage("현재 순자산을 채웠습니다.")
    } catch (err) {
      if (requestAccountSeq === selectedAccountSeqRef.current) {
        setHistoryError(getErrorMessage(err))
      }
    } finally {
      setFillingSummary(false)
    }
  }

  const handleEditMonth = (row: GrowthMonthHistoryRow) => {
    setForm({
      year: String(row.year),
      month: String(row.month),
      netWorthKrw: String(row.net_worth_krw),
      monthlyDividendKrw: String(row.monthly_dividend_krw),
    })
    setMessage("선택한 월 기록을 불러왔습니다.")
    setHistoryError("")
  }

  const handleDeleteMonth = async (row: GrowthMonthHistoryRow) => {
    const requestAccountSeq = selectedAccountSeq
    if (!requestAccountSeq) {
      setHistoryError("계좌를 선택하세요.")
      return
    }

    if (!window.confirm(`${row.year}년 ${row.month}월 성장 기록을 삭제할까요?`)) {
      return
    }

    const targetKey = monthRowKey(row)
    setMessage("")
    setHistoryError("")
    setDeletingKey(targetKey)

    try {
      await apiDelete(
        buildAccountQuery(`/api/growth/month-history/${row.year}/${row.month}`, requestAccountSeq),
      )
      if (requestAccountSeq !== selectedAccountSeqRef.current) {
        return
      }
      const history = await loadHistory(requestAccountSeq)
      if (requestAccountSeq !== selectedAccountSeqRef.current) {
        return
      }
      setMonthHistory(history.monthRows)
      setAnnualHistory(history.annualRows)
      setMessage("성장 기록을 삭제했습니다.")
    } catch (err) {
      if (requestAccountSeq === selectedAccountSeqRef.current) {
        setHistoryError(getErrorMessage(err))
      }
    } finally {
      setDeletingKey((current) => (current === targetKey ? "" : current))
    }
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage("")
    setHistoryError("")

    const requestAccountSeq = selectedAccountSeq
    if (!requestAccountSeq) {
      setHistoryError("계좌를 선택하세요.")
      return
    }

    const year = parseRequiredNumber(form.year)
    const month = parseRequiredNumber(form.month)
    const netWorthInput = normalizeNumericInput(form.netWorthKrw)
    const monthlyDividendInput = normalizeNumericInput(form.monthlyDividendKrw)
    const netWorthKrw = Number(netWorthInput)
    const monthlyDividendKrw = monthlyDividendInput ? Number(monthlyDividendInput) : 0

    if (!Number.isInteger(year) || year < 2000 || year > 2099) {
      setHistoryError("년은 2000부터 2099 사이로 입력하세요.")
      return
    }

    if (!Number.isInteger(month) || month < 1 || month > 12) {
      setHistoryError("월은 1부터 12 사이로 입력하세요.")
      return
    }

    if (!netWorthInput) {
      setHistoryError("순자산을 입력하세요.")
      return
    }

    if (!Number.isFinite(netWorthKrw) || netWorthKrw < 0) {
      setHistoryError("순자산은 0 이상의 숫자로 입력하세요.")
      return
    }

    if (!Number.isFinite(monthlyDividendKrw) || monthlyDividendKrw < 0) {
      setHistoryError("월 배당은 0 이상의 숫자로 입력하세요.")
      return
    }

    setSaving(true)

    try {
      await apiPut<GrowthMonthHistoryRow>(
        buildAccountQuery(`/api/growth/month-history/${year}/${month}`, requestAccountSeq),
        {
          net_worth_krw: netWorthKrw,
          monthly_dividend_krw: monthlyDividendKrw,
        },
      )
      if (requestAccountSeq !== selectedAccountSeqRef.current) {
        return
      }
      const history = await loadHistory(requestAccountSeq)
      if (requestAccountSeq !== selectedAccountSeqRef.current) {
        return
      }
      setMonthHistory(history.monthRows)
      setAnnualHistory(history.annualRows)
      setMessage("성장 기록을 저장했습니다.")
    } catch (err) {
      if (requestAccountSeq === selectedAccountSeqRef.current) {
        setHistoryError(getErrorMessage(err))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>성장기록</h2>
        <p>월별 순자산과 배당 이력.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {historyError && <div className="error">{historyError}</div>}

      <section className="panel form-panel">
        <div className="section-heading">
          <h3>계좌 선택</h3>
          <span>{accounts.length.toLocaleString("ko-KR")}개</span>
        </div>
        {accounts.length > 0 ? (
          <>
            <label>
              Toss 계좌
              <select
                value={selectedAccountSeq}
                onChange={(event) => {
                  selectedAccountSeqRef.current = event.target.value
                  setSelectedAccountSeq(event.target.value)
                }}
              >
                {accounts.map((account) => (
                  <option key={account.account_seq} value={account.account_seq}>
                    {accountLabel(account)}
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
                <span>계좌번호</span>
                <strong>{selectedAccount?.account_no ?? "-"}</strong>
              </div>
            </div>
          </>
        ) : (
          <p className="empty-state">
            {accountsLoaded ? "Toss 계좌가 없습니다." : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
      </section>

      <form className="panel form-panel compact-form" onSubmit={handleSubmit}>
        <div className="section-heading">
          <h3>월 기록</h3>
          <span>KRW</span>
        </div>
        <div className="growth-entry-grid">
          <label>
            년
            <input
              inputMode="numeric"
              onChange={(event) => setForm((prev) => ({ ...prev, year: event.target.value }))}
              value={form.year}
            />
          </label>
          <label>
            월
            <input
              inputMode="numeric"
              onChange={(event) => setForm((prev) => ({ ...prev, month: event.target.value }))}
              value={form.month}
            />
          </label>
          <label>
            순자산
            <input
              inputMode="decimal"
              onChange={(event) =>
                setForm((prev) => ({ ...prev, netWorthKrw: event.target.value }))
              }
              placeholder="0"
              value={form.netWorthKrw}
            />
          </label>
          <label>
            월 배당
            <input
              inputMode="decimal"
              onChange={(event) =>
                setForm((prev) => ({ ...prev, monthlyDividendKrw: event.target.value }))
              }
              placeholder="0"
              value={form.monthlyDividendKrw}
            />
          </label>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            disabled={!selectedAccountSeq || fillingSummary}
            onClick={handleFillCurrentNetWorth}
            type="button"
          >
            현재 순자산 채우기
          </button>
          <button className="primary-button" disabled={hasNoAccounts || saving} type="submit">
            기록 저장
          </button>
        </div>
        {historyLoading && <p className="form-message">성장 기록을 불러오는 중입니다.</p>}
        {message && <p className="form-message success-text">{message}</p>}
      </form>

      <section className="panel">
        <div className="section-heading">
          <h3>Growth Month History</h3>
          <span>{monthHistory.length.toLocaleString("ko-KR")}개월</span>
        </div>
        {monthHistory.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table growth-table">
              <thead>
                <tr>
                  <th>년</th>
                  <th>월</th>
                  <th className="numeric-cell">순자산</th>
                  <th className="numeric-cell">월 배당</th>
                  <th className="numeric-cell">평균 수익률</th>
                  <th className="numeric-cell">수익률</th>
                  <th className="numeric-cell">누적배당</th>
                  <th className="numeric-cell">관리</th>
                </tr>
              </thead>
              <tbody>
                {monthHistory.map((row) => (
                  <tr key={monthRowKey(row)}>
                    <td>{row.year}</td>
                    <td>{row.month}</td>
                    <td className="numeric-cell">{formatKrw(row.net_worth_krw)}</td>
                    <td className="numeric-cell">{formatKrw(row.monthly_dividend_krw)}</td>
                    <td className="numeric-cell">{formatRatio(row.average_return_ratio)}</td>
                    <td className="numeric-cell">{formatRatio(row.monthly_return_ratio)}</td>
                    <td className="numeric-cell">{formatKrw(row.cumulative_dividend_krw)}</td>
                    <td className="numeric-cell">
                      <div className="table-actions">
                        <button onClick={() => handleEditMonth(row)} type="button">
                          수정
                        </button>
                        <button
                          disabled={deletingKey === monthRowKey(row)}
                          onClick={() => handleDeleteMonth(row)}
                          type="button"
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">월별 성장 기록이 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Growth Annual History</h3>
          <span>{annualHistory.length.toLocaleString("ko-KR")}년</span>
        </div>
        {annualHistory.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>년</th>
                  <th className="numeric-cell">순자산</th>
                  <th className="numeric-cell">평균 수익률</th>
                  <th className="numeric-cell">연 수익률</th>
                </tr>
              </thead>
              <tbody>
                {annualHistory.map((row) => (
                  <tr key={`${row.account_seq}:${row.year}:${row.source_month}`}>
                    <td>{row.display_year}</td>
                    <td className="numeric-cell">{formatKrw(row.net_worth_krw)}</td>
                    <td className="numeric-cell">{formatRatio(row.average_return_ratio)}</td>
                    <td className="numeric-cell">{formatRatio(row.annual_return_ratio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">연간 성장 기록이 없습니다.</p>
        )}
      </section>
    </section>
  )
}

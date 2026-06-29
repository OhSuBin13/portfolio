import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { TossAccount, TossHolding } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatNumber = (value: number) =>
  value.toLocaleString("ko-KR", {
    maximumFractionDigits: 6,
  })

const formatMoney = (value: number | null, currency: TossHolding["currency"]) =>
  value === null
    ? "-"
    : `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${currency}`

const accountLabel = (account: TossAccount) =>
  `${account.display_name} (${account.account_type})`

export function HoldingsPage() {
  const readOnly = true
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [holdings, setHoldings] = useState<TossHolding[]>([])
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [accountsError, setAccountsError] = useState("")
  const [holdingsError, setHoldingsError] = useState("")

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
          if (current && accountData.some((account) => account.account_seq === current)) {
            return current
          }
          return accountData[0]?.account_seq ?? ""
        })
        if (accountData.length === 0) {
          setHoldings([])
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        setHoldings([])
        setSelectedAccountSeq("")
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      setHoldings([])
      setHoldingsLoading(false)
      setHoldingsError("")
      return
    }

    let ignore = false
    setHoldingsLoading(true)

    apiGet<TossHolding[]>(
      `/api/toss/holdings?account_seq=${encodeURIComponent(selectedAccountSeq)}`,
    )
      .then((holdingData) => {
        if (ignore) {
          return
        }

        setHoldings(holdingData)
        setHoldingsError("")
      })
      .catch((err) => {
        if (!ignore) {
          setHoldings([])
          setHoldingsError(getErrorMessage(err))
        }
      })
      .finally(() => {
        if (!ignore) {
          setHoldingsLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq])

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)

  return (
    <section className="screen-stack" data-read-only={readOnly}>
      <header className="page-header">
        <h2>Toss 보유자산</h2>
        <p>토스증권 계좌에서 읽어온 보유 내역을 조회합니다.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {holdingsError && <div className="error">{holdingsError}</div>}

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
                onChange={(event) => setSelectedAccountSeq(event.target.value)}
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
            {accountsLoaded
              ? "Toss 계좌가 없습니다. 서버의 Toss API 인증 정보를 확인하세요."
              : "Toss 계좌를 불러오는 중입니다."}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>보유 내역</h3>
          <span>{holdings.length.toLocaleString("ko-KR")}개 종목</span>
        </div>
        {holdings.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>시장</th>
                  <th>통화</th>
                  <th className="numeric-cell">수량</th>
                  <th className="numeric-cell">평균매입가</th>
                  <th className="numeric-cell">현재가</th>
                  <th className="numeric-cell">평가금액</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding) => (
                  <tr key={`${holding.market}:${holding.symbol}`}>
                    <td>
                      <strong>{holding.symbol}</strong>
                      <br />
                      <span>{holding.name}</span>
                    </td>
                    <td>{holding.market}</td>
                    <td>{holding.currency}</td>
                    <td className="numeric-cell">{formatNumber(holding.quantity)}</td>
                    <td className="numeric-cell">
                      {formatMoney(holding.average_purchase_price, holding.currency)}
                    </td>
                    <td className="numeric-cell">{formatMoney(holding.last_price, holding.currency)}</td>
                    <td className="numeric-cell">{formatMoney(holding.market_value, holding.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">
            {holdingsLoading
              ? "Toss 보유자산을 불러오는 중입니다."
              : "선택한 Toss 계좌의 보유자산이 없습니다."}
          </p>
        )}
      </section>
    </section>
  )
}

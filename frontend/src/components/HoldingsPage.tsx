import { useEffect, useState } from "react"
import { formatTossAccountLabel } from "../accountLabels"
import { apiGet } from "../api"
import type { TossAccount, TossBuyingPower, TossHolding } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatNumber = (value: number) =>
  value.toLocaleString("ko-KR", {
    maximumFractionDigits: 6,
  })

const formatMoney = (value: number | null, currency: TossHolding["currency"]) =>
  value === null
    ? "-"
    : `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${currency}`

export function HoldingsPage() {
  const readOnly = true
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [holdings, setHoldings] = useState<TossHolding[]>([])
  const [buyingPower, setBuyingPower] = useState<TossBuyingPower[]>([])
  const [accountsLoaded, setAccountsLoaded] = useState(false)
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [portfolioLoadedAccountSeq, setPortfolioLoadedAccountSeq] = useState("")
  const [accountsError, setAccountsError] = useState("")
  const [holdingsError, setHoldingsError] = useState("")
  const [buyingPowerError, setBuyingPowerError] = useState("")

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
          setBuyingPower([])
          setBuyingPowerError("")
          setPortfolioLoadedAccountSeq("")
        }
      })
      .catch((err) => {
        if (ignore) {
          return
        }

        setAccounts([])
        setHoldings([])
        setBuyingPower([])
        setBuyingPowerError("")
        setSelectedAccountSeq("")
        setPortfolioLoadedAccountSeq("")
        setAccountsLoaded(true)
        setAccountsError(getErrorMessage(err))
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      void Promise.resolve().then(() => {
        setHoldingsLoading(false)
        setHoldings([])
        setHoldingsError("")
        setBuyingPower([])
        setBuyingPowerError("")
        setPortfolioLoadedAccountSeq("")
      })
      return
    }

    let ignore = false

    void Promise.resolve().then(() => {
      if (ignore) {
        return
      }

      setHoldingsLoading(true)
      setHoldings([])
      setHoldingsError("")
      setBuyingPower([])
      setBuyingPowerError("")
      setPortfolioLoadedAccountSeq("")
      Promise.allSettled([
        apiGet<TossHolding[]>(
          `/api/toss/holdings?account_seq=${encodeURIComponent(selectedAccountSeq)}`,
        ),
        apiGet<TossBuyingPower[]>(
          `/api/toss/buying-power?account_seq=${encodeURIComponent(selectedAccountSeq)}`,
        ),
      ])
        .then(([holdingResult, buyingPowerResult]) => {
          if (ignore) {
            return
          }

          if (holdingResult.status === "fulfilled") {
            setHoldings(holdingResult.value)
            setHoldingsError("")
          } else {
            setHoldings([])
            setHoldingsError(getErrorMessage(holdingResult.reason))
          }

          if (buyingPowerResult.status === "fulfilled") {
            setBuyingPower(buyingPowerResult.value)
            setBuyingPowerError("")
          } else {
            setBuyingPower([])
            setBuyingPowerError(getErrorMessage(buyingPowerResult.reason))
          }

          setPortfolioLoadedAccountSeq(selectedAccountSeq)
        })
        .finally(() => {
          if (!ignore) {
            setHoldingsLoading(false)
          }
        })
    })

    return () => {
      ignore = true
    }
  }, [selectedAccountSeq])

  const selectedAccount = accounts.find((account) => account.account_seq === selectedAccountSeq)
  const accountsLoading = !accountsLoaded && !accountsError
  const portfolioLoading =
    accountsLoading ||
    (Boolean(selectedAccountSeq) && portfolioLoadedAccountSeq !== selectedAccountSeq)
  const noAccountMessage = accountsLoaded
    ? "Toss 계좌가 없습니다. 서버의 Toss API 인증 정보를 확인하세요."
    : "Toss 계좌를 불러오는 중입니다."
  const buyingPowerEmptyMessage = accountsLoading
    ? "Toss 계좌를 불러오는 중입니다."
    : !selectedAccountSeq
      ? "선택된 Toss 계좌가 없습니다."
      : portfolioLoading || holdingsLoading
        ? "Toss 매수 가능 금액을 불러오는 중입니다."
        : "선택한 Toss 계좌의 매수 가능 금액이 없습니다."
  const holdingsEmptyMessage = accountsLoading
    ? "Toss 계좌를 불러오는 중입니다."
    : !selectedAccountSeq
      ? "선택된 Toss 계좌가 없습니다."
      : portfolioLoading || holdingsLoading
        ? "Toss 보유자산을 불러오는 중입니다."
        : "선택한 Toss 계좌의 보유자산이 없습니다."

  return (
    <section className="screen-stack" data-read-only={readOnly}>
      <header className="page-header">
        <h2>Toss 보유자산</h2>
        <p>토스증권 계좌에서 읽어온 보유 내역을 조회합니다.</p>
      </header>

      {accountsError && <div className="error">{accountsError}</div>}
      {holdingsError && <div className="error">{holdingsError}</div>}
      {buyingPowerError && <div className="error">{buyingPowerError}</div>}

      <section className="panel form-panel">
        <div className="section-heading">
          <h3>계좌 선택</h3>
          <span>{accounts.length.toLocaleString("ko-KR")}개</span>
        </div>
        <label>
          Toss 계좌
          <select
            disabled={accounts.length === 0}
            value={selectedAccountSeq}
            onChange={(event) => setSelectedAccountSeq(event.target.value)}
          >
            {accounts.length > 0 ? (
              accounts.map((account) => (
                <option key={account.account_seq} value={account.account_seq}>
                  {formatTossAccountLabel(account)}
                </option>
              ))
            ) : (
              <option value="">{accountsLoaded ? "선택 가능한 Toss 계좌 없음" : "Toss 계좌를 불러오는 중"}</option>
            )}
          </select>
        </label>
        <div className="mix-list">
          <div className="mix-row">
            <span>account_seq</span>
            <strong>{selectedAccountSeq || "-"}</strong>
          </div>
          <div className="mix-row">
            <span>계좌번호</span>
            <strong>{selectedAccount?.account_no ?? "-"}</strong>
          </div>
        </div>
        {accounts.length === 0 && <p className="empty-state">{noAccountMessage}</p>}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>매수 가능 금액</h3>
          <span>{buyingPower.length.toLocaleString("ko-KR")}개 통화</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>통화</th>
                <th className="numeric-cell">현금 기반 매수 가능 금액</th>
              </tr>
            </thead>
            <tbody>
              {buyingPower.length > 0 ? (
                buyingPower.map((row) => (
                  <tr key={row.currency}>
                    <td>{row.currency}</td>
                    <td className="numeric-cell">
                      {formatMoney(row.cash_buying_power, row.currency)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="empty-table-cell" colSpan={2}>
                    {buyingPowerEmptyMessage}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>보유 내역</h3>
          <span>{holdings.length.toLocaleString("ko-KR")}개 종목</span>
        </div>
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
              {holdings.length > 0 ? (
                holdings.map((holding) => (
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
                ))
              ) : (
                <tr>
                  <td className="empty-table-cell" colSpan={7}>
                    {holdingsEmptyMessage}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}

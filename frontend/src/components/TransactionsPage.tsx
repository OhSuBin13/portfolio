import { useCallback, useEffect, useState } from "react"
import { apiGet, apiPost } from "../api"
import type { Account, Asset, Transaction } from "../types"

const transactionTypes = [
  ["deposit", "입금"],
  ["withdrawal", "출금"],
  ["buy", "매수"],
  ["sell", "매도"],
  ["dividend", "배당"],
  ["interest", "이자"],
  ["fee", "수수료"],
  ["debt_payment", "부채상환"],
  ["adjustment", "조정"],
]

const today = () => {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))
const transactionTypeLabel = (type: string) =>
  transactionTypes.find(([value]) => value === type)?.[1] ?? type
const formatNumber = (value: number) => value.toLocaleString("ko-KR", { maximumFractionDigits: 6 })
const formatAmount = (amount: number, currency: string) => `${formatNumber(amount)} ${currency}`

type TransactionForm = {
  occurredOn: string
  type: string
  accountId: string
  assetId: string
  quantity: string
  amount: string
  currency: string
  fxRateToKrw: string
  memo: string
}

export function TransactionsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loadError, setLoadError] = useState("")
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [form, setForm] = useState<TransactionForm>({
    occurredOn: today(),
    type: "deposit",
    accountId: "",
    assetId: "",
    quantity: "",
    amount: "",
    currency: "KRW",
    fxRateToKrw: "",
    memo: "",
  })

  const loadTransactions = useCallback(async () => {
    const data = await apiGet<Transaction[]>("/api/transactions")
    setTransactions(data)
  }, [])

  useEffect(() => {
    Promise.all([
      apiGet<Account[]>("/api/accounts"),
      apiGet<Asset[]>("/api/assets"),
      apiGet<Transaction[]>("/api/transactions"),
    ])
      .then(([accountData, assetData, transactionData]) => {
        setAccounts(accountData)
        setAssets(assetData)
        setTransactions(transactionData)
        setLoadError("")
        setForm((prev) => ({
          ...prev,
          accountId: prev.accountId || (accountData[0] ? String(accountData[0].id) : ""),
          assetId: prev.assetId || (assetData[0] ? String(assetData[0].id) : ""),
        }))
      })
      .catch((err) => setLoadError(getErrorMessage(err)))
  }, [])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage("")
    setError("")

    const accountId = Number(form.accountId)
    const assetId = Number(form.assetId)
    const amount = Number(form.amount)
    const isAdjustment = form.type === "adjustment"
    const needsQuantity = form.type === "buy" || form.type === "sell"
    const quantityValue = Number(form.quantity)
    const quantity = needsQuantity ? quantityValue : null
    const fxRateToKrw = form.fxRateToKrw.trim() ? Number(form.fxRateToKrw) : null

    if (!accountId || !assetId) {
      setError("계좌와 자산을 선택하세요.")
      return
    }

    if (!form.amount.trim() || !Number.isFinite(amount) || amount < 0) {
      setError(
        isAdjustment ? "조정 금액은 0 이상 숫자로 입력하세요." : "금액은 0보다 큰 숫자로 입력하세요.",
      )
      return
    }

    if (!isAdjustment && amount <= 0) {
      setError("금액은 0보다 큰 숫자로 입력하세요.")
      return
    }

    if (needsQuantity && (!Number.isFinite(quantityValue) || quantityValue <= 0)) {
      setError("매수와 매도는 0보다 큰 수량이 필요합니다.")
      return
    }

    if (fxRateToKrw !== null && (!Number.isFinite(fxRateToKrw) || fxRateToKrw <= 0)) {
      setError("환율은 비워두거나 0보다 큰 숫자로 입력하세요.")
      return
    }

    try {
      await apiPost<Transaction>("/api/transactions", {
        occurred_on: form.occurredOn,
        type: form.type,
        account_id: accountId,
        asset_id: assetId,
        quantity,
        amount,
        currency: form.currency.trim().toUpperCase(),
        memo: form.memo.trim(),
        fx_rate_to_krw: fxRateToKrw,
      })
      await loadTransactions()
      setForm((prev) => ({
        ...prev,
        occurredOn: today(),
        quantity: "",
        amount: "",
        fxRateToKrw: "",
        memo: "",
      }))
      setMessage("거래를 저장했습니다.")
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  const accountNames = new Map(accounts.map((account) => [account.id, account.name]))
  const assetNames = new Map(
    assets.map((asset) => [asset.id, asset.symbol ? `${asset.name} (${asset.symbol})` : asset.name]),
  )

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>거래내역</h2>
        <p>입출금, 매수/매도, 배당과 수수료를 기록합니다.</p>
      </header>

      {loadError && <div className="error">{loadError}</div>}

      <form className="panel form-panel" onSubmit={handleSubmit}>
        <div className="section-heading">
          <h3>거래 입력</h3>
          <span>계좌 {accounts.length.toLocaleString("ko-KR")}개</span>
        </div>
        <div className="field-row triple">
          <label>
            거래일
            <input
              type="date"
              value={form.occurredOn}
              onChange={(event) => setForm((prev) => ({ ...prev, occurredOn: event.target.value }))}
            />
          </label>
          <label>
            거래 유형
            <select
              value={form.type}
              onChange={(event) => setForm((prev) => ({ ...prev, type: event.target.value }))}
            >
              {transactionTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            통화
            <input
              value={form.currency}
              onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}
            />
          </label>
        </div>

        <div className="field-row">
          <label>
            계좌
            <select
              value={form.accountId}
              onChange={(event) => setForm((prev) => ({ ...prev, accountId: event.target.value }))}
            >
              <option value="">선택</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            자산
            <select
              value={form.assetId}
              onChange={(event) => setForm((prev) => ({ ...prev, assetId: event.target.value }))}
            >
              <option value="">선택</option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.symbol ? `${asset.name} (${asset.symbol})` : asset.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="field-row triple">
          <label>
            수량
            <input
              inputMode="decimal"
              value={form.quantity}
              onChange={(event) => setForm((prev) => ({ ...prev, quantity: event.target.value }))}
              placeholder={form.type === "buy" || form.type === "sell" ? "필수" : "비움"}
            />
          </label>
          <label>
            금액
            <input
              inputMode="decimal"
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
              placeholder="0"
            />
          </label>
          <label>
            원화 환율
            <input
              inputMode="decimal"
              value={form.fxRateToKrw}
              onChange={(event) => setForm((prev) => ({ ...prev, fxRateToKrw: event.target.value }))}
              placeholder="선택"
            />
          </label>
        </div>

        <label>
          메모
          <input
            value={form.memo}
            onChange={(event) => setForm((prev) => ({ ...prev, memo: event.target.value }))}
            placeholder="거래 설명"
          />
        </label>

        <button className="primary-button" type="submit">
          거래 저장
        </button>
        {error && <p className="form-message error-text">{error}</p>}
        {message && <p className="form-message success-text">{message}</p>}
      </form>

      <section className="panel">
        <div className="section-heading">
          <h3>거래 장부</h3>
          <span>{transactions.length.toLocaleString("ko-KR")}건</span>
        </div>
        {transactions.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>일자</th>
                  <th>유형</th>
                  <th>계좌</th>
                  <th>자산</th>
                  <th className="numeric-cell">수량</th>
                  <th className="numeric-cell">금액</th>
                  <th className="numeric-cell">환율</th>
                  <th>메모</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => (
                  <tr key={transaction.id}>
                    <td>{transaction.occurred_on}</td>
                    <td>{transactionTypeLabel(transaction.type)}</td>
                    <td>
                      {transaction.account_id === null
                        ? "삭제된 계좌"
                        : (accountNames.get(transaction.account_id) ?? transaction.account_id)}
                    </td>
                    <td>
                      {transaction.asset_id === null
                        ? "삭제된 자산"
                        : (assetNames.get(transaction.asset_id) ?? transaction.asset_id)}
                    </td>
                    <td className="numeric-cell">
                      {transaction.quantity === null ? "-" : formatNumber(transaction.quantity)}
                    </td>
                    <td className="numeric-cell">
                      {formatAmount(transaction.amount, transaction.currency)}
                    </td>
                    <td className="numeric-cell">
                      {transaction.fx_rate_to_krw === null ? "-" : formatNumber(transaction.fx_rate_to_krw)}
                    </td>
                    <td>{transaction.memo || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">저장된 거래가 없습니다.</p>
        )}
      </section>
    </section>
  )
}

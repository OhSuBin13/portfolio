import { useEffect, useState } from "react"
import { apiGet, apiPost } from "../api"
import type { Account, Asset, Transaction } from "../types"

const accountTypes = [
  ["cash", "현금"],
  ["savings", "예금"],
  ["brokerage", "증권"],
  ["crypto_wallet", "가상자산 지갑"],
  ["debt", "부채"],
]

const assetTypes = [
  ["cash", "현금"],
  ["savings", "예금"],
  ["stock_etf", "주식/ETF"],
  ["crypto", "가상자산"],
  ["debt", "부채"],
]

const today = () => new Date().toISOString().slice(0, 10)

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

type AccountForm = {
  name: string
  type: string
  currency: string
}

type AssetForm = {
  symbol: string
  name: string
  type: string
  currency: string
  market: string
}

type BalanceForm = {
  occurredOn: string
  accountId: string
  assetId: string
  amount: string
  currency: string
  memo: string
}

export function HoldingsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [loadError, setLoadError] = useState("")

  const [accountForm, setAccountForm] = useState<AccountForm>({
    name: "",
    type: "cash",
    currency: "KRW",
  })
  const [assetForm, setAssetForm] = useState<AssetForm>({
    symbol: "",
    name: "",
    type: "cash",
    currency: "KRW",
    market: "KR",
  })
  const [balanceForm, setBalanceForm] = useState<BalanceForm>({
    occurredOn: today(),
    accountId: "",
    assetId: "",
    amount: "",
    currency: "KRW",
    memo: "초기 잔액",
  })

  const [accountMessage, setAccountMessage] = useState("")
  const [accountError, setAccountError] = useState("")
  const [assetMessage, setAssetMessage] = useState("")
  const [assetError, setAssetError] = useState("")
  const [balanceMessage, setBalanceMessage] = useState("")
  const [balanceError, setBalanceError] = useState("")

  const refreshAccounts = async () => {
    const data = await apiGet<Account[]>("/api/accounts")
    setAccounts(data)
    return data
  }

  const refreshAssets = async () => {
    const data = await apiGet<Asset[]>("/api/assets")
    setAssets(data)
    return data
  }

  useEffect(() => {
    Promise.all([apiGet<Account[]>("/api/accounts"), apiGet<Asset[]>("/api/assets")])
      .then(([accountData, assetData]) => {
        setAccounts(accountData)
        setAssets(assetData)
        setLoadError("")
        setBalanceForm((prev) => ({
          ...prev,
          accountId: prev.accountId || (accountData[0] ? String(accountData[0].id) : ""),
          assetId: prev.assetId || (assetData[0] ? String(assetData[0].id) : ""),
        }))
      })
      .catch((err) => setLoadError(getErrorMessage(err)))
  }, [])

  const handleAccountSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAccountMessage("")
    setAccountError("")

    if (!accountForm.name.trim()) {
      setAccountError("계좌 이름을 입력하세요.")
      return
    }

    try {
      const created = await apiPost<Account>("/api/accounts", {
        name: accountForm.name.trim(),
        type: accountForm.type,
        currency: accountForm.currency.trim().toUpperCase(),
      })
      await refreshAccounts()
      setBalanceForm((prev) => ({ ...prev, accountId: String(created.id) }))
      setAccountForm((prev) => ({ ...prev, name: "" }))
      setAccountMessage("계좌를 만들었습니다.")
    } catch (err) {
      setAccountError(getErrorMessage(err))
    }
  }

  const handleAssetSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAssetMessage("")
    setAssetError("")

    if (!assetForm.name.trim()) {
      setAssetError("자산 이름을 입력하세요.")
      return
    }

    try {
      const created = await apiPost<Asset>("/api/assets", {
        symbol: assetForm.symbol.trim() || null,
        name: assetForm.name.trim(),
        type: assetForm.type,
        currency: assetForm.currency.trim().toUpperCase(),
        market: assetForm.market.trim().toUpperCase(),
      })
      await refreshAssets()
      setBalanceForm((prev) => ({ ...prev, assetId: String(created.id) }))
      setAssetForm((prev) => ({ ...prev, symbol: "", name: "" }))
      setAssetMessage("자산을 만들었습니다.")
    } catch (err) {
      setAssetError(getErrorMessage(err))
    }
  }

  const handleBalanceSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBalanceMessage("")
    setBalanceError("")

    const amount = Number(balanceForm.amount)
    const accountId = Number(balanceForm.accountId)
    const assetId = Number(balanceForm.assetId)

    if (!accountId || !assetId) {
      setBalanceError("계좌와 자산을 선택하세요.")
      return
    }

    if (!balanceForm.amount.trim() || !Number.isFinite(amount) || amount < 0) {
      setBalanceError("초기 금액은 0 이상 숫자로 입력하세요.")
      return
    }

    try {
      await apiPost<Transaction>("/api/transactions", {
        occurred_on: balanceForm.occurredOn,
        type: "adjustment",
        account_id: accountId,
        asset_id: assetId,
        quantity: null,
        amount,
        currency: balanceForm.currency.trim().toUpperCase(),
        memo: balanceForm.memo.trim(),
      })
      setBalanceForm((prev) => ({ ...prev, amount: "", memo: "초기 잔액" }))
      setBalanceMessage("초기 잔액을 반영했습니다.")
    } catch (err) {
      setBalanceError(getErrorMessage(err))
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>보유자산</h2>
        <p>계좌와 자산을 등록하고 시작 잔액을 맞춥니다.</p>
      </header>

      {loadError && <div className="error">{loadError}</div>}

      <div className="form-grid">
        <form className="panel form-panel" onSubmit={handleAccountSubmit}>
          <div className="section-heading">
            <h3>계좌 만들기</h3>
            <span>{accounts.length.toLocaleString("ko-KR")}개</span>
          </div>
          <label>
            계좌 이름
            <input
              value={accountForm.name}
              onChange={(event) => setAccountForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="예: 국민 생활비"
            />
          </label>
          <div className="field-row">
            <label>
              계좌 유형
              <select
                value={accountForm.type}
                onChange={(event) => setAccountForm((prev) => ({ ...prev, type: event.target.value }))}
              >
                {accountTypes.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              통화
              <input
                value={accountForm.currency}
                onChange={(event) =>
                  setAccountForm((prev) => ({ ...prev, currency: event.target.value }))
                }
              />
            </label>
          </div>
          <button className="primary-button" type="submit">
            계좌 저장
          </button>
          {accountError && <p className="form-message error-text">{accountError}</p>}
          {accountMessage && <p className="form-message success-text">{accountMessage}</p>}
        </form>

        <form className="panel form-panel" onSubmit={handleAssetSubmit}>
          <div className="section-heading">
            <h3>자산 만들기</h3>
            <span>{assets.length.toLocaleString("ko-KR")}개</span>
          </div>
          <label>
            자산 이름
            <input
              value={assetForm.name}
              onChange={(event) => setAssetForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="예: 삼성전자 보통주"
            />
          </label>
          <div className="field-row">
            <label>
              심볼
              <input
                value={assetForm.symbol}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, symbol: event.target.value }))}
                placeholder="선택"
              />
            </label>
            <label>
              자산 유형
              <select
                value={assetForm.type}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, type: event.target.value }))}
              >
                {assetTypes.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="field-row">
            <label>
              통화
              <input
                value={assetForm.currency}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, currency: event.target.value }))}
              />
            </label>
            <label>
              시장
              <input
                value={assetForm.market}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, market: event.target.value }))}
              />
            </label>
          </div>
          <button className="primary-button" type="submit">
            자산 저장
          </button>
          {assetError && <p className="form-message error-text">{assetError}</p>}
          {assetMessage && <p className="form-message success-text">{assetMessage}</p>}
        </form>
      </div>

      <form className="panel form-panel compact-form" onSubmit={handleBalanceSubmit}>
        <div className="section-heading">
          <h3>초기 잔액 반영</h3>
          <span>조정 거래</span>
        </div>
        <div className="field-row triple">
          <label>
            기준일
            <input
              type="date"
              value={balanceForm.occurredOn}
              onChange={(event) =>
                setBalanceForm((prev) => ({ ...prev, occurredOn: event.target.value }))
              }
            />
          </label>
          <label>
            계좌
            <select
              value={balanceForm.accountId}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, accountId: event.target.value }))}
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
              value={balanceForm.assetId}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, assetId: event.target.value }))}
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
            금액/수량
            <input
              inputMode="decimal"
              value={balanceForm.amount}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, amount: event.target.value }))}
              placeholder="0"
            />
          </label>
          <label>
            통화
            <input
              value={balanceForm.currency}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, currency: event.target.value }))}
            />
          </label>
          <label>
            메모
            <input
              value={balanceForm.memo}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, memo: event.target.value }))}
            />
          </label>
        </div>
        <button className="secondary-button" type="submit">
          초기 잔액 저장
        </button>
        {balanceError && <p className="form-message error-text">{balanceError}</p>}
        {balanceMessage && <p className="form-message success-text">{balanceMessage}</p>}
      </form>
    </section>
  )
}

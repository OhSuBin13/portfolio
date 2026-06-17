import { useEffect, useState } from "react"
import { apiDelete, apiGet, apiPost, apiPut } from "../api"
import type { Account, Asset, Transaction } from "../types"

const accountTypes = [
  ["cash", "현금"],
  ["savings", "예금"],
  ["brokerage", "증권"],
  ["debt", "부채"],
]

const assetTypes = [
  ["stock_etf", "주식/ETF"],
]

const initialTransactionTypes = [
  ["adjustment", "잔액/수량 조정"],
  ["buy", "초기 매수 보유"],
]

const today = () => {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const accountTypeLabel = (type: string) => accountTypes.find(([value]) => value === type)?.[1] ?? type

type AccountForm = {
  name: string
  type: string
}

type AssetForm = {
  symbol: string
  name: string
  type: string
  currency: string
  market: string
}

type BalanceForm = {
  type: string
  occurredOn: string
  accountId: string
  assetId: string
  quantity: string
  amount: string
  currency: string
  fxRateToKrw: string
  memo: string
}

type HoldingsView = "overview" | "account-detail"

const isStockEtfAsset = (asset: Asset | undefined) => asset?.type === "stock_etf"

const balanceFormForAsset = (form: BalanceForm, asset: Asset | undefined): BalanceForm => {
  if (isStockEtfAsset(asset)) {
    return form
  }

  if (form.type !== "buy" && !form.quantity) {
    return form
  }

  return {
    ...form,
    type: "adjustment",
    quantity: "",
    memo: form.type === "buy" ? "초기 잔액" : form.memo,
  }
}

export function HoldingsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [loadError, setLoadError] = useState("")
  const [holdingsView, setHoldingsView] = useState<HoldingsView>("overview")

  const [accountForm, setAccountForm] = useState<AccountForm>({
    name: "",
    type: "cash",
  })
  const [accountEditForm, setAccountEditForm] = useState<AccountForm>({
    name: "",
    type: "cash",
  })
  const [selectedAccountId, setSelectedAccountId] = useState("")
  const [assetForm, setAssetForm] = useState<AssetForm>({
    symbol: "",
    name: "",
    type: "stock_etf",
    currency: "USD",
    market: "US",
  })
  const [balanceForm, setBalanceForm] = useState<BalanceForm>({
    type: "adjustment",
    occurredOn: today(),
    accountId: "",
    assetId: "",
    quantity: "",
    amount: "",
    currency: "KRW",
    fxRateToKrw: "",
    memo: "초기 잔액",
  })

  const [accountMessage, setAccountMessage] = useState("")
  const [accountError, setAccountError] = useState("")
  const [accountManageMessage, setAccountManageMessage] = useState("")
  const [accountManageError, setAccountManageError] = useState("")
  const [assetMessage, setAssetMessage] = useState("")
  const [assetError, setAssetError] = useState("")
  const [balanceMessage, setBalanceMessage] = useState("")
  const [balanceError, setBalanceError] = useState("")
  const selectedBalanceAsset = assets.find((asset) => String(asset.id) === balanceForm.assetId)
  const showBalanceQuantity = selectedBalanceAsset?.type === "stock_etf"
  const availableInitialTransactionTypes = showBalanceQuantity
    ? initialTransactionTypes
    : initialTransactionTypes.filter(([value]) => value !== "buy")

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
        setBalanceForm((prev) => {
          const assetId = prev.assetId || (assetData[0] ? String(assetData[0].id) : "")
          return balanceFormForAsset(
            {
              ...prev,
              accountId: prev.accountId || (accountData[0] ? String(accountData[0].id) : ""),
              assetId,
            },
            assetData.find((asset) => String(asset.id) === assetId),
          )
        })
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
      })
      await refreshAccounts()
      setBalanceForm((prev) => ({ ...prev, accountId: String(created.id) }))
      setAccountForm((prev) => ({ ...prev, name: "" }))
      setAccountMessage("계좌를 만들었습니다.")
    } catch (err) {
      setAccountError(getErrorMessage(err))
    }
  }

  const clearSelectedAccount = () => {
    setSelectedAccountId("")
    setAccountEditForm({ name: "", type: "cash" })
  }

  const handleAccountSelect = async (accountId: number) => {
    setAccountManageMessage("")
    setAccountManageError("")

    try {
      const account = await apiGet<Account>(`/api/accounts/${accountId}`)
      setSelectedAccountId(String(account.id))
      setAccountEditForm({
        name: account.name,
        type: account.type,
      })
      setHoldingsView("account-detail")
    } catch (err) {
      setAccountManageError(getErrorMessage(err))
    }
  }

  const handleAccountDetailBack = () => {
    setAccountManageMessage("")
    setAccountManageError("")
    clearSelectedAccount()
    setHoldingsView("overview")
  }

  const handleAccountUpdate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAccountManageMessage("")
    setAccountManageError("")

    if (!selectedAccountId) {
      setAccountManageError("수정할 계좌를 선택하세요.")
      return
    }

    if (!accountEditForm.name.trim()) {
      setAccountManageError("계좌 이름을 입력하세요.")
      return
    }

    try {
      const updated = await apiPut<Account>(`/api/accounts/${selectedAccountId}`, {
        name: accountEditForm.name.trim(),
        type: accountEditForm.type,
      })
      await refreshAccounts()
      setSelectedAccountId(String(updated.id))
      setAccountEditForm({
        name: updated.name,
        type: updated.type,
      })
      setAccountManageMessage("계좌를 수정했습니다.")
    } catch (err) {
      setAccountManageError(getErrorMessage(err))
    }
  }

  const handleSelectedAccountDelete = async () => {
    if (!selectedAccountId) {
      setAccountManageError("삭제할 계좌를 선택하세요.")
      return
    }

    if (!window.confirm("계좌를 삭제할까요? 연결된 보유자산도 함께 정리됩니다.")) {
      return
    }

    setAccountManageMessage("")
    setAccountManageError("")

    try {
      await apiDelete(`/api/accounts/${selectedAccountId}`)
      const nextAccounts = await refreshAccounts()
      const fallbackAccountId = nextAccounts[0] ? String(nextAccounts[0].id) : ""
      const deletedAccountId = selectedAccountId

      clearSelectedAccount()
      setHoldingsView("overview")

      setBalanceForm((prev) => {
        const currentStillExists = nextAccounts.some((account) => String(account.id) === prev.accountId)
        return {
          ...prev,
          accountId:
            currentStillExists && prev.accountId !== deletedAccountId ? prev.accountId : fallbackAccountId,
        }
      })
      setAccountManageMessage("계좌를 삭제했습니다.")
    } catch (err) {
      setAccountManageError(getErrorMessage(err))
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
      const nextAssets = await refreshAssets()
      const createdAsset = nextAssets.find((asset) => asset.id === created.id)
      setBalanceForm((prev) =>
        balanceFormForAsset({ ...prev, assetId: String(created.id) }, createdAsset),
      )
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
    const quantity = Number(balanceForm.quantity)
    const fxRateToKrw = balanceForm.fxRateToKrw.trim() ? Number(balanceForm.fxRateToKrw) : null
    const isBuy = showBalanceQuantity && balanceForm.type === "buy"

    if (!accountId || !assetId) {
      setBalanceError("계좌와 자산을 선택하세요.")
      return
    }

    if (isBuy && (!balanceForm.quantity.trim() || !Number.isFinite(quantity) || quantity <= 0)) {
      setBalanceError("초기 매수 보유는 0보다 큰 수량이 필요합니다.")
      return
    }

    if (!balanceForm.amount.trim() || !Number.isFinite(amount) || amount < 0) {
      setBalanceError(
        isBuy ? "초기 매수 금액은 0보다 큰 숫자로 입력하세요." : "조정 금액은 0 이상 숫자로 입력하세요.",
      )
      return
    }

    if (isBuy && amount <= 0) {
      setBalanceError("초기 매수 금액은 0보다 큰 숫자로 입력하세요.")
      return
    }

    if (fxRateToKrw !== null && (!Number.isFinite(fxRateToKrw) || fxRateToKrw <= 0)) {
      setBalanceError("환율은 비워두거나 0보다 큰 숫자로 입력하세요.")
      return
    }

    try {
      await apiPost<Transaction>("/api/transactions", {
        occurred_on: balanceForm.occurredOn,
        type: isBuy ? "buy" : "adjustment",
        account_id: accountId,
        asset_id: assetId,
        quantity: isBuy ? quantity : null,
        amount,
        currency: balanceForm.currency.trim().toUpperCase(),
        memo: balanceForm.memo.trim(),
        fx_rate_to_krw: fxRateToKrw,
      })
      setBalanceForm((prev) => ({
        ...prev,
        quantity: "",
        amount: "",
        fxRateToKrw: "",
        memo: prev.type === "buy" ? "초기 매수" : "초기 잔액",
      }))
      setBalanceMessage("초기 거래를 저장했습니다.")
    } catch (err) {
      setBalanceError(getErrorMessage(err))
    }
  }

  if (holdingsView === "account-detail") {
    return (
      <section className="screen-stack" data-api="get_account" data-view="account-detail">
        <header className="page-header">
          <button className="secondary-button" type="button" onClick={handleAccountDetailBack}>
            목록으로
          </button>
          <h2>계좌 상세</h2>
          <p>{selectedAccountId ? `계좌 #${selectedAccountId}` : "계좌를 다시 선택해 주세요."}</p>
        </header>

        <form className="panel form-panel narrow-form" onSubmit={handleAccountUpdate}>
          <div className="section-heading">
            <h3>계좌 수정</h3>
            <span>{selectedAccountId ? "수정/삭제 가능" : "선택 없음"}</span>
          </div>
          <label>
            계좌 이름
            <input
              value={accountEditForm.name}
              onChange={(event) =>
                setAccountEditForm((prev) => ({ ...prev, name: event.target.value }))
              }
              disabled={!selectedAccountId}
              placeholder="수정할 계좌를 선택하세요"
            />
          </label>
          <label>
            계좌 유형
            <select
              value={accountEditForm.type}
              onChange={(event) =>
                setAccountEditForm((prev) => ({ ...prev, type: event.target.value }))
              }
              disabled={!selectedAccountId}
            >
              {accountTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="action-row">
            <button className="secondary-button" type="submit" disabled={!selectedAccountId}>
              수정 저장
            </button>
            <button
              className="danger-button"
              type="button"
              disabled={!selectedAccountId}
              onClick={handleSelectedAccountDelete}
            >
              삭제
            </button>
          </div>
          {accountManageError && <p className="form-message error-text">{accountManageError}</p>}
          {accountManageMessage && <p className="form-message success-text">{accountManageMessage}</p>}
        </form>
      </section>
    )
  }

  return (
    <section className="screen-stack" data-view="holdings-overview">
      <header className="page-header">
        <h2>보유자산</h2>
        <p>계좌와 자산을 등록하고 시작 잔액을 맞춥니다.</p>
      </header>

      {loadError && <div className="error">{loadError}</div>}

      <div className="form-grid">
        <section className="panel form-panel">
          <form className="form-panel" onSubmit={handleAccountSubmit}>
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
            <button className="primary-button" type="submit">
              계좌 저장
            </button>
            {accountError && <p className="form-message error-text">{accountError}</p>}
            {accountMessage && <p className="form-message success-text">{accountMessage}</p>}
          </form>

          <div className="panel-divider" />

          <div className="account-management" data-api="list_accounts">
            <div className="section-heading">
              <h3>계좌 목록</h3>
              <span>{accounts.length.toLocaleString("ko-KR")}개</span>
            </div>

            {accounts.length === 0 ? (
              <p className="empty-state">등록된 계좌가 없습니다.</p>
            ) : (
              <div className="account-list">
                {accounts.map((account) => (
                  <div className="account-row" key={account.id}>
                    <div>
                      <strong>{account.name}</strong>
                      <span>{accountTypeLabel(account.type)}</span>
                    </div>
                    <div className="row-actions">
                      <button
                        className="secondary-button compact-button"
                        type="button"
                        onClick={() => handleAccountSelect(account.id)}
                      >
                        관리
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {accountManageError && <p className="form-message error-text">{accountManageError}</p>}
            {accountManageMessage && <p className="form-message success-text">{accountManageMessage}</p>}
          </div>
        </section>

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
              <select
                value={assetForm.currency}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, currency: event.target.value }))}
              >
                <option value="KRW">KRW</option>
                <option value="USD">USD</option>
              </select>
            </label>
            <label>
              시장
              <select
                value={assetForm.market}
                onChange={(event) => setAssetForm((prev) => ({ ...prev, market: event.target.value }))}
              >
                <option value="US">US</option>
              </select>
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
          <h3>초기 잔액/보유 반영</h3>
          <span>{showBalanceQuantity && balanceForm.type === "buy" ? "매수 거래" : "조정 거래"}</span>
        </div>
        <div className="field-row triple">
          <label>
            반영 방식
            <select
              value={balanceForm.type}
              onChange={(event) =>
                setBalanceForm((prev) => ({
                  ...prev,
                  type: event.target.value,
                  memo: event.target.value === "buy" ? "초기 매수" : "초기 잔액",
                }))
              }
            >
              {availableInitialTransactionTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
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
            통화
            <select
              value={balanceForm.currency}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, currency: event.target.value }))}
            >
              <option value="KRW">KRW</option>
              <option value="USD">USD</option>
            </select>
          </label>
        </div>
        <div className="field-row triple">
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
              onChange={(event) => {
                const assetId = event.target.value
                const nextAsset = assets.find((asset) => String(asset.id) === assetId)
                setBalanceForm((prev) => balanceFormForAsset({ ...prev, assetId }, nextAsset))
              }}
            >
              <option value="">선택</option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.symbol ? `${asset.name} (${asset.symbol})` : asset.name}
                </option>
              ))}
            </select>
          </label>
          {showBalanceQuantity && (
            <label>
              수량
              <input
                inputMode="decimal"
                value={balanceForm.quantity}
                onChange={(event) =>
                  setBalanceForm((prev) => ({ ...prev, quantity: event.target.value }))
                }
                placeholder={balanceForm.type === "buy" ? "필수" : "비움"}
              />
            </label>
          )}
        </div>
        <div className="field-row triple">
          <label>
            {balanceForm.type === "buy" ? "금액" : showBalanceQuantity ? "목표 잔액/수량" : "목표 잔액"}
            <input
              inputMode="decimal"
              value={balanceForm.amount}
              onChange={(event) => setBalanceForm((prev) => ({ ...prev, amount: event.target.value }))}
              placeholder="0"
            />
          </label>
          <label>
            원화 환율
            <input
              inputMode="decimal"
              value={balanceForm.fxRateToKrw}
              onChange={(event) =>
                setBalanceForm((prev) => ({ ...prev, fxRateToKrw: event.target.value }))
              }
              placeholder="선택"
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
          초기 거래 저장
        </button>
        {balanceError && <p className="form-message error-text">{balanceError}</p>}
        {balanceMessage && <p className="form-message success-text">{balanceMessage}</p>}
      </form>
    </section>
  )
}

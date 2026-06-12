import { useState } from "react"
import { apiPost, apiUpload } from "../api"
import type { ImportConfirmResult, ImportPreview } from "../types"

const today = () => {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatKrw = (value: number) => `${value.toLocaleString("ko-KR")} 원`

export function ImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [occurredOn, setOccurredOn] = useState(today())
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [previewMessage, setPreviewMessage] = useState("")
  const [previewError, setPreviewError] = useState("")
  const [confirmMessage, setConfirmMessage] = useState("")
  const [confirmError, setConfirmError] = useState("")
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null)
    setPreview(null)
    setPreviewMessage("")
    setPreviewError("")
    setConfirmMessage("")
    setConfirmError("")
  }

  const handlePreviewSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPreviewMessage("")
    setPreviewError("")
    setConfirmMessage("")
    setConfirmError("")

    if (!file) {
      setPreviewError("CSV 파일을 선택하세요.")
      return
    }

    try {
      setIsPreviewing(true)
      const data = await apiUpload<ImportPreview>("/api/imports/preview", file)
      setPreview(data)
      setPreviewMessage(
        `미리보기 완료: 반영 ${data.mapped_rows.length.toLocaleString("ko-KR")}행, 제외 ${data.ignored_rows.length.toLocaleString("ko-KR")}행`,
      )
    } catch (err) {
      setPreview(null)
      setPreviewError(getErrorMessage(err))
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleConfirm = async () => {
    setConfirmMessage("")
    setConfirmError("")

    if (!preview) {
      setConfirmError("먼저 CSV 미리보기를 실행하세요.")
      return
    }

    if (preview.mapped_rows.length === 0) {
      setConfirmError("반영할 행이 없습니다.")
      return
    }

    if (!occurredOn) {
      setConfirmError("반영일을 선택하세요.")
      return
    }

    try {
      setIsConfirming(true)
      const result = await apiPost<ImportConfirmResult>("/api/imports/confirm", {
        occurred_on: occurredOn,
        mapped_rows: preview.mapped_rows,
      })
      setConfirmMessage(
        `가져오기를 완료했습니다. 계좌 ${result.created_accounts.toLocaleString("ko-KR")}개, 자산 ${result.created_assets.toLocaleString("ko-KR")}개, 보유 ${result.created_holdings.toLocaleString("ko-KR")}개, 거래 ${result.created_transactions.toLocaleString("ko-KR")}개를 반영했습니다. 백업: ${result.backup_path}`,
      )
    } catch (err) {
      setConfirmError(getErrorMessage(err))
    } finally {
      setIsConfirming(false)
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>가져오기</h2>
        <p>스프레드시트에서 내보낸 CSV를 확인한 뒤 반영합니다.</p>
      </header>

      <form className="panel form-panel" onSubmit={handlePreviewSubmit}>
        <div className="section-heading">
          <h3>CSV 미리보기</h3>
          <span>{file ? file.name : "파일 없음"}</span>
        </div>
        <div className="field-row">
          <label>
            CSV 파일
            <input accept=".csv,text/csv" onChange={handleFileChange} type="file" />
          </label>
          <label>
            반영일
            <input
              onChange={(event) => setOccurredOn(event.target.value)}
              type="date"
              value={occurredOn}
            />
          </label>
        </div>
        <div className="action-row">
          <button className="secondary-button" disabled={isPreviewing} type="submit">
            {isPreviewing ? "확인 중" : "미리보기"}
          </button>
          <button
            className="primary-button"
            disabled={isConfirming || !preview || preview.mapped_rows.length === 0}
            onClick={handleConfirm}
            type="button"
          >
            {isConfirming ? "가져오는 중" : "백업 후 가져오기"}
          </button>
        </div>
        {previewError && <p className="form-message error-text">{previewError}</p>}
        {previewMessage && <p className="form-message success-text">{previewMessage}</p>}
        {confirmError && <p className="form-message error-text">{confirmError}</p>}
        {confirmMessage && <p className="form-message success-text">{confirmMessage}</p>}
      </form>

      {preview && (
        <section className="panel">
          <div className="section-heading">
            <h3>미리보기 결과</h3>
            <span>
              반영 {preview.mapped_rows.length.toLocaleString("ko-KR")}행 / 제외{" "}
              {preview.ignored_rows.length.toLocaleString("ko-KR")}행
            </span>
          </div>

          {preview.mapped_rows.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>행</th>
                    <th>자산 유형</th>
                    <th>이름</th>
                    <th>평가액</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.mapped_rows.map((row) => (
                    <tr key={`${row.row_number}-${row.name}`}>
                      <td>{row.row_number.toLocaleString("ko-KR")}</td>
                      <td>{row.asset_type}</td>
                      <td>{row.symbol ? `${row.name} (${row.symbol})` : row.name}</td>
                      <td className="numeric-cell">{formatKrw(row.value_krw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-state">반영 가능한 행이 없습니다.</p>
          )}
        </section>
      )}

      {preview && preview.ignored_rows.length > 0 && (
        <section className="panel">
          <div className="section-heading">
            <h3>제외된 행</h3>
            <span>{preview.ignored_rows.length.toLocaleString("ko-KR")}행</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>행</th>
                  <th>메시지</th>
                </tr>
              </thead>
              <tbody>
                {preview.ignored_rows.map((row) => (
                  <tr key={`${row.row_number}-${row.message}`}>
                    <td>{row.row_number.toLocaleString("ko-KR")}</td>
                    <td>{row.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  )
}

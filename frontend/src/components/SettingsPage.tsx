import { useCallback, useEffect, useState } from "react"
import { apiGet, apiPost } from "../api"
import type { BackupRecord, MarketDataStatus } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatKrw = (value: number | null) =>
  value === null ? "-" : `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원`

const latestBackupFrom = (records: BackupRecord[]) =>
  records.reduce<BackupRecord | null>(
    (latest, record) => (!latest || record.created_at > latest.created_at ? record : latest),
    null,
  )

export function SettingsPage() {
  const [alphaVantageKey, setAlphaVantageKey] = useState("")
  const [backups, setBackups] = useState<BackupRecord[]>([])
  const [marketStatuses, setMarketStatuses] = useState<MarketDataStatus[]>([])
  const [loadError, setLoadError] = useState("")
  const [backupMessage, setBackupMessage] = useState("")
  const [backupError, setBackupError] = useState("")
  const [isBackingUp, setIsBackingUp] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const refreshBackups = useCallback(async () => {
    const data = await apiGet<BackupRecord[]>("/api/backups")
    setBackups(data)
    return data
  }, [])

  const refreshMarketStatuses = useCallback(async () => {
    const data = await apiGet<MarketDataStatus[]>("/api/market-data/status")
    setMarketStatuses(data)
    return data
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshBackups(), refreshMarketStatuses()])
  }, [refreshBackups, refreshMarketStatuses])

  useEffect(() => {
    Promise.all([
      apiGet<BackupRecord[]>("/api/backups"),
      apiGet<MarketDataStatus[]>("/api/market-data/status"),
    ])
      .then(([backupData, marketData]) => {
        setBackups(backupData)
        setMarketStatuses(marketData)
        setLoadError("")
      })
      .catch((err) => setLoadError(getErrorMessage(err)))
  }, [])

  const handleBackup = async () => {
    setBackupMessage("")
    setBackupError("")

    try {
      setIsBackingUp(true)
      const created = await apiPost<BackupRecord>("/api/backups")
      await refreshBackups()
      setBackupMessage(`백업을 만들었습니다. 경로: ${created.path}`)
    } catch (err) {
      setBackupError(getErrorMessage(err))
    } finally {
      setIsBackingUp(false)
    }
  }

  const handleRefresh = async () => {
    setLoadError("")

    try {
      setIsRefreshing(true)
      await refreshAll()
    } catch (err) {
      setLoadError(getErrorMessage(err))
    } finally {
      setIsRefreshing(false)
    }
  }

  const latestBackup = latestBackupFrom(backups)

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>설정</h2>
        <p>시세 상태, 백업, 서버 설정 상태를 관리합니다.</p>
      </header>

      {loadError && <div className="error">{loadError}</div>}

      <section className="panel form-panel narrow-form">
        <div className="section-heading">
          <h3>Alpha Vantage</h3>
          <span>로컬 입력</span>
        </div>
        <label>
          Alpha Vantage API 키
          <input
            autoComplete="off"
            onChange={(event) => setAlphaVantageKey(event.target.value)}
            placeholder="서버 저장 미지원"
            type="password"
            value={alphaVantageKey}
          />
        </label>
        <p className="form-message">
          {alphaVantageKey
            ? "입력한 키는 현재 화면 상태에만 보관되며 서버로 전송하거나 저장하지 않습니다."
            : "백엔드는 서버 설정 또는 환경 변수의 키를 사용합니다. 이 입력값은 아직 저장되지 않습니다."}
        </p>
      </section>

      <div className="form-grid">
        <section className="panel form-panel">
          <div className="section-heading">
            <h3>자동 시세 갱신</h3>
            <span>{marketStatuses.length.toLocaleString("ko-KR")}개 상태</span>
          </div>
          <p className="form-message">
            백엔드가 앱 실행 중 5분마다 시세를 자동으로 갱신합니다. 이 화면에서는 최신 상태를 확인합니다.
          </p>
          <div className="action-row">
            <button
              className="secondary-button"
              disabled={isRefreshing}
              onClick={handleRefresh}
              type="button"
            >
              {isRefreshing ? "새로고침 중" : "상태 새로고침"}
            </button>
          </div>
        </section>

        <section className="panel form-panel">
          <div className="section-heading">
            <h3>백업</h3>
            <span>{backups.length.toLocaleString("ko-KR")}개</span>
          </div>
          <button className="secondary-button" disabled={isBackingUp} onClick={handleBackup} type="button">
            {isBackingUp ? "백업 중" : "수동 백업 만들기"}
          </button>
          {backupError && <p className="form-message error-text">{backupError}</p>}
          {backupMessage && <p className="form-message success-text">{backupMessage}</p>}
          {latestBackup ? (
            <div className="mix-list">
              <div className="mix-row">
                <span>최근 경로</span>
                <strong>{latestBackup.path}</strong>
              </div>
              <div className="mix-row">
                <span>사유</span>
                <strong>{latestBackup.reason}</strong>
              </div>
              <div className="mix-row">
                <span>생성 시각</span>
                <strong>{latestBackup.created_at}</strong>
              </div>
            </div>
          ) : (
            <p className="empty-state">백업 기록이 없습니다.</p>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="section-heading">
          <h3>시세 상태</h3>
          <span>{marketStatuses.length.toLocaleString("ko-KR")}개 자산</span>
        </div>
        {marketStatuses.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>자산 ID</th>
                  <th>소스</th>
                  <th>가격</th>
                  <th>상태</th>
                  <th>오류</th>
                  <th>수집 시각</th>
                </tr>
              </thead>
              <tbody>
                {marketStatuses.map((status) => (
                  <tr key={`${status.asset_id}-${status.source}`}>
                    <td>{status.asset_id.toLocaleString("ko-KR")}</td>
                    <td>{status.source}</td>
                    <td className="numeric-cell">{formatKrw(status.price_krw)}</td>
                    <td>{status.status}</td>
                    <td>{status.error_message || "-"}</td>
                    <td>{status.fetched_at || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">시세 상태가 없습니다.</p>
        )}
      </section>
    </section>
  )
}

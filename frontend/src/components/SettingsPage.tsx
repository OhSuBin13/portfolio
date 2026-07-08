import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { BackupRecord, BackupStatus } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatBackupInterval = (seconds: number) => {
  const totalSeconds = Math.max(1, Math.round(seconds))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const remainingSeconds = totalSeconds % 60
  const parts: string[] = []

  if (hours > 0) {
    parts.push(`${hours.toLocaleString("ko-KR")}시간`)
  }
  if (minutes > 0) {
    parts.push(`${minutes.toLocaleString("ko-KR")}분`)
  }
  if (remainingSeconds > 0 || parts.length === 0) {
    parts.push(`${remainingSeconds.toLocaleString("ko-KR")}초`)
  }

  return parts.join(" ")
}

const latestBackupFrom = (records: BackupRecord[]) =>
  records.reduce<BackupRecord | null>(
    (latest, record) => (!latest || record.created_at > latest.created_at ? record : latest),
    null,
  )

export function SettingsPage() {
  const [backups, setBackups] = useState<BackupRecord[]>([])
  const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null)
  const [loadError, setLoadError] = useState("")

  useEffect(() => {
    let ignore = false

    Promise.all([
      apiGet<BackupRecord[]>("/api/backups"),
      apiGet<BackupStatus>("/api/backups/status"),
    ])
      .then(([backupData, statusData]) => {
        if (ignore) {
          return
        }

        setBackups(backupData)
        setBackupStatus(statusData)
        setLoadError("")
      })
      .catch((err) => {
        if (!ignore) {
          setBackupStatus(null)
          setLoadError(getErrorMessage(err))
        }
      })

    return () => {
      ignore = true
    }
  }, [])

  const latestBackup = latestBackupFrom(backups)
  const backupStatusMessage =
    backupStatus === null
      ? "백업 설정을 불러오는 중입니다."
      : backupStatus.enabled
        ? `백엔드가 앱 실행 중 ${formatBackupInterval(backupStatus.interval_seconds)}마다 백업을 자동으로 만듭니다. 이 화면은 서버에 저장된 백업 기록을 조회합니다.`
        : "백엔드의 주기 자동 백업이 꺼져 있습니다. 앱 시작 백업과 서버에 저장된 백업 기록은 계속 확인할 수 있습니다."

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>설정</h2>
        <p>Toss API 인증 정보와 백업 상태를 확인합니다.</p>
      </header>

      {loadError && <div className="error">{loadError}</div>}

      <div className="form-grid">
        <section className="panel form-panel">
          <div className="section-heading">
            <h3>Toss API 인증 정보</h3>
            <span>서버 환경 변수</span>
          </div>
          <p className="form-message">
            Toss 계좌, 보유자산, USD/KRW 환율 조회에는 백엔드에 설정된 Toss API 인증 정보가
            필요합니다. 계좌가 보이지 않으면 서버 환경 변수와 Toss Open API 권한을 확인하세요.
          </p>
        </section>

        <section className="panel form-panel">
          <div className="section-heading">
            <h3>자동 백업</h3>
            <span>{backups.length.toLocaleString("ko-KR")}개</span>
          </div>
          <p className="form-message">{backupStatusMessage}</p>
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
    </section>
  )
}

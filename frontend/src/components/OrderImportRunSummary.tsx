import type { TossOrderImportRun } from "../types"

type OrderImportRunSummaryProps = {
  latestImportRun: TossOrderImportRun | null
  formatDateTime: (value: string | null) => string
}

export function OrderImportRunSummary({
  latestImportRun,
  formatDateTime,
}: OrderImportRunSummaryProps) {
  if (!latestImportRun) {
    return <p className="empty-state">가져오기 이력이 없습니다.</p>
  }

  return (
    <div className="mix-list">
      <div className="mix-row">
        <span>상태</span>
        <strong>{latestImportRun.run_status}</strong>
      </div>
      <div className="mix-row">
        <span>필터</span>
        <strong>
          {latestImportRun.status_filter}
          {latestImportRun.symbol_filter ? ` / ${latestImportRun.symbol_filter}` : ""}
        </strong>
      </div>
      <div className="mix-row">
        <span>가져온 주문</span>
        <strong>{latestImportRun.imported_count.toLocaleString("ko-KR")}건</strong>
      </div>
      <div className="mix-row">
        <span>시작 시각</span>
        <strong>{formatDateTime(latestImportRun.started_at)}</strong>
      </div>
      <div className="mix-row">
        <span>완료 시각</span>
        <strong>{formatDateTime(latestImportRun.completed_at)}</strong>
      </div>
      {latestImportRun.error_message && (
        <div className="mix-row">
          <span>오류</span>
          <strong>{latestImportRun.error_message}</strong>
        </div>
      )}
    </div>
  )
}

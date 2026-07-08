import {
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react"
import { Plus, X } from "lucide-react"
import { formatChartDateTime } from "../chartDates"
import type { TradeMarker } from "../chartMarkers"
import type { TossHolding } from "../types"

type MarkerMemoPriceFormatter = (
  value: number,
  currency: TossHolding["currency"] | undefined,
) => string

type MarkerMemoDrawerProps = {
  selectedMarker: TradeMarker | undefined
  selectedHolding: TossHolding | undefined
  memoMarkers: TradeMarker[]
  selectedMarkerKey: string
  memoListExpanded: boolean
  memoManageMode: boolean
  formatPrice: MarkerMemoPriceFormatter
  onDeleteMarkerMemo: (event: ReactMouseEvent<HTMLButtonElement>, marker: TradeMarker) => void
  onMemoListItemKeyDown: (event: KeyboardEvent<HTMLDivElement>, marker: TradeMarker) => void
  onOpenMarkerMemoDetail: (marker: TradeMarker) => void
  onOpenMarkerMemoDialog: () => void
  onToggleMemoListExpanded: () => void
  onToggleMemoManageMode: () => void
}

export function MarkerMemoDrawer({
  selectedMarker,
  selectedHolding,
  memoMarkers,
  selectedMarkerKey,
  memoListExpanded,
  memoManageMode,
  formatPrice,
  onDeleteMarkerMemo,
  onMemoListItemKeyDown,
  onOpenMarkerMemoDetail,
  onOpenMarkerMemoDialog,
  onToggleMemoListExpanded,
  onToggleMemoManageMode,
}: MarkerMemoDrawerProps) {
  return (
    <div className="marker-memo-drawer">
      <button
        aria-expanded={memoListExpanded}
        aria-label={memoListExpanded ? "작성된 판단 메모 접기" : "작성된 판단 메모 펼치기"}
        className="marker-memo-toggle"
        onClick={onToggleMemoListExpanded}
        title={memoListExpanded ? "작성된 판단 메모 접기" : "작성된 판단 메모 펼치기"}
        type="button"
      >
        {memoListExpanded ? ">>" : "<<"}
      </button>
      {selectedMarker && (
        <button
          aria-label="선택한 매매 마커 판단 메모 작성"
          className="icon-button marker-memo-compose-button"
          onClick={onOpenMarkerMemoDialog}
          title="선택한 매매 마커 판단 메모 작성"
          type="button"
        >
          <Plus size={17} />
        </button>
      )}
      {memoListExpanded && (
        <aside className="marker-memo-list-panel" aria-label="작성된 판단 메모">
          <div className="marker-memo-list-heading">
            <div>
              <h4>작성된 판단 메모</h4>
              <span>{memoMarkers.length.toLocaleString("ko-KR")}건</span>
            </div>
            <button
              aria-label="작성된 판단 메모 관리"
              aria-pressed={memoManageMode}
              className={`secondary-button marker-memo-manage-button${memoManageMode ? " active" : ""}`}
              onClick={onToggleMemoManageMode}
              title={memoManageMode ? "삭제 모드 끄기" : "삭제 모드 켜기"}
              type="button"
            >
              관리
            </button>
          </div>
          {memoMarkers.length > 0 && selectedHolding ? (
            <div className="marker-memo-list">
              {memoMarkers.map((marker) => (
                <div
                  className={`marker-memo-list-item marker-memo-list-item-${marker.tone}${
                    selectedMarkerKey === marker.key ? " selected" : ""
                  }${memoManageMode ? " manage-mode" : ""}`}
                  key={marker.key}
                  onClick={() => onOpenMarkerMemoDetail(marker)}
                  onKeyDown={(event) => onMemoListItemKeyDown(event, marker)}
                  role="button"
                  tabIndex={0}
                >
                  <span className="marker-memo-list-item-body">
                    <span className="marker-memo-list-item-header">
                      <span className={`marker-memo-list-badge marker-memo-list-badge-${marker.tone}`}>
                        {marker.label}
                      </span>
                      <time>{formatChartDateTime(marker.timestamp)}</time>
                    </span>
                    <strong>{formatPrice(marker.price, selectedHolding.currency)}</strong>
                    <span className="marker-memo-preview">{marker.memo.trim()}</span>
                  </span>
                  {memoManageMode && (
                    <button
                      aria-label={`${marker.label} 판단 메모 삭제`}
                      className="icon-button marker-memo-delete-button"
                      onClick={(event) => onDeleteMarkerMemo(event, marker)}
                      title="판단 메모 삭제"
                      type="button"
                    >
                      <X size={15} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state compact-empty">작성된 판단 메모가 없습니다.</p>
          )}
        </aside>
      )}
    </div>
  )
}

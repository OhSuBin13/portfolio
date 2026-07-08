import { Calendar, DollarSign, Hash, Save, StickyNote, X } from "lucide-react"
import { formatChartDateTime } from "../chartDates"
import type { TradeMarker } from "../chartMarkers"
import type { TossHolding } from "../types"

type MarkerMemoPriceFormatter = (
  value: number,
  currency: TossHolding["currency"] | undefined,
) => string

type MarkerMemoDialogProps = {
  selectedMarker: TradeMarker
  currency: TossHolding["currency"] | undefined
  markerMemoDraft: string
  memoSaving: boolean
  formatPrice: MarkerMemoPriceFormatter
  onClose: () => void
  onDraftChange: (value: string) => void
  onSave: () => void
}

export function MarkerMemoDialog({
  selectedMarker,
  currency,
  markerMemoDraft,
  memoSaving,
  formatPrice,
  onClose,
  onDraftChange,
  onSave,
}: MarkerMemoDialogProps) {
  return (
    <div className="marker-memo-overlay">
      <section
        aria-label="판단 메모 세부 정보"
        aria-modal="true"
        className="panel marker-memo-dialog"
        role="dialog"
      >
        <div className="section-heading marker-memo-dialog-heading">
          <div>
            <h3>판단 메모 세부 정보</h3>
            <span>{selectedMarker.label} 판단 기록</span>
          </div>
          <button
            aria-label="판단 메모 작성 화면 닫기"
            className="icon-button"
            onClick={onClose}
            title="판단 메모 작성 화면 닫기"
            type="button"
          >
            <X size={16} />
          </button>
        </div>
        <div className="marker-memo-panel">
          <div className={`marker-selected-header marker-selected-header-${selectedMarker.tone}`}>
            <div>
              <span className="marker-selected-badge">{selectedMarker.label}</span>
              <h4>{selectedMarker.label} 판단 기록</h4>
              <p>{formatChartDateTime(selectedMarker.timestamp)}</p>
            </div>
            <div className="marker-selected-price">
              <span>체결가</span>
              <strong>{formatPrice(selectedMarker.price, currency)}</strong>
            </div>
          </div>

          <div className="marker-detail-grid">
            <div className="marker-detail-item">
              <Calendar size={18} />
              <div>
                <span>시점</span>
                <strong>{formatChartDateTime(selectedMarker.timestamp)}</strong>
              </div>
            </div>
            <div className="marker-detail-item">
              <DollarSign size={18} />
              <div>
                <span>가격</span>
                <strong>{formatPrice(selectedMarker.price, currency)}</strong>
              </div>
            </div>
            <div className="marker-detail-item">
              <Hash size={18} />
              <div>
                <span>수량</span>
                <strong>{selectedMarker.quantity}</strong>
              </div>
            </div>
          </div>

          <label className="marker-note-field">
            <span>
              <StickyNote size={16} />
              판단 메모
            </span>
            <textarea
              onChange={(event) => onDraftChange(event.target.value)}
              placeholder={`${selectedMarker.label} 판단 근거, 리스크, 다음 행동을 적어두세요.`}
              rows={4}
              value={markerMemoDraft}
            />
          </label>
          <div className="marker-note-actions">
            <span className="marker-note-state">
              {markerMemoDraft.trim() ? "메모 작성 중" : "메모 없음"}
            </span>
            <button
              className="primary-button compact-button"
              disabled={memoSaving}
              onClick={onSave}
              type="button"
            >
              <Save size={16} />
              저장
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

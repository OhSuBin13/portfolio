import { type MouseEvent as ReactMouseEvent } from "react"
import { Plus, Trash2, X } from "lucide-react"
import type { MovingAverageConfig } from "./CandleChart"

export type MovingAverageForm = {
  days: string
  color: string
  lineWidth: string
}

type ChartSettingsDialogProps = {
  movingAverageConfigs: MovingAverageConfig[]
  movingAverageForm: MovingAverageForm
  showVolume: boolean
  onAddMovingAverage: () => void
  onClose: () => void
  onMovingAverageFormChange: (form: MovingAverageForm) => void
  onRemoveMovingAverage: (id: string) => void
  onShowVolumeChange: (showVolume: boolean) => void
}

export function ChartSettingsDialog({
  movingAverageConfigs,
  movingAverageForm,
  showVolume,
  onAddMovingAverage,
  onClose,
  onMovingAverageFormChange,
  onRemoveMovingAverage,
  onShowVolumeChange,
}: ChartSettingsDialogProps) {
  const onBackdropMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose()
    }
  }

  return (
    <div className="chart-settings-overlay" onMouseDown={onBackdropMouseDown}>
      <section
        aria-label="차트 설정"
        aria-modal="true"
        className="panel chart-settings-panel chart-settings-dialog"
        role="dialog"
      >
        <div className="section-heading chart-settings-heading">
          <div>
            <h3>설정</h3>
            <span>{movingAverageConfigs.length.toLocaleString("ko-KR")}개 이동평균</span>
          </div>
          <button
            aria-label="차트 설정 닫기"
            className="icon-button"
            onClick={onClose}
            title="차트 설정 닫기"
            type="button"
          >
            <X size={16} />
          </button>
        </div>
        <div className="chart-settings-grid">
          <label className="checkbox-label">
            <input
              checked={showVolume}
              onChange={(event) => onShowVolumeChange(event.target.checked)}
              type="checkbox"
            />
            거래량
          </label>
          <div className="moving-average-form">
            <label>
              일 수
              <input
                min={2}
                max={400}
                onChange={(event) =>
                  onMovingAverageFormChange({ ...movingAverageForm, days: event.target.value })
                }
                type="number"
                value={movingAverageForm.days}
              />
            </label>
            <label>
              색깔
              <input
                onChange={(event) =>
                  onMovingAverageFormChange({ ...movingAverageForm, color: event.target.value })
                }
                type="color"
                value={movingAverageForm.color}
              />
            </label>
            <label>
              선 굵기
              <input
                min={1}
                max={6}
                onChange={(event) =>
                  onMovingAverageFormChange({
                    ...movingAverageForm,
                    lineWidth: event.target.value,
                  })
                }
                type="number"
                value={movingAverageForm.lineWidth}
              />
            </label>
            <button className="secondary-button compact-button" onClick={onAddMovingAverage} type="button">
              <Plus size={16} />
              추가
            </button>
          </div>
        </div>
        {movingAverageConfigs.length > 0 && (
          <div className="moving-average-list">
            {movingAverageConfigs.map((config) => (
              <div className="moving-average-row" key={config.id}>
                <span className="moving-average-swatch" style={{ backgroundColor: config.color }} />
                <strong>{config.days}일 종가</strong>
                <span>{config.lineWidth}px</span>
                <button
                  aria-label={`${config.days}일 이동평균 삭제`}
                  className="icon-button"
                  onClick={() => onRemoveMovingAverage(config.id)}
                  title={`${config.days}일 이동평균 삭제`}
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

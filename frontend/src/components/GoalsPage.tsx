import { useEffect, useState } from "react"
import { apiGet, apiPost } from "../api"
import { getErrorMessage } from "../errors"
import { normalizeNumericInput } from "../numberInputs"
import type { Goal } from "../types"

const goalTypes = [
  ["net_worth", "순자산"],
  ["monthly_income", "월 배당/소득"],
]

const formatKrw = (value: number) => `${value.toLocaleString("ko-KR")} 원`
const goalTypeLabel = (type: string) => (type === "monthly_income" ? "월 배당/소득" : "순자산")

type GoalForm = {
  name: string
  type: string
  targetAmountKrw: string
}

export function GoalsPage() {
  const [form, setForm] = useState<GoalForm>({
    name: "",
    type: "net_worth",
    targetAmountKrw: "",
  })
  const [goals, setGoals] = useState<Goal[]>([])
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  const refreshGoals = async () => {
    const data = await apiGet<Goal[]>("/api/goals")
    setGoals(data)
  }

  useEffect(() => {
    let ignore = false
    apiGet<Goal[]>("/api/goals")
      .then((data) => {
        if (!ignore) {
          setGoals(data)
          setError("")
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(getErrorMessage(err))
        }
      })
    return () => {
      ignore = true
    }
  }, [])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage("")
    setError("")

    const targetAmountKrw = Number(normalizeNumericInput(form.targetAmountKrw))

    if (!form.name.trim()) {
      setError("목표 이름을 입력하세요.")
      return
    }

    if (!Number.isFinite(targetAmountKrw) || targetAmountKrw <= 0) {
      setError("목표 금액은 0보다 큰 숫자로 입력하세요.")
      return
    }

    try {
      await apiPost("/api/goals", {
        name: form.name.trim(),
        type: form.type,
        target_amount_krw: targetAmountKrw,
      })
      await refreshGoals()
      setForm((prev) => ({ ...prev, name: "", targetAmountKrw: "" }))
      setMessage("목표를 저장했습니다.")
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>목표</h2>
        <p>순자산과 월 소득 목표를 등록합니다.</p>
      </header>

      <form className="panel form-panel narrow-form" onSubmit={handleSubmit}>
        <div className="section-heading">
          <h3>목표 만들기</h3>
          <span>KRW</span>
        </div>
        <label>
          목표 이름
          <input
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            placeholder="예: 순자산 1억"
          />
        </label>
        <div className="field-row">
          <label>
            목표 유형
            <select
              value={form.type}
              onChange={(event) => setForm((prev) => ({ ...prev, type: event.target.value }))}
            >
              {goalTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            목표 금액
            <input
              inputMode="numeric"
              value={form.targetAmountKrw}
              onChange={(event) => setForm((prev) => ({ ...prev, targetAmountKrw: event.target.value }))}
              placeholder="0"
            />
          </label>
        </div>
        <button className="primary-button" type="submit">
          목표 저장
        </button>
        {error && <p className="form-message error-text">{error}</p>}
        {message && <p className="form-message success-text">{message}</p>}
      </form>

      <section className="panel">
        <div className="section-heading">
          <h3>목표 현황</h3>
          <span>{goals.length.toLocaleString("ko-KR")}개 목표</span>
        </div>
        {goals.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>목표</th>
                  <th>유형</th>
                  <th className="numeric-cell">목표 금액</th>
                </tr>
              </thead>
              <tbody>
                {goals.map((goal) => (
                  <tr key={goal.id}>
                    <td>{goal.name}</td>
                    <td>{goalTypeLabel(goal.type)}</td>
                    <td className="numeric-cell">{formatKrw(goal.target_amount_krw)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">등록된 목표가 없습니다.</p>
        )}
      </section>
    </section>
  )
}

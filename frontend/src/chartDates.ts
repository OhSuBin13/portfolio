export type ChartPeriod = "daily" | "weekly" | "monthly" | "annual"

type DateParts = {
  year: number
  month: number
  day: number
}

const SOURCE_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})/

const pad2 = (value: number) => String(value).padStart(2, "0")

const formatDateParts = ({ year, month, day }: DateParts) =>
  `${year}-${pad2(month)}-${pad2(day)}`

export const parseChartDate = (value: string) => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const sourceDateParts = (value: string): DateParts | null => {
  const match = SOURCE_DATE_RE.exec(value)
  if (match) {
    return {
      year: Number(match[1]),
      month: Number(match[2]),
      day: Number(match[3]),
    }
  }

  const parsed = parseChartDate(value)
  if (!parsed) {
    return null
  }

  return {
    year: parsed.getUTCFullYear(),
    month: parsed.getUTCMonth() + 1,
    day: parsed.getUTCDate(),
  }
}

export const chartDateKey = (value: string) => {
  const parts = sourceDateParts(value)
  return parts ? formatDateParts(parts) : value.slice(0, 10)
}

export const formatChartDateLabel = (value: string, selectedChartPeriod: ChartPeriod) => {
  const parts = sourceDateParts(value)
  if (!parts) {
    return selectedChartPeriod === "annual"
      ? value.slice(2, 4)
      : selectedChartPeriod === "monthly"
        ? value.slice(2, 7)
        : value.slice(2, 10)
  }

  const year = String(parts.year).slice(2)
  const month = pad2(parts.month)
  const day = pad2(parts.day)
  if (selectedChartPeriod === "annual") {
    return year
  }
  return selectedChartPeriod === "monthly" ? `${year}-${month}` : `${year}-${month}-${day}`
}

export const formatChartDateTime = (value: string) => {
  const parsed = parseChartDate(value)
  if (!parsed) {
    return value
  }
  return parsed.toLocaleString("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  })
}

const weekGroupKey = (timestamp: string) => {
  const parts = sourceDateParts(timestamp)
  if (!parts) {
    return timestamp.slice(0, 10)
  }

  const monday = new Date(Date.UTC(parts.year, parts.month - 1, parts.day))
  const day = monday.getUTCDay() || 7
  monday.setUTCDate(monday.getUTCDate() - day + 1)
  return formatDateParts({
    year: monday.getUTCFullYear(),
    month: monday.getUTCMonth() + 1,
    day: monday.getUTCDate(),
  })
}

const monthGroupKey = (timestamp: string) => {
  const parts = sourceDateParts(timestamp)
  return parts ? `${parts.year}-${pad2(parts.month)}` : timestamp.slice(0, 7)
}

const yearGroupKey = (timestamp: string) => {
  const parts = sourceDateParts(timestamp)
  return parts ? String(parts.year) : timestamp.slice(0, 4)
}

export const chartPeriodGroupKey = (timestamp: string, selectedChartPeriod: ChartPeriod) => {
  if (selectedChartPeriod === "weekly") {
    return weekGroupKey(timestamp)
  }
  if (selectedChartPeriod === "monthly") {
    return monthGroupKey(timestamp)
  }
  if (selectedChartPeriod === "annual") {
    return yearGroupKey(timestamp)
  }
  return chartDateKey(timestamp)
}

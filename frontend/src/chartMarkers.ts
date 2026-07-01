import type { ChartMarkerMemo, TossOrder } from "./types"

export type TradeMarker = {
  key: string
  label: "매수" | "추가매수" | "Trim"
  tone: "buy" | "trim"
  timestamp: string
  price: number
  quantity: string
  memo: string
}

const parseOrderDate = (value: string | null) => {
  if (!value) {
    return null
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const numericOrderPrice = (order: TossOrder) => {
  const value = Number(order.average_filled_price ?? order.price)
  return Number.isFinite(value) && value > 0 ? value : null
}

const numericOrderQuantity = (order: TossOrder) => {
  const rawQuantity = order.filled_quantity || order.quantity
  const value = Number(rawQuantity.replace(/,/g, ""))
  return Number.isFinite(value) && value > 0 ? value : null
}

export const buildTradeMarkers = (
  orders: TossOrder[],
  markerMemos: ChartMarkerMemo[],
): TradeMarker[] => {
  const memosByKey = new Map(markerMemos.map((memo) => [memo.marker_key, memo.memo]))
  let positionQuantity = 0

  return [...orders]
    .sort((left, right) => {
      const leftDate = parseOrderDate(left.filled_at ?? left.ordered_at)?.getTime() ?? 0
      const rightDate = parseOrderDate(right.filled_at ?? right.ordered_at)?.getTime() ?? 0
      return leftDate - rightDate
    })
    .flatMap((order) => {
      const side = order.side.toUpperCase()
      if (side !== "BUY" && side !== "SELL") {
        return []
      }
      const price = numericOrderPrice(order)
      if (price === null) {
        return []
      }
      const filledQuantity = numericOrderQuantity(order)
      const key = `order:${order.order_id}`
      const isBuy = side === "BUY"
      const label = isBuy && positionQuantity <= 0 ? "매수" : isBuy ? "추가매수" : "Trim"
      if (filledQuantity !== null) {
        positionQuantity = isBuy
          ? positionQuantity + filledQuantity
          : Math.max(0, positionQuantity - filledQuantity)
      }
      return [
        {
          key,
          label,
          tone: isBuy ? "buy" : "trim",
          timestamp: order.filled_at ?? order.ordered_at,
          price,
          quantity: order.filled_quantity || order.quantity,
          memo: memosByKey.get(key) ?? "",
        },
      ]
    })
}

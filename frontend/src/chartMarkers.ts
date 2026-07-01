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

export type MarkerPlacementInput = {
  marker: TradeMarker
  candleIndex: number
}

export type MarkerPlacement = MarkerPlacementInput & {
  xOffset: number
}

const OVERLAPPING_MARKER_OFFSET_X = 16
const QUANTITY_EPSILON = 0.00000001

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

const orderDateKey = (order: TossOrder) => (order.filled_at ?? order.ordered_at).slice(0, 10)

type OpenPositionLot = {
  orderKey: string
  dateKey: string
  remainingQuantity: number
  hasVisibleSell: boolean
}

const hiddenSameDayRoundTripOrderKeys = (orders: TossOrder[]) => {
  const hiddenOrderKeys = new Set<string>()
  const openLots: OpenPositionLot[] = []

  orders.forEach((order) => {
    const side = order.side.toUpperCase()
    if (side !== "BUY" && side !== "SELL") {
      return
    }
    if (numericOrderPrice(order) === null) {
      return
    }
    const quantity = numericOrderQuantity(order)
    if (quantity === null) {
      return
    }
    const orderKey = `order:${order.order_id}`
    const dateKey = orderDateKey(order)

    if (side === "BUY") {
      openLots.push({
        orderKey,
        dateKey,
        remainingQuantity: quantity,
        hasVisibleSell: false,
      })
      return
    }

    let remainingSellQuantity = quantity
    const consumedLots: Array<{ lot: OpenPositionLot; fullyClosed: boolean }> = []

    while (remainingSellQuantity > QUANTITY_EPSILON && openLots.length > 0) {
      const lot = openLots[0]
      const consumedQuantity = Math.min(lot.remainingQuantity, remainingSellQuantity)
      lot.remainingQuantity -= consumedQuantity
      remainingSellQuantity -= consumedQuantity

      const fullyClosed = lot.remainingQuantity <= QUANTITY_EPSILON
      consumedLots.push({ lot, fullyClosed })
      if (fullyClosed) {
        openLots.shift()
      }
    }

    const closesOnlySameDayHiddenLots =
      remainingSellQuantity <= QUANTITY_EPSILON &&
      consumedLots.length > 0 &&
      consumedLots.every(
        ({ lot, fullyClosed }) =>
          lot.dateKey === dateKey && fullyClosed && !lot.hasVisibleSell,
      )

    if (closesOnlySameDayHiddenLots) {
      hiddenOrderKeys.add(orderKey)
      consumedLots.forEach(({ lot }) => hiddenOrderKeys.add(lot.orderKey))
      return
    }

    consumedLots.forEach(({ lot }) => {
      lot.hasVisibleSell = true
    })
  })

  return hiddenOrderKeys
}

export const buildTradeMarkers = (
  orders: TossOrder[],
  markerMemos: ChartMarkerMemo[],
): TradeMarker[] => {
  const memosByKey = new Map(markerMemos.map((memo) => [memo.marker_key, memo.memo]))
  let positionQuantity = 0
  const sortedOrders = [...orders].sort((left, right) => {
    const leftDate = parseOrderDate(left.filled_at ?? left.ordered_at)?.getTime() ?? 0
    const rightDate = parseOrderDate(right.filled_at ?? right.ordered_at)?.getTime() ?? 0
    return leftDate - rightDate
  })
  const hiddenOrderKeys = hiddenSameDayRoundTripOrderKeys(sortedOrders)

  return sortedOrders
    .flatMap((order) => {
      const side = order.side.toUpperCase()
      if (side !== "BUY" && side !== "SELL") {
        return []
      }
      const key = `order:${order.order_id}`
      if (hiddenOrderKeys.has(key)) {
        return []
      }
      const price = numericOrderPrice(order)
      if (price === null) {
        return []
      }
      const filledQuantity = numericOrderQuantity(order)
      if (filledQuantity === null) {
        return []
      }
      const isBuy = side === "BUY"
      const label = isBuy && positionQuantity <= 0 ? "매수" : isBuy ? "추가매수" : "Trim"
      positionQuantity = isBuy
        ? positionQuantity + filledQuantity
        : Math.max(0, positionQuantity - filledQuantity)
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

export const spreadOverlappingMarkers = (
  markerPlacements: MarkerPlacementInput[],
): MarkerPlacement[] => {
  const groupSizes = new Map<number, number>()
  const groupIndexes = new Map<number, number>()

  markerPlacements.forEach(({ candleIndex }) => {
    groupSizes.set(candleIndex, (groupSizes.get(candleIndex) ?? 0) + 1)
  })

  return markerPlacements.map((placement) => {
    const groupSize = groupSizes.get(placement.candleIndex) ?? 1
    const groupIndex = groupIndexes.get(placement.candleIndex) ?? 0
    groupIndexes.set(placement.candleIndex, groupIndex + 1)

    return {
      ...placement,
      xOffset: (groupIndex - (groupSize - 1) / 2) * OVERLAPPING_MARKER_OFFSET_X,
    }
  })
}

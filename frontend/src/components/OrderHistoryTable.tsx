import type { TossOrder } from "../types"

const displayValue = (value: string | null) => value || "-"

type OrderHistoryTableProps = {
  orders: TossOrder[]
  formatDateTime: (value: string | null) => string
}

export function OrderHistoryTable({ orders, formatDateTime }: OrderHistoryTableProps) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>주문 시각</th>
            <th>종목</th>
            <th>매매</th>
            <th>상태</th>
            <th className="numeric-cell">수량</th>
            <th className="numeric-cell">가격</th>
            <th className="numeric-cell">체결 수량</th>
            <th className="numeric-cell">체결 금액</th>
            <th className="numeric-cell">수수료</th>
            <th className="numeric-cell">세금</th>
            <th>결제일</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id}>
              <td>{formatDateTime(order.ordered_at)}</td>
              <td>
                <strong>{order.symbol}</strong>
                <br />
                <span>{order.currency}</span>
              </td>
              <td>{order.side}</td>
              <td>{order.order_status}</td>
              <td className="numeric-cell">{order.quantity}</td>
              <td className="numeric-cell">{displayValue(order.price)}</td>
              <td className="numeric-cell">{order.filled_quantity}</td>
              <td className="numeric-cell">{displayValue(order.filled_amount)}</td>
              <td className="numeric-cell">{displayValue(order.commission)}</td>
              <td className="numeric-cell">{displayValue(order.tax)}</td>
              <td>{displayValue(order.settlement_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

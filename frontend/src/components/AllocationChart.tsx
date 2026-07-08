import {
  getAllocationCallouts,
  pieChart,
  type AllocationSegment,
} from "../allocationChart"

type AllocationChartProps = {
  allocationSegments: AllocationSegment[]
}

export function AllocationChart({ allocationSegments }: AllocationChartProps) {
  const visibleAllocationSegments = allocationSegments.filter((segment) => segment.value > 0)
  const allocationCallouts = getAllocationCallouts(visibleAllocationSegments)

  return (
    <div className="allocation-chart">
      <svg
        aria-label="주식/ETF와 현금 비중"
        className="allocation-pie-svg"
        role="img"
        viewBox={`0 0 ${pieChart.width} ${pieChart.height}`}
      >
        {allocationCallouts.map((callout) => (
          <path
            className="allocation-slice"
            d={callout.path}
            fill={callout.color}
            key={callout.key}
          />
        ))}
        {allocationCallouts.map((callout) => (
          <g className="allocation-callout" key={`label-${callout.key}`}>
            <polyline className="allocation-label-line" points={callout.linePoints} />
            <text textAnchor={callout.textAnchor} x={callout.textX} y={callout.textY}>
              <tspan className="allocation-label-name">{callout.label}</tspan>
              <tspan className="allocation-label-percent" x={callout.textX} y={callout.percentY}>
                {callout.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%
              </tspan>
            </text>
          </g>
        ))}
      </svg>
      <div className="allocation-details">
        <div className="allocation-meter" aria-hidden="true">
          {visibleAllocationSegments.map((segment) => (
            <span
              className="allocation-segment"
              key={segment.key}
              style={{ backgroundColor: segment.color, width: `${segment.value}%` }}
            />
          ))}
        </div>
        <div className="allocation-legend">
          {allocationSegments.map((segment) => (
            <div className="allocation-legend-row" key={segment.key}>
              <span className="allocation-swatch" style={{ backgroundColor: segment.color }} />
              <span>{segment.label}</span>
              <strong>
                {segment.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} %
              </strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

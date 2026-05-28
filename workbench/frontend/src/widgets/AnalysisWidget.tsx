import React from 'react'
import { WidgetProps } from './index'

interface AnalysisConfig {
  daily_spend?: number
  monthly_spend?: number
  daily_tokens?: number
  charts?: { label: string; data: number[]; color?: string }[]
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: '16px 20px',
    boxSizing: 'border-box',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    color: '#c9d1d9',
  },
  metricsRow: {
    display: 'flex',
    gap: 0,
    marginBottom: 16,
  },
  metricCard: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
  },
  metricValue: {
    fontSize: 28,
    fontWeight: 600,
    color: '#e6edf3',
    lineHeight: 1.2,
  },
  metricLabel: {
    fontSize: 12,
    color: '#8b949e',
    marginTop: 4,
  },
  divider: {
    border: 'none',
    borderTop: '1px solid #30363d',
    margin: '0 0 12px 0',
  },
  chartLabel: {
    fontSize: 11,
    color: '#8b949e',
    marginBottom: 8,
  },
  barChart: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 3,
    flex: 1,
  },
  bar: {
    flex: 1,
    borderRadius: 2,
    minHeight: 4,
  },
  fallbackValue: {
    fontSize: 28,
    fontWeight: 600,
    color: '#484f58',
    lineHeight: 1.2,
  },
}

function formatNumber(n: number | undefined | null): string {
  if (n === undefined || n === null) return '--'
  if (n >= 10000) {
    return (n / 10000).toFixed(1) + 'w'
  }
  return n.toLocaleString()
}

export default function AnalysisWidget({ config }: WidgetProps) {
  const c = config as AnalysisConfig
  const charts = c.charts || []
  const firstChart = charts.length > 0 ? charts[0] : null

  return (
    <div style={s.container}>
      {/* Metric cards */}
      <div style={s.metricsRow}>
        <div style={s.metricCard}>
          <div style={c.daily_spend !== undefined ? s.metricValue : s.fallbackValue}>
            {formatNumber(c.daily_spend)}
          </div>
          <div style={s.metricLabel}>今日消费</div>
        </div>
        <div style={s.metricCard}>
          <div style={c.monthly_spend !== undefined ? s.metricValue : s.fallbackValue}>
            {formatNumber(c.monthly_spend)}
          </div>
          <div style={s.metricLabel}>本月消费</div>
        </div>
        <div style={s.metricCard}>
          <div style={c.daily_tokens !== undefined ? s.metricValue : s.fallbackValue}>
            {formatNumber(c.daily_tokens)}
          </div>
          <div style={s.metricLabel}>今日 Token</div>
        </div>
      </div>

      {/* Chart section */}
      {firstChart && (
        <>
          <hr style={s.divider} />
          <div style={s.chartLabel}>{firstChart.label}</div>
          <Bars data={firstChart.data} color={firstChart.color || '#58a6ff'} />
        </>
      )}
    </div>
  )
}

function Bars({ data, color }: { data: number[]; color: string }) {
  const points = data.slice(-14)
  const max = Math.max(...points, 1)

  return (
    <div style={s.barChart}>
      {points.map((value, idx) => {
        const height = Math.max(4, (value / max) * 100)
        return (
          <div
            key={idx}
            style={{
              ...s.bar,
              height,
              backgroundColor: color,
            }}
          />
        )
      })}
    </div>
  )
}

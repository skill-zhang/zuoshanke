import React from 'react'
import { WidgetProps } from './index'

interface KlineItem {
  date: string
  open: number
  close: number
  high: number
  low: number
  volume: number
}

interface StockConfig {
  price?: number
  currency?: string
  change?: number
  change_pct?: number
  name?: string
  code?: string
  high?: number
  low?: number
  volume?: number
  market_cap?: number
  kline?: KlineItem[]
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    padding: 20,
    height: '100%',
    boxSizing: 'border-box',
    background: '#161b22',
    color: '#c9d1d9',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  topRow: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 8,
    marginBottom: 2,
  },
  price: {
    fontSize: 30,
    fontWeight: 300,
    color: '#e6edf3',
    lineHeight: 1.1,
  },
  currency: {
    fontSize: 16,
    color: '#8b949e',
    lineHeight: 1,
    marginBottom: 2,
  },
  changeRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 13,
    marginBottom: 8,
  },
  changeUp: {
    color: '#3fb950',
    fontWeight: 500,
  },
  changeDown: {
    color: '#f85149',
    fontWeight: 500,
  },
  nameRow: {
    fontSize: 13,
    color: '#8b949e',
    marginBottom: 12,
  },
  chartSection: {
    marginBottom: 12,
    paddingTop: 8,
  },
  chartLabel: {
    fontSize: 11,
    color: '#8b949e',
    marginBottom: 6,
  },
  chartDates: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: 10,
    color: '#484f58',
    marginTop: 2,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 0,
    flex: 1,
    alignContent: 'stretch',
  },
  gridItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '10px 4px',
    borderBottom: '1px solid #484f58',
    borderRight: '1px solid #484f58',
  },
  gridItemLastRow: {
    borderBottom: 'none',
  },
  gridItemLastCol: {
    borderRight: 'none',
  },
  gridLabel: {
    fontSize: 11,
    color: '#8b949e',
    letterSpacing: '0.5px',
    marginBottom: 4,
  },
  gridValue: {
    fontSize: 15,
    color: '#c9d1d9',
    fontWeight: 500,
  },
  fallback: {
    fontSize: 30,
    color: '#484f58',
    fontWeight: 300,
  },
}

function formatNumber(v: number | undefined | null): string {
  if (v === undefined || v === null) return '--'
  if (Math.abs(v) >= 1_0000_0000) {
    return (v / 1_0000_0000).toFixed(2) + '亿'
  }
  if (Math.abs(v) >= 1_0000) {
    return (v / 1_0000).toFixed(2) + '万'
  }
  return v.toLocaleString()
}

/** 折线图 SVG 组件 */
function KlineChart({ kline, isUp }: { kline: KlineItem[]; isUp: boolean }) {
  const prices = kline.map(d => Number(d.close)).filter(v => !isNaN(v))
  if (prices.length < 2) return null

  const maxPrice = Math.max(...prices)
  const minPrice = Math.min(...prices)
  const range = maxPrice - minPrice || 1
  const w = prices.length * 10
  const h = 60
  const color = isUp ? '#3fb950' : '#f85149'
  const fillColor = isUp ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)'

  const linePath = prices.map((p, i) => {
    const x = i * 10 + 5
    const y = h - ((p - minPrice) / range) * 50
    return `${i === 0 ? 'M' : 'L'}${x},${y}`
  }).join(' ')

  const areaPath = linePath + ` L${(prices.length - 1) * 10 + 5},${h} L5,${h} Z`

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: h, display: 'block' }}>
      {/* 网格线 */}
      <line x1="0" y1="0" x2={w} y2="0" stroke="#21262d" strokeWidth="0.5" />
      <line x1="0" y1={h / 2} x2={w} y2={h / 2} stroke="#21262d" strokeWidth="0.5" />
      <line x1="0" y1={h} x2={w} y2={h} stroke="#21262d" strokeWidth="0.5" />
      {/* 面积填充 */}
      <path d={areaPath} fill={fillColor} />
      {/* 折线 */}
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* 起点圆点 */}
      <circle cx="5" cy={h - ((prices[0] - minPrice) / range) * 50} r="2" fill="#484f58" />
      {/* 终点圆点 */}
      <circle cx={(prices.length - 1) * 10 + 5} cy={h - ((prices[prices.length - 1] - minPrice) / range) * 50} r="2.5" fill={color} />
    </svg>
  )
}

const gridFields: { label: string; key: keyof StockConfig; fmt?: (v: any) => string }[] = [
  { label: '最高', key: 'high', fmt: (v) => Number(v).toFixed(2) },
  { label: '最低', key: 'low', fmt: (v) => Number(v).toFixed(2) },
  { label: '成交量', key: 'volume', fmt: formatNumber },
  { label: '市值', key: 'market_cap', fmt: formatNumber },
]

export default function StockWidget({ config }: WidgetProps) {
  const c = config as StockConfig
  const hasPrice = c.price !== undefined && c.price !== null

  if (!hasPrice) {
    return (
      <div
        style={{
          ...s.container,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span style={s.fallback}>--</span>
        {c.name && (
          <div style={{ ...s.nameRow, marginBottom: 0, marginTop: 8 }}>
            {c.name}
            {c.code ? ` (${c.code})` : ''}
          </div>
        )}
      </div>
    )
  }

  const changeNum = Number(c.change ?? 0);
  const changePctNum = Number(c.change_pct ?? 0);
  const isUp = changeNum >= 0;
  const priceNum = Number(c.price ?? 0);
  const arrow = isUp ? '▲' : '▼';
  const changeColor = isUp ? s.changeUp : s.changeDown;
  const changeText = `${isUp ? '+' : ''}${changeNum.toFixed(2)} (${changePctNum >= 0 ? '+' : ''}${changePctNum.toFixed(2)}%)`

  const kline: KlineItem[] = c.kline || []

  return (
    <div style={s.container}>
      {/* Price + Currency */}
      <div style={s.topRow}>
        <span style={s.price}>{priceNum.toFixed(2)}</span>
        <span style={s.currency}>{c.currency || '--'}</span>
      </div>

      {/* Change indicator */}
      <div style={s.changeRow}>
        <span style={changeColor}>
          {arrow} {changeText}
        </span>
      </div>

      {/* Name + Code */}
      <div style={s.nameRow}>
        {c.name || '--'}
        {c.code ? ` (${c.code})` : ''}
      </div>

      {/* 📊 最近30日股价折线图 */}
      {kline.length > 1 && (
        <div style={s.chartSection}>
          <div style={s.chartLabel}>最近30日走势</div>
          <KlineChart kline={kline} isUp={isUp} />
          <div style={s.chartDates}>
            <span>{kline[0]?.date || ''}</span>
            <span>{kline[kline.length - 1]?.date || ''}</span>
          </div>
        </div>
      )}

      {/* 2x2 Grid: 最高 / 最低 / 成交量 / 市值 */}
      <div style={s.grid}>
        {gridFields.map((field, idx) => {
          const isLastRow = idx >= 2
          const isLastCol = idx % 2 === 1
          const val = c[field.key]

          const display = val !== undefined && val !== null && field.fmt ? field.fmt(val) : '--'

          return (
            <div
              key={field.label}
              style={{
                ...s.gridItem,
                ...(isLastRow ? s.gridItemLastRow : {}),
                ...(isLastCol ? s.gridItemLastCol : {}),
              }}
            >
              <div style={s.gridLabel}>{field.label}</div>
              <div style={s.gridValue}>{display}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

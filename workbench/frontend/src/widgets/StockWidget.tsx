import React from 'react'
import { WidgetProps } from './index'

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
    marginBottom: 16,
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

import React from 'react'
import { WidgetProps } from './index'

interface WeatherConfig {
  city?: string
  temp?: number
  feels_like?: number
  desc?: string
  humidity?: number
  wind?: number
  high?: number
  low?: number
  sunrise?: string
  sunset?: string
  visibility?: number
  precipitation?: number
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
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  leftGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  icon: {
    fontSize: 32,
    lineHeight: 1,
  },
  temp: {
    fontSize: 36,
    fontWeight: 300,
    color: '#e6edf3',
    lineHeight: 1,
  },
  unit: {
    fontSize: 18,
    color: '#8b949e',
    lineHeight: 1,
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  rightGroup: {
    textAlign: 'right',
  },
  desc: {
    fontSize: 15,
    color: '#e6edf3',
    fontWeight: 500,
    textTransform: 'capitalize',
  },
  feelsLike: {
    fontSize: 12,
    color: '#8b949e',
    marginTop: 2,
  },
  cityRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 14,
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
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: 4,
  },
  gridValue: {
    fontSize: 15,
    color: '#c9d1d9',
    fontWeight: 500,
  },
  fallback: {
    fontSize: 36,
    color: '#484f58',
    fontWeight: 300,
  },
}

const gridFields: { key: keyof WeatherConfig; label: string; suffix?: string; fmt?: (v: any) => string }[] = [
  { key: 'humidity', label: 'Humidity', suffix: '%' },
  { key: 'wind', label: 'Wind', suffix: ' km/h' },
  { key: 'high', label: 'High', suffix: '°C' },
  { key: 'low', label: 'Low', suffix: '°C' },
  { key: 'sunrise', label: 'Sunrise' },
  { key: 'sunset', label: 'Sunset' },
  { key: 'visibility', label: 'Visibility', suffix: ' km' },
  { key: 'precipitation', label: 'Precipitation', suffix: '%' },
]

export default function WeatherWidget({ config }: WidgetProps) {
  const c = config as WeatherConfig
  const hasData = c.temp !== undefined && c.temp !== null

  if (!hasData) {
    return (
      <div style={{ ...s.container, alignItems: 'center', justifyContent: 'center' }}>
        <span style={s.fallback}>--°C</span>
        {c.city && <div style={{ ...s.cityRow, marginBottom: 0, marginTop: 8 }}>📍 {c.city}</div>}
      </div>
    )
  }

  return (
    <div style={s.container}>
      {/* Top row */}
      <div style={s.topRow}>
        <div style={s.leftGroup}>
          <span style={s.icon}>🌤️</span>
          <span style={s.temp}>{Math.round(c.temp!)}</span>
          <span style={s.unit}>°C</span>
        </div>
        <div style={s.rightGroup}>
          <div style={s.desc}>{c.desc || '--'}</div>
          <div style={s.feelsLike}>Feels like {c.feels_like !== undefined ? `${Math.round(c.feels_like)}°C` : '--'}</div>
        </div>
      </div>

      {/* City */}
      <div style={s.cityRow}>
        <span>📍</span>
        <span>{c.city || 'Unknown'}</span>
      </div>

      {/* 8-item grid */}
      <div style={s.grid}>
        {gridFields.map((field, idx) => {
          const isLastRow = idx >= 4
          const isLastCol = idx % 2 === 1
          const val = c[field.key]

          let display: string
          if (val === undefined || val === null) {
            display = '--'
          } else if (field.fmt) {
            display = field.fmt(val)
          } else if (field.suffix) {
            display = `${val}${field.suffix}`
          } else {
            display = String(val)
          }

          return (
            <div
              key={field.key}
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

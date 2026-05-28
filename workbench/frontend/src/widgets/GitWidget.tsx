import React from 'react'
import { WidgetProps } from './index'

interface GitConfig {
  yesterday?: {
    count?: number
    details?: string[]
  }
  today?: {
    commits?: number
  }
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 16,
    overflow: 'hidden',
  },
  statRow: {
    display: 'flex',
    gap: 16,
    marginBottom: 12,
  },
  statBox: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '12px 8px',
    borderRadius: 8,
    background: '#161b22',
    border: '1px solid #30363d',
  },
  statLabel: {
    fontSize: 11,
    color: '#8b949e',
    marginBottom: 4,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  statValue: {
    fontSize: 32,
    fontWeight: 500,
    lineHeight: 1.1,
  },
  statValueBlue: {
    color: '#58a6ff',
  },
  statValueGreen: {
    color: '#3fb950',
  },
  statValueDim: {
    color: '#484f58',
  },
  detailsHeader: {
    fontSize: 11,
    color: '#8b949e',
    marginBottom: 6,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  detailsList: {
    flex: 1,
    overflow: 'hidden',
  },
  detailItem: {
    fontSize: 11,
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
    color: '#8b949e',
    lineHeight: '20px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  empty: {
    fontSize: 11,
    color: '#484f58',
    fontStyle: 'italic',
  },
}

export default function GitWidget({ config }: WidgetProps) {
  const c = config as GitConfig
  const yesterdayCount = c.yesterday?.count ?? 0
  const details = c.yesterday?.details ?? []
  const todayCommits = c.today?.commits ?? 0
  const topDetails = details.slice(0, 5)

  return (
    <div style={s.container}>
      {/* Stat boxes */}
      <div style={s.statRow}>
        <div style={s.statBox}>
          <div style={s.statLabel}>昨日提交</div>
          <div style={{ ...s.statValue, ...s.statValueBlue }}>
            {yesterdayCount}
          </div>
        </div>
        <div style={s.statBox}>
          <div style={s.statLabel}>今日提交</div>
          <div style={{ ...s.statValue, ...(todayCommits > 0 ? s.statValueGreen : s.statValueDim) }}>
            {todayCommits}
          </div>
        </div>
      </div>

      {/* Commit details */}
      <div style={s.detailsHeader}>最近提交</div>
      <div style={s.detailsList}>
        {topDetails.length === 0 ? (
          <div style={s.empty}>暂无提交记录</div>
        ) : (
          topDetails.map((d, i) => (
            <div key={i} style={s.detailItem} title={d}>
              {d}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

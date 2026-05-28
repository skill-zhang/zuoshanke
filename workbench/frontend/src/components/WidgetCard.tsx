import React from 'react'
import { WidgetConfig } from '../api'
import { getWidgetMeta, WidgetProps } from '../widgets/index'

interface Props {
  widget: WidgetConfig
  onDelete: (id: string) => void
  onConfigChange: (id: string, config: Record<string, any>) => void
  onRefresh: () => void
}

const s: Record<string, React.CSSProperties> = {
  card: {
    background: '#161b22',
    borderRadius: 12,
    border: '1px solid #30363d',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    minHeight: 200,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: '1px solid #21262d',
  },
  title: { fontSize: 14, fontWeight: 500, color: '#e6edf3' },
  actions: { display: 'flex', gap: 4 },
  actionBtn: {
    width: 24,
    height: 24,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 12,
    color: '#8b949e',
    transition: 'all 0.12s',
  },
  body: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 },
  unknown: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: '#484f58',
    fontSize: 13,
    padding: 24,
    textAlign: 'center',
  },
}

export default function WidgetCard({ widget, onDelete, onConfigChange, onRefresh }: Props) {
  const meta = getWidgetMeta(widget.widget_type)

  let parsedConfig: Record<string, any> = {}
  try {
    parsedConfig = JSON.parse(widget.config || '{}')
  } catch { /* ignore */ }

  const handleConfigChange = (newConfig: Record<string, any>) => {
    onConfigChange(widget.id, newConfig)
  }

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div style={s.title}>
          {meta?.icon || '📦'} {widget.title || meta?.name || widget.widget_type}
        </div>
        <div style={s.actions}>
          <button
            style={s.actionBtn}
            title="刷新"
            onClick={e => { e.stopPropagation(); onRefresh(); }}
            onMouseEnter={e => { e.currentTarget.style.background = '#21262d'; e.currentTarget.style.color = '#e6edf3' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#8b949e' }}
          >🔄</button>
          <button
            style={s.actionBtn}
            title="删除"
            onClick={e => { e.stopPropagation(); if (confirm('删除此组件？')) onDelete(widget.id); }}
            onMouseEnter={e => { e.currentTarget.style.background = '#21262d'; e.currentTarget.style.color = '#f85149' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#8b949e' }}
          >✕</button>
        </div>
      </div>
      <div style={s.body}>
        {meta ? (
          <meta.component config={parsedConfig} onConfigChange={handleConfigChange} />
        ) : (
          <div style={s.unknown}>
            未知组件类型: {widget.widget_type}
          </div>
        )}
      </div>
    </div>
  )
}

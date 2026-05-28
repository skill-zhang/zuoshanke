import React from 'react'
import { WidgetProps } from './index'

interface TodoItem {
  id: string
  text: string
  done: boolean
  priority?: 'high' | 'medium'
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 16,
    overflow: 'hidden',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 0',
    fontSize: 14,
    borderBottom: '1px solid #21262d',
  },
  checkbox: {
    fontSize: 16,
    cursor: 'default',
    flexShrink: 0,
    width: 20,
    textAlign: 'center' as const,
  },
  text: {
    flex: 1,
    color: '#c9d1d9',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  textDone: {
    flex: 1,
    color: '#484f58',
    textDecoration: 'line-through',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  badge: {
    fontSize: 11,
    padding: '1px 6px',
    borderRadius: 4,
    fontWeight: 500,
    flexShrink: 0,
  },
  badgeHigh: {
    background: '#da3633',
    color: '#fff',
  },
  badgeMedium: {
    background: '#d29922',
    color: '#fff',
  },
  footer: {
    textAlign: 'right' as const,
    fontSize: 12,
    color: '#8b949e',
    paddingTop: 8,
    borderTop: '1px solid #21262d',
    marginTop: 4,
  },
  empty: {
    textAlign: 'center' as const,
    color: '#484f58',
    fontSize: 13,
    marginTop: 32,
  },
}

export default function TodoWidget({ config }: WidgetProps) {
  const rawItems: TodoItem[] = Array.isArray(config) ? config : (config.items || []);
  const items = rawItems.slice(0, 10);
  const doneCount = items.filter(i => i.done).length
  const totalCount = items.length

  return (
    <div style={s.container}>
      <div style={s.list}>
        {items.length === 0 ? (
          <div style={s.empty}>暂无待办事项</div>
        ) : (
          items.map(item => (
            <div key={item.id} style={s.item}>
              <span style={{ ...s.checkbox, color: item.done ? '#3fb950' : '#484f58' }}>
                {item.done ? '✓' : '○'}
              </span>
              <span style={item.done ? s.textDone : s.text}>
                {item.text}
              </span>
              {item.priority === 'high' && (
                <span style={{ ...s.badge, ...s.badgeHigh }}>高优</span>
              )}
              {item.priority === 'medium' && (
                <span style={{ ...s.badge, ...s.badgeMedium }}>中优</span>
              )}
            </div>
          ))
        )}
      </div>
      <div style={s.footer}>
        完成 {doneCount} / {totalCount}
      </div>
    </div>
  )
}

import React from 'react'
import { WidgetProps } from './index'

const style: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: '12px 16px',
    overflow: 'hidden',
  },
  item: {
    display: 'flex',
    alignItems: 'flex-start',
    padding: '10px 0',
    borderBottom: '1px solid #21262d',
  },
  rank: {
    fontSize: 12,
    color: '#484f58',
    minWidth: 20,
    lineHeight: '18px',
    textAlign: 'right' as const,
    marginRight: 8,
  },
  content: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    fontSize: 13,
    color: '#e6edf3',
    lineHeight: '18px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  meta: {
    fontSize: 11,
    color: '#484f58',
    marginTop: 2,
    lineHeight: '16px',
  },
  empty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    fontSize: 13,
    color: '#484f58',
  },
}

const MAX_ITEMS = 15

export default function NewsWidget({ config }: WidgetProps) {
  const rawItems: Array<{ rank: number; title: string; source?: string; time?: string }> =
    Array.isArray(config) ? config : (config.items || []);
  const items = rawItems.slice(0, MAX_ITEMS);

  if (items.length === 0) {
    return <div style={style.empty}>暂无资讯</div>
  }

  return (
    <div style={style.container}>
      {items.map((item, i) => (
        <div key={i} style={style.item}>
          <div style={style.rank}>{item.rank}</div>
          <div style={style.content}>
            <div style={style.title}>{item.title}</div>
            {(item.source || item.time) && (
              <div style={style.meta}>
                {item.source}{item.source && item.time ? ' · ' : ''}{item.time}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

import React from 'react'
import { WidgetProps } from './index'

interface ShoppingItem {
  rank: number
  name: string
  store: string
  price: number
  original?: number
  discount?: string
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 12,
    overflow: 'hidden',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 0',
    borderBottom: '1px solid #21262d',
  },
  rank: {
    fontSize: 12,
    color: '#484f58',
    minWidth: 16,
    textAlign: 'center' as const,
  },
  info: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 2,
    minWidth: 0,
  },
  name: {
    fontSize: 14,
    color: '#c9d1d9',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  store: {
    fontSize: 12,
    color: '#8b949e',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  priceArea: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 6,
    flexShrink: 0,
  },
  price: {
    fontSize: 15,
    fontWeight: 600,
    color: '#f85149',
    whiteSpace: 'nowrap' as const,
  },
  original: {
    fontSize: 12,
    color: '#484f58',
    textDecoration: 'line-through',
    whiteSpace: 'nowrap' as const,
  },
  discount: {
    fontSize: 11,
    color: '#f85149',
    whiteSpace: 'nowrap' as const,
  },
  empty: {
    textAlign: 'center' as const,
    color: '#484f58',
    fontSize: 13,
    marginTop: 32,
  },
}

export default function ShoppingWidget({ config }: WidgetProps) {
  const rawItems: ShoppingItem[] = Array.isArray(config) ? config : (config.items || []);
  const items = rawItems.slice(0, 20);

  return (
    <div style={s.container}>
      <div style={s.list}>
        {items.length === 0 ? (
          <div style={s.empty}>暂无商品数据</div>
        ) : (
          items.map((item, idx) => (
            <div key={idx} style={s.row}>
              <span style={s.rank}>{item.rank}</span>
              <div style={s.info}>
                <span style={s.name}>{item.name}</span>
                <span style={s.store}>{item.store}</span>
              </div>
              <div style={s.priceArea}>
                <span style={s.price}>¥{item.price}</span>
                {item.original != null && item.original > item.price && (
                  <span style={s.original}>¥{item.original}</span>
                )}
                {item.discount && (
                  <span style={s.discount}>{item.discount}</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

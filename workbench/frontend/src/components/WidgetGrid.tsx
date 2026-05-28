import React from 'react'
import WidgetCard from './WidgetCard'
import { WidgetConfig } from '../api'

interface Props {
  widgets: WidgetConfig[]
  onDelete: (id: string) => void
  onConfigChange: (id: string, config: Record<string, any>) => void
  onRefresh: () => void
}

const style: Record<string, React.CSSProperties> = {
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: 16,
  },
}

export default function WidgetGrid({ widgets, onDelete, onConfigChange, onRefresh }: Props) {
  return (
    <div style={style.grid}>
      {widgets.map(w => (
        <WidgetCard
          key={w.id}
          widget={w}
          onDelete={onDelete}
          onConfigChange={onConfigChange}
          onRefresh={onRefresh}
        />
      ))}
    </div>
  )
}

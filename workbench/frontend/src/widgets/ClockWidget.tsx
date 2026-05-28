import React, { useState, useEffect } from 'react'
import { WidgetProps } from './index'

const style: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    padding: 24,
    textAlign: 'center',
  },
  time: { fontSize: 48, fontWeight: 300, fontFamily: 'monospace', color: '#e6edf3', letterSpacing: 2 },
  date: { fontSize: 13, color: '#8b949e', marginTop: 8 },
}

export default function ClockWidget({ config }: WidgetProps) {
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const formatTime = (d: Date) => {
    const h = d.getHours().toString().padStart(2, '0')
    const m = d.getMinutes().toString().padStart(2, '0')
    const s = d.getSeconds().toString().padStart(2, '0')
    return config.format === '12h'
      ? `${(d.getHours() % 12 || 12).toString().padStart(2, '0')}:${m}:${s} ${d.getHours() >= 12 ? 'PM' : 'AM'}`
      : `${h}:${m}:${s}`
  }

  const formatDate = (d: Date) => {
    const days = ['日', '一', '二', '三', '四', '五', '六']
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${days[d.getDay()]}`
  }

  return (
    <div style={style.container}>
      <div style={style.time}>{formatTime(now)}</div>
      <div style={style.date}>{formatDate(now)}</div>
    </div>
  )
}

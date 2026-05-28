import React from 'react'
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
  icon: { fontSize: 48, marginBottom: 12 },
  text: { fontSize: 16, color: '#c9d1d9', lineHeight: 1.6 },
  editBtn: {
    marginTop: 12,
    padding: '4px 12px',
    fontSize: 12,
    background: '#21262d',
    border: '1px solid #30363d',
    borderRadius: 6,
    color: '#8b949e',
    cursor: 'pointer',
  },
}

export default function HelloWidget({ config, onConfigChange }: WidgetProps) {
  return (
    <div style={style.container}>
      <div style={style.icon}>👋</div>
      <div style={style.text}>{config.text || '你好！'}</div>
      <button
        style={style.editBtn}
        onClick={() => {
          const newText = prompt('编辑文字：', config.text)
          if (newText) onConfigChange({ ...config, text: newText })
        }}
      >
        编辑
      </button>
    </div>
  )
}

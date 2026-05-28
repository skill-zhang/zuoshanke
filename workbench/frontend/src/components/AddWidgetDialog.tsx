import React, { useState } from 'react'
import { WidgetMeta } from '../api'

interface Props {
  widgetTypes: WidgetMeta[]
  onAdd: (type: string, title: string) => void
  onClose: () => void
}

const style: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.6)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 100,
  },
  dialog: {
    background: '#161b22', borderRadius: 12, border: '1px solid #30363d',
    padding: 24, minWidth: 360, maxWidth: 480,
  },
  title: { fontSize: 16, fontWeight: 600, color: '#e6edf3', marginBottom: 16 },
  input: {
    width: '100%', padding: '8px 12px', background: '#0d1117',
    border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9',
    fontSize: 14, marginBottom: 16, outline: 'none',
  },
  types: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  typeBtn: {
    padding: '8px 16px', background: '#21262d', border: '1px solid #30363d',
    borderRadius: 8, color: '#c9d1d9', cursor: 'pointer', fontSize: 13,
    transition: 'all 0.12s',
  },
  typeBtnSelected: {
    padding: '8px 16px', background: '#1f6feb33', border: '1px solid #58a6ff',
    borderRadius: 8, color: '#58a6ff', cursor: 'pointer', fontSize: 13,
  },
  actions: { display: 'flex', gap: 8, justifyContent: 'flex-end' },
  btn: {
    padding: '8px 20px', borderRadius: 6, fontSize: 14, cursor: 'pointer',
    border: 'none',
  },
  btnPrimary: { background: '#238636', color: '#fff', fontWeight: 500 },
  btnGhost: { background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d' },
}

export default function AddWidgetDialog({ widgetTypes, onAdd, onClose }: Props) {
  const [selected, setSelected] = useState(widgetTypes[0]?.type || '')
  const [title, setTitle] = useState('')

  return (
    <div style={style.overlay} onClick={onClose}>
      <div style={style.dialog} onClick={e => e.stopPropagation()}>
        <div style={style.title}>添加组件</div>

        <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 8 }}>选择组件类型：</div>
        <div style={style.types}>
          {widgetTypes.map(t => (
            <button
              key={t.type}
              style={selected === t.type ? style.typeBtnSelected : style.typeBtn}
              onClick={() => setSelected(t.type)}
            >
              {t.icon} {t.name}
            </button>
          ))}
        </div>

        <input
          style={style.input}
          placeholder="组件标题（可选）"
          value={title}
          onChange={e => setTitle(e.target.value)}
        />

        <div style={style.actions}>
          <button style={{ ...style.btn, ...style.btnGhost }} onClick={onClose}>取消</button>
          <button
            style={{ ...style.btn, ...style.btnPrimary }}
            disabled={!selected}
            onClick={() => onAdd(selected, title)}
          >
            添加
          </button>
        </div>
      </div>
    </div>
  )
}

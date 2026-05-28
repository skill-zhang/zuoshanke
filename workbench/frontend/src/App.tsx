import React, { useState, useEffect, useCallback } from 'react'
import WidgetGrid from './components/WidgetGrid'
import AddWidgetDialog from './components/AddWidgetDialog'
import { listWidgets, createWidget, deleteWidget, updateWidget, WidgetConfig, getWidgetTypes, WidgetMeta } from './api'

const style: Record<string, React.CSSProperties> = {
  app: {
    minHeight: '100vh',
    background: '#0d1117',
    color: '#c9d1d9',
    padding: 24,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
    paddingBottom: 16,
    borderBottom: '1px solid #21262d',
  },
  title: { fontSize: 20, fontWeight: 600, color: '#e6edf3' },
  subtitle: { fontSize: 13, color: '#8b949e', marginTop: 4 },
  addBtn: {
    padding: '8px 20px',
    background: '#238636',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 300,
    color: '#484f58',
    fontSize: 14,
  },
  error: {
    padding: 24,
    textAlign: 'center',
    color: '#f85149',
    fontSize: 14,
  },
}

export default function App() {
  const [widgets, setWidgets] = useState<WidgetConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [widgetTypes, setWidgetTypes] = useState<WidgetMeta[]>([])

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const [w, types] = await Promise.all([listWidgets(), getWidgetTypes()])
      setWidgets(w)
      setWidgetTypes(types)
    } catch (e: any) {
      setError(e?.message || '加载失败，后端可能未启动')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async (type: string, title: string) => {
    try {
      setError('')
      await createWidget({ widget_type: type, title })
      await load()
      setShowAdd(false)
    } catch (e: any) {
      setError('添加失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteWidget(id)
      setWidgets(prev => prev.filter(w => w.id !== id))
    } catch {
      setError('删除失败')
    }
  }

  const handleConfigChange = async (id: string, config: Record<string, any>) => {
    try {
      await updateWidget(id, { config: JSON.stringify(config) })
    } catch {
      // 静默失败，配置更新不影响整体
    }
  }

  if (error && widgets.length === 0) {
    return (
      <div style={style.app}>
        <div style={style.header}>
          <div>
            <div style={style.title}>🏠 个人工作台</div>
            <div style={style.subtitle}>加载失败，请确认后端已启动</div>
          </div>
          <button style={style.addBtn} onClick={load}>重试</button>
        </div>
        <div style={style.error}>
          ⚠️ {error}<br />
          <span style={{ fontSize: 12, color: '#6e7681', marginTop: 8, display: 'block' }}>
            启动命令：cd workbench/backend && venv/bin/python main.py
          </span>
        </div>
      </div>
    )
  }

  return (
    <div style={style.app}>
      <div style={style.header}>
        <div>
          <div style={style.title}>🏠 个人工作台</div>
          <div style={style.subtitle}>{loading ? '加载中…' : `${widgets.length} 个组件`}</div>
        </div>
        <button style={style.addBtn} onClick={() => setShowAdd(true)}>
          + 添加组件
        </button>
      </div>

      {loading ? (
        <div style={style.empty}>⏳ 加载中…</div>
      ) : widgets.length === 0 ? (
        <div style={style.empty}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📦</div>
          <div>还没有任何组件</div>
          <div style={{ color: '#6e7681', marginTop: 8 }}>点击「添加组件」开始搭建你的工作台</div>
        </div>
      ) : (
        <WidgetGrid
          widgets={widgets}
          onDelete={handleDelete}
          onConfigChange={handleConfigChange}
          onRefresh={load}
        />
      )}

      {showAdd && (
        <AddWidgetDialog
          widgetTypes={widgetTypes}
          onAdd={handleAdd}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  )
}

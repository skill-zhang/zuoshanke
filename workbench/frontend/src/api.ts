/** 工作台前端 API */
const API_BASE = '/api'

export interface WidgetConfig {
  id: string
  widget_type: string
  title: string
  config: string
  position: number
  width: number
  height: number
  enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface LayoutConfig {
  columns: number
  gap: number
  max_widgets: number
  theme: string
}

export interface WidgetMeta {
  type: string
  name: string
  icon: string
}

export async function listWidgets(): Promise<WidgetConfig[]> {
  const res = await fetch(`${API_BASE}/widgets`)
  const data = await res.json()
  return data.widgets || []
}

export async function createWidget(data: Partial<WidgetConfig>): Promise<WidgetConfig> {
  const res = await fetch(`${API_BASE}/widgets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const d = await res.json()
  return d.widget
}

export async function updateWidget(id: string, data: Partial<WidgetConfig>): Promise<WidgetConfig> {
  const res = await fetch(`${API_BASE}/widgets/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const d = await res.json()
  return d.widget
}

export async function deleteWidget(id: string): Promise<void> {
  await fetch(`${API_BASE}/widgets/${id}`, { method: 'DELETE' })
}

export async function reorderWidgets(order: string[]): Promise<void> {
  await fetch(`${API_BASE}/widgets/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order }),
  })
}

export async function getLayout(): Promise<LayoutConfig> {
  const res = await fetch(`${API_BASE}/layout`)
  return res.json()
}

export async function updateLayout(data: Partial<LayoutConfig>): Promise<LayoutConfig> {
  const res = await fetch(`${API_BASE}/layout`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function getWidgetTypes(): Promise<WidgetMeta[]> {
  const res = await fetch(`${API_BASE}/widget-types`)
  const data = await res.json()
  return data.types || []
}

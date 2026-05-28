import React from 'react'

export interface WidgetProps {
  config: Record<string, any>
  onConfigChange: (config: Record<string, any>) => void
}

export interface WidgetMeta {
  type: string
  name: string
  icon: string
  defaultConfig: Record<string, any>
  component: React.ComponentType<WidgetProps>
}

import HelloWidget from './HelloWidget'
import ClockWidget from './ClockWidget'

const registry: WidgetMeta[] = [
  {
    type: 'hello',
    name: '你好世界',
    icon: '👋',
    defaultConfig: { text: '你好！这是你的个人工作台 🎉' },
    component: HelloWidget,
  },
  {
    type: 'clock',
    name: '数字时钟',
    icon: '🕐',
    defaultConfig: { format: '24h' },
    component: ClockWidget,
  },
]

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return registry.find(w => w.type === type)
}

export function getWidgetTypes(): WidgetMeta[] {
  return registry
}

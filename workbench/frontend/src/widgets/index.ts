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
import WeatherWidget from './WeatherWidget'
import TodoWidget from './TodoWidget'
import NewsWidget from './NewsWidget'
import GameWidget from './GameWidget'
import AnalysisWidget from './AnalysisWidget'
import GitWidget from './GitWidget'
import StockWidget from './StockWidget'
import ShoppingWidget from './ShoppingWidget'

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
  {
    type: 'weather',
    name: '天气预报',
    icon: '🌤️',
    defaultConfig: { city: '北京', temp: 22, desc: '晴朗' },
    component: WeatherWidget,
  },
  {
    type: 'todo',
    name: '待办事项',
    icon: '✅',
    defaultConfig: {
      items: [
        { id: '1', text: '示例任务1', done: false, priority: 'high' },
        { id: '2', text: '示例任务2', done: true },
        { id: '3', text: '示例任务3', done: false, priority: 'medium' },
      ],
    },
    component: TodoWidget,
  },
  {
    type: 'news',
    name: '资讯快报',
    icon: '📰',
    defaultConfig: { items: [{ rank: 1, title: '示例新闻', source: '来源', time: '今日' }] },
    component: NewsWidget,
  },
  {
    type: 'game',
    name: '游戏',
    icon: '🎮',
    defaultConfig: { url: '', title: '游戏' },
    component: GameWidget,
  },
  {
    type: 'analysis',
    name: '数据分析',
    icon: '📊',
    defaultConfig: {
      daily_spend: 0,
      monthly_spend: 0,
      daily_tokens: 0,
      charts: [],
    },
    component: AnalysisWidget,
  },
  {
    type: 'git',
    name: '代码提交',
    icon: '🔨',
    defaultConfig: { yesterday: { count: 0, details: [] }, today: { commits: 0 } },
    component: GitWidget,
  },
  {
    type: 'stock',
    name: '股票行情',
    icon: '📈',
    defaultConfig: { price: 0, change: 0, change_pct: '0%' },
    component: StockWidget,
  },
  {
    type: 'shopping',
    name: '购物清单',
    icon: '🛒',
    defaultConfig: { items: [] },
    component: ShoppingWidget,
  },
]

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return registry.find(w => w.type === type)
}

export function getWidgetTypes(): WidgetMeta[] {
  return registry
}

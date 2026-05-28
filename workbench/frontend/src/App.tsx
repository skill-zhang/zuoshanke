/**
 * 🏠 个人工作台（Schema v1.8 — 独立沙箱版）
 * 视觉对齐 prototype-workbench-v2.0.html
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import { listWidgets, WidgetConfig } from './api'

/* ═══════════════════════════ 颜色 ═══════════════════════════ */
const C = {
  bg: '#0d1117', cardBg: '#161b22', border: '#30363d',
  text: '#c9d1d9', dim: '#8b949e', faint: '#484f58',
  green: '#3fb950', red: '#f85149', blue: '#58a6ff', gold: '#d29922',
  hoverBorder: '#454d59', headerHover: '#1c2333',
}

/* ═══════════════════════════ 卡片标题映射 ═══════════════════════════ */
const CARD_TITLES: Record<string, string> = {
  weather: '今日天气', todo: '今日待办', news: '今日资讯',
  game: '小游戏', analysis: '数据分析', git: '代码提交',
  stock: '股票行情', shopping: '618 热销榜',
}

const CARD_FOOTERS: Record<string, string> = {
  weather: '📡 完整预报', todo: '📋 全部待办', news: '📰 查看全部',
  game: '🎮 进入游戏', analysis: '📊 详细报表', git: '🔨 提交记录',
  stock: '📈 查看详情', shopping: '🛒 查看更多',
}

/* ═══════════════════════════ Avatar SVG（从 AgentCharacter 原封搬来） ═══════════════ */
const EYE = { L:'M31 17 Q33 16 35 17', R:'M37 17 Q39 16 41 17' }
const MOUTH = 'M33 24 Q36 25.5 39 24'

const AvatarSVG = () => (
  <svg viewBox="10 0 52 50" width="56" height="56" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <radialGradient id="bgGlow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.09"/>
        <stop offset="60%" stopColor="#00d4ff" stopOpacity="0.025"/>
        <stop offset="100%" stopColor="#00d4ff" stopOpacity="0"/>
      </radialGradient>
      <linearGradient id="skinTone" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#2a2a3e"/>
        <stop offset="50%" stopColor="#1e1e32"/>
        <stop offset="100%" stopColor="#1a1a2e"/>
      </linearGradient>
      <linearGradient id="hairGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#1a1a2e"/>
        <stop offset="50%" stopColor="#16213e"/>
        <stop offset="100%" stopColor="#0f3460"/>
      </linearGradient>
      <linearGradient id="hairStreak" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="#00d4ff"/>
        <stop offset="100%" stopColor="#7b2ff7"/>
      </linearGradient>
      <linearGradient id="jacketGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#1a2332"/>
        <stop offset="100%" stopColor="#0f1624"/>
      </linearGradient>
      <linearGradient id="visorGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.3"/>
        <stop offset="50%" stopColor="#00d4ff" stopOpacity="0.06"/>
        <stop offset="100%" stopColor="#00d4ff" stopOpacity="0.18"/>
      </linearGradient>
      <filter id="neonGlow"><feGaussianBlur stdDeviation="0.8"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <filter id="softGlow"><feGaussianBlur stdDeviation="0.5"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <circle cx="36" cy="28" r="28" fill="url(#bgGlow)"/>
    <path d="M14 42 L10 44 L12 50 L16 54 L56 54 L60 50 L62 44 L58 42" fill="url(#jacketGrad)" stroke="#1e2a3a" strokeWidth="0.8"/>
    <path d="M26 34 Q22 32 24 28 L48 28 Q50 32 46 34 Z" fill="#1a2332" stroke="#1e2a3a" strokeWidth="0.6"/>
    <path d="M28 34 L26 28" fill="none" stroke="#00d4ff" strokeWidth="0.5" opacity="0.3"/>
    <path d="M44 34 L46 28" fill="none" stroke="#00d4ff" strokeWidth="0.5" opacity="0.3"/>
    <line x1="36" y1="38" x2="36" y2="54" stroke="#1e2a3a" strokeWidth="1"/>
    <path d="M24 38 Q30 36 36 36 Q42 36 48 38 L48 46 Q42 48 36 48 Q30 48 24 46 Z" fill="url(#jacketGrad)" stroke="#1e2a3a" strokeWidth="0.5" opacity="0.7"/>
    <polygon points="34,40 36,38 38,40 36,42" fill="none" stroke="#00d4ff" strokeWidth="0.6" opacity="0.45" filter="url(#softGlow)"/>
    <circle cx="12" cy="46" r="1" fill="#00d4ff" opacity="0.4" filter="url(#softGlow)"/>
    <circle cx="60" cy="46" r="1" fill="#00d4ff" opacity="0.4" filter="url(#softGlow)"/>
    <rect x="32" y="28" width="8" height="6" rx="2" fill="url(#skinTone)" stroke="#2d3748" strokeWidth="0.4"/>
    <ellipse cx="36" cy="20" rx="10" ry="10.5" fill="url(#skinTone)" stroke="#2d3748" strokeWidth="0.6"/>
    <path d="M26 20 Q26 28 30 30 Q36 31 42 30 Q46 28 46 20" fill="none" stroke="#2d3748" strokeWidth="0.4" opacity="0.4"/>
    <path d="M33 29 Q36 30.5 39 29" fill="none" stroke="#3d4a5c" strokeWidth="0.3" opacity="0.25"/>
    <path d="M25 16 Q25 6 30 4 Q33 2 36 3 Q39 2 42 4 Q47 6 47 16 Q43 10 36 9 Q29 10 25 16 Z" fill="url(#hairGrad)"/>
    <path d="M26 14 Q24 10 27 8 Q29 7 31 8 Q29 10 28 13 Z" fill="url(#hairGrad)"/>
    <path d="M31 4 Q31 2 32 1 L33 4 Z" fill="url(#hairGrad)"/>
    <path d="M36 3 Q36 1 37 0 L38 3 Z" fill="url(#hairGrad)"/>
    <path d="M40 4 Q41 2 42 2 L42 4 Z" fill="url(#hairGrad)"/>
    <path d="M29 13 Q30 9 33 8" fill="none" stroke="url(#hairStreak)" strokeWidth="1.5" strokeLinecap="round" filter="url(#softGlow)"/>
    <path d="M37 10 Q39 7 42 7" fill="none" stroke="url(#hairStreak)" strokeWidth="0.8" strokeLinecap="round" opacity="0.5" filter="url(#softGlow)"/>
    <path d="M24 16 Q28 14 36 14 Q44 14 48 16 L48 20 Q44 22 36 22 Q28 22 24 20 Z" fill="url(#visorGrad)" stroke="#00d4ff" strokeWidth="0.7" opacity="0.7"/>
    <path d="M26 17 Q30 16 34 16 L35 17 L33 18 Q29 18 26 17 Z" fill="#00d4ff" opacity="0.1"/>
    <circle cx="36" cy="18" r="1.3" fill="#00d4ff" opacity="0.2" filter="url(#neonGlow)"/>
    <circle cx="26" cy="18" r="0.7" fill="#00d4ff" opacity="0.3" filter="url(#neonGlow)"/>
    <circle cx="46" cy="18" r="0.7" fill="#00d4ff" opacity="0.3" filter="url(#neonGlow)"/>
    <path d="M25 16 Q31 14.5 36 14.5 Q41 14.5 47 16" fill="none" stroke="#00d4ff" strokeWidth="0.35" opacity="0.45"/>
    <g><path d={EYE.L} fill="none" stroke="#00d4ff" strokeWidth="1" strokeLinecap="round"/><path d={EYE.R} fill="none" stroke="#00d4ff" strokeWidth="1" strokeLinecap="round"/></g>
    <path d={MOUTH} fill="none" stroke="#3d4a5c" strokeWidth="0.7" strokeLinecap="round"/>
    <circle cx="47" cy="16" r="2" fill="none" stroke="#00d4ff" strokeWidth="0.4" opacity="0.3"/>
    <circle cx="47" cy="16" r="0.5" fill="#00d4ff" opacity="0.2" filter="url(#neonGlow)"/>
  </svg>
)

/* ═══════════════════════════ inline 样式 ═══════════════════════════ */
const merge = (...objs: (React.CSSProperties | undefined)[]): React.CSSProperties =>
  Object.assign({}, ...objs.filter(Boolean))

/* ═══════════════════════════ Widget Renderers ═══════════════════════════ */

// ① Weather
const renderWeather = (config: any) => {
  const w = Array.isArray(config) ? config[0] : config
  if (!w?.temp) return <div style={{ padding: 16, color: C.faint }}>等待数据更新</div>
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ fontSize: 48, lineHeight: 1 }}>☀️</div>
        <div>
          <div style={{ fontSize: 36, fontWeight: 300, lineHeight: 1.1, color: '#e6edf3' }}>
            {w.temp}°<span style={{ fontSize: 18, color: C.faint }}>C</span>
          </div>
          <div style={{ fontSize: 13, color: C.dim, marginTop: 2 }}>{w.desc} · 体感 {w.feels_like}°</div>
          <div style={{ fontSize: 12, color: C.faint, marginTop: 2 }}>📍 {w.city}</div>
        </div>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px',
        marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}`,
      }}>
        {[
          ['💧 湿度', w.humidity], ['🌬 风力', w.wind],
          ['🌅 日出', w.sunrise], ['🌇 日落', w.sunset],
          ['🌡 最高', `${w.high}°`], ['🌡 最低', `${w.low}°`],
          ['👁 能见度', w.visibility], ['☂ 降水', w.precipitation],
        ].map(([l, v], i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
            <span style={{ color: C.dim }}>{l}</span>
            <span style={{ color: C.text, fontWeight: 500 }}>{v ?? '--'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ② Todo
const renderTodo = (config: any) => {
  const items: any[] = Array.isArray(config) ? config : (config.items || [])
  const done = items.filter((i: any) => i.done).length
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.slice(0, 10).map((i: any) => (
          <div key={i.id} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '8px 10px', background: C.bg,
            borderRadius: 6, fontSize: 13,
            opacity: i.done ? 0.6 : 1,
          }}>
            <div style={{
              width: 16, height: 16, borderRadius: 4,
              border: `2px solid ${i.done ? C.green : C.border}`,
              flexShrink: 0,
              background: i.done ? C.green : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, color: '#fff',
            }}>
              {i.done ? '✓' : ''}
            </div>
            <span style={{
              flex: 1, color: i.done ? C.faint : C.text,
              textDecoration: i.done ? 'line-through' : 'none',
            }}>{i.text}</span>
            {i.priority === 'high' && (
              <span style={{ fontSize: 11, padding: '1px 6px', borderRadius: 3, fontWeight: 500, color: C.red, background: 'rgba(248,81,73,0.1)' }}>高</span>
            )}
            {i.priority === 'medium' && (
              <span style={{ fontSize: 11, padding: '1px 6px', borderRadius: 3, fontWeight: 500, color: C.gold, background: 'rgba(210,153,34,0.1)' }}>中</span>
            )}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 12, paddingTop: 10, borderTop: `1px solid ${C.border}`, fontSize: 12, color: C.dim }}>
        <span>共 <strong style={{ color: C.text }}>{items.length}</strong> 项</span>
        <span>已完成 <strong style={{ color: C.green }}>{done}</strong></span>
      </div>
    </div>
  )
}

// ③ News
const renderNews = (config: any) => {
  const items: any[] = Array.isArray(config) ? config : (config.items || [])
  if (!items.length) return <div style={{ padding: 16, textAlign: 'center', color: C.faint }}>暂无资讯</div>
  return (
    <div style={{ padding: 16 }}>
      {items.slice(0, 15).map((i: any) => (
        <div key={i.rank} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontSize: 12, color: C.faint, minWidth: 20 }}>{i.rank}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{i.title}</div>
            <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>{i.source} · {i.time}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ④ Game
const renderGame = (config: any) => {
  const g = Array.isArray(config) ? config[0] : (config || {})
  return (
    <div style={{ padding: 16 }}>
      <div style={{
        width: '100%', aspectRatio: '16/10',
        background: 'linear-gradient(135deg, #1a2332, #0d1117)',
        border: `1px solid ${C.border}`, borderRadius: 6,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 42, position: 'relative', cursor: g.url ? 'pointer' : 'default',
      }} onClick={() => g.url && window.open(g.url, '_blank')}>
        🎮
        {g.url && <span style={{ position: 'absolute', bottom: 6, right: 8, background: 'rgba(0,0,0,0.7)', color: C.text, fontSize: 11, padding: '2px 8px', borderRadius: 4 }}>▶ 打开游戏</span>}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
        <span style={{ fontSize: 12, color: C.dim }}>{g.title || '未知游戏'}</span>
        {g.url && (
          <button style={{
            background: 'linear-gradient(135deg, #e6c84a 0%, #c8a84e 50%, #a08030 100%)',
            color: '#0d1117', border: 'none', borderRadius: 6, padding: '6px 14px',
            fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }} onClick={() => window.open(g.url, '_blank')}>开始游戏</button>
        )}
      </div>
    </div>
  )
}

// ⑤ Analysis
const renderAnalysis = (config: any) => {
  const a = Array.isArray(config) ? config[0] : (config || {})
  const charts: any[] = a.charts || []
  const maxVal = charts.length > 0 ? Math.max(...(charts[0]?.data || [0])) : 1
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 12 }}>
        {[
          { val: a.daily_spend, label: '今日消费' },
          { val: a.monthly_spend, label: '本月消费' },
          { val: a.daily_tokens, label: '今日 Token' },
        ].map((m, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 600, color: C.text }}>{m.val ?? '--'}</div>
            <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>{m.label}</div>
          </div>
        ))}
      </div>
      {charts.slice(0, 1).map((c, ci) => (
        <div key={ci} style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 11, color: C.dim, marginBottom: 6 }}>{c.label}</div>
          <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 40 }}>
            {(c.data as number[]).slice(-14).map((v: number, i: number) => (
              <div key={i} style={{
                flex: 1, background: c.color || C.blue, borderRadius: 2,
                height: `${Math.max((v / maxVal) * 100, 5)}%`, minHeight: 4,
                opacity: 0.7 + (i / 28) * 0.3,
              }} title={`${v.toFixed(1)}`} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ⑥ Git
const renderGit = (config: any) => {
  const g = Array.isArray(config) ? config[0] : (config || {})
  const y = g.yesterday || {}
  const t = g.today || {}
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1, textAlign: 'center', padding: '10px 8px', background: C.bg, borderRadius: 6 }}>
          <div style={{ fontSize: 24, fontWeight: 600, color: C.blue }}>{y.count ?? 0}</div>
          <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>昨日提交</div>
        </div>
        <div style={{ flex: 1, textAlign: 'center', padding: '10px 8px', background: C.bg, borderRadius: 6 }}>
          <div style={{ fontSize: 24, fontWeight: 600, color: (t.commits ?? 0) > 0 ? C.green : C.faint }}>{t.commits ?? 0}</div>
          <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>今日提交</div>
        </div>
      </div>
      {(y.details || []).slice(0, 5).map((d: string, i: number) => (
        <div key={i} style={{ fontSize: 11, color: C.dim, padding: '3px 0', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d}</div>
      ))}
    </div>
  )
}

// ⑦ Stock
const renderStock = (config: any) => {
  const s2 = Array.isArray(config) ? config[0] : (config || {})
  const changeNum = Number(s2.change ?? 0)
  const isUp = changeNum >= 0
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 32, lineHeight: 1 }}>📈</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 30, fontWeight: 300, color: '#e6edf3', lineHeight: 1.1 }}>
            {Number(s2.price || 0).toFixed(2)}<span style={{ fontSize: 16, color: C.faint }}>{s2.currency || ''}</span>
          </div>
          <div style={{ fontSize: 13, color: isUp ? C.green : C.red, marginTop: 2 }}>
            {isUp ? '▲' : '▼'} {s2.change} ({s2.change_pct})
          </div>
          <div style={{ fontSize: 12, color: C.faint, marginTop: 2 }}>{s2.name} · {s2.code}</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
        {[
          ['最高', s2.high], ['最低', s2.low],
          ['成交量', s2.volume], ['市值', s2.market_cap],
        ].map(([l, v], i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
            <span style={{ color: C.dim }}>{l}</span>
            <span style={{ color: C.text, fontWeight: 500 }}>{v ?? '--'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ⑧ Shopping
const renderShopping = (config: any) => {
  const items: any[] = Array.isArray(config) ? config : (config.items || [])
  return (
    <div style={{ padding: 16 }}>
      {items.slice(0, 20).map((i: any) => (
        <div key={i.rank} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontSize: 12, color: C.faint, minWidth: 16 }}>{i.rank}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{i.name}</div>
            <div style={{ fontSize: 11, color: C.dim }}>{i.store}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: C.red }}>{i.price}</div>
            <div style={{ fontSize: 11, color: C.faint }}><s>{i.original}</s> {i.discount}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

const WIDGET_RENDERERS: Record<string, (config: any) => React.ReactElement> = {
  weather: renderWeather, todo: renderTodo, news: renderNews,
  game: renderGame, analysis: renderAnalysis, git: renderGit,
  stock: renderStock, shopping: renderShopping,
}

/* ═══════════════════════════ App ═══════════════════════════ */
export default function App() {
  const [widgets, setWidgets] = useState<WidgetConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [clock, setClock] = useState('')
  const [greeting, setGreeting] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [barExpanded, setBarExpanded] = useState(true)
  const [inputFocused, setInputFocused] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const [avatarSpeech, setAvatarSpeech] = useState('')
  const [avatarSpeaking, setAvatarSpeaking] = useState(false)
  const processingRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setWidgets(await listWidgets()) } catch { /* ignore */ }
    setLoading(false)
  }, [])

  // SSE 聊天：发送 → avatar NPC 字幕回应
  const sendWorkbenchChat = useCallback(async (text: string) => {
    if (!text.trim()) return
    if (processingRef.current) return
    processingRef.current = true

    setInputVal('')
    setAvatarSpeaking(true)
    setAvatarSpeech('')

    try {
      const resp = await fetch('/api/workbench/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: text }),
      })
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              if (event.type === 'speech:token') {
                setAvatarSpeech(event.text)
              } else if (event.type === 'speech:done') {
                setAvatarSpeech(event.text)
              } else if (event.type === 'done') {
                setAvatarSpeaking(false)
                processingRef.current = false
                setTimeout(() => setAvatarSpeech(''), 4000)
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch (e) {
      console.error('[workbench] SSE error:', e)
      setAvatarSpeaking(false)
      processingRef.current = false
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
      const h = now.getHours()
      if (h < 6) setGreeting('夜深了 🌙')
      else if (h < 9) setGreeting('早上好 🌅')
      else if (h < 12) setGreeting('上午好 ☀️')
      else if (h < 14) setGreeting('中午好 ☀️')
      else if (h < 18) setGreeting('下午好 🌤️')
      else setGreeting('晚上好 🌆')
      setSubtitle(`${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 星期${['日','一','二','三','四','五','六'][now.getDay()]}`)
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  const parseConfig = (w: WidgetConfig) => {
    try { return JSON.parse(w.config || '{}') } catch { return {} }
  }

  const handleEnterMain = () => {
    window.location.href = '/'
  }

  return (
    <div style={{
      minHeight: '100vh', background: C.bg, color: C.text,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: 14, lineHeight: 1.5,
      display: 'flex', flexDirection: 'column',
    }}>
      {/* ═══ Avatar（fixed 漂浮，hover 显示气泡） ═══ */}
      <div style={{
        position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)',
        zIndex: 100, width: 70, height: 66, cursor: 'pointer',
      }} onClick={handleEnterMain}
        onMouseEnter={e => { e.currentTarget.style.zIndex = '101' }}
      >
        <div style={{ width: 56, height: 56, margin: '3px auto 0', filter: 'drop-shadow(0 2px 16px rgba(0,212,255,0.12))' }}>
          <AvatarSVG />
        </div>
        {/* 🆕 移动端渐变紫色用户名 — 独立 fixed 定位在 avatar 右上 */}
        <span className="wb-username-mobile" style={{ display: 'none' }}>清泉</span>
        {/* 状态气泡 — hover 显示 */}
        <div style={{
          position: 'absolute', top: 10, left: 78,
          background: '#1a2332', border: '1px solid rgba(0,212,255,0.33)',
          borderRadius: 8, padding: '4px 12px', fontSize: 13, color: C.text,
          whiteSpace: 'nowrap', pointerEvents: 'none',
          opacity: 0, transition: 'opacity 0.2s',
        }} className="avatar-bubble">
          <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', marginRight: 4, background: C.green, verticalAlign: 'middle' }} />
          在线待命
        </div>
        <div style={{
          textAlign: 'center', fontSize: 8, color: C.faint,
          textTransform: 'uppercase', letterSpacing: 0.5, marginTop: -2,
          opacity: 0, transition: 'opacity 0.2s',
        }} className="avatar-label">IDLE</div>
        {/* hover 触发器 — 用 CSS hover 控制气泡和标签显示 */}
        <style>{`
          .avatar-area:hover .avatar-bubble,
          .avatar-area:hover .avatar-label { opacity: 1 !important; }
          /* 🆕 移动端：渐变紫色用户名独立定位在 avatar 右上 */
          @media (max-width: 760px) {
            .wb-username-mobile {
              display: inline !important;
              position: fixed !important;
              top: 5px;
              left: calc(50% + 131px);
              z-index: 100;
              font-size: 20px;
              font-weight: 700;
              background: linear-gradient(135deg, #a855f7, #7c3aed, #c084fc);
              -webkit-background-clip: text !important;
              -webkit-text-fill-color: transparent !important;
              background-clip: text !important;
              white-space: nowrap;
              font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
              letter-spacing: 1px;
            }
          }
        `}</style>
      </div>

      {/* ═══ Avatar 对话字幕（fixed 在 avatar 下方） ═══ */}
      <div style={{
        position: 'fixed', top: 72, left: '50%', transform: 'translateX(-50%)',
        maxWidth: 520, width: '90%', zIndex: 99,
        background: 'rgba(13,17,23,0.88)', border: '1px solid #30363d', borderRadius: 10,
        padding: '14px 24px', textAlign: 'center', pointerEvents: 'none',
        opacity: avatarSpeaking || avatarSpeech ? 1 : 0,
        transition: 'opacity 0.4s, transform 0.3s',
      }}>
        <div style={{ fontSize: 14, color: C.text, minHeight: 20 }}>
          {avatarSpeech || '\u00A0'}
        </div>
        <div style={{ fontSize: 11, color: C.dim, marginTop: 4 }}>— 坐山客 —</div>
      </div>

      {/* ═══ Main ═══ */}
      <div className="wb-main-content" style={{ flex: 1, overflowY: 'auto', padding: '3px 32px 110px', display: 'flex', flexDirection: 'column' }}>
        <style>{`
          @media (max-width: 760px) {
            .wb-main-content { padding: 3px 16px 110px !important; }
            .wb-card-grid { grid-template-columns: 1fr !important; }
          }
        `}</style>
        {/* Greeting */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 28, fontWeight: 600, color: C.text, margin: 0, marginBottom: 4 }}>{greeting}</h1>
            <div style={{ fontSize: 13, color: C.dim }}>{subtitle}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ fontSize: 14, color: C.dim, fontVariant: 'tabular-nums', marginRight: 8 }}>{clock}</span>
            <button style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', background: C.cardBg, border: `1px solid ${C.border}`,
              borderRadius: 8, color: C.text, fontSize: 13, cursor: 'pointer',
            }} onClick={load}>
              <span style={{ fontSize: 15 }}>🔄</span> 刷新
            </button>
            <button style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 14px',
              background: 'linear-gradient(135deg, #e6c84a 0%, #c8a84e 50%, #a08030 100%)',
              color: '#0d1117', border: `1px solid #c8a84e`,
              borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
              textShadow: '0 1px 0 rgba(255,255,255,0.15)',
            }} onClick={handleEnterMain}>
              进入坐山客空间 →
            </button>
          </div>
        </div>

        {/* Card Grid */}
        <div className="wb-card-grid" style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: 16, alignItems: 'start', flex: 1,
        }}>
          {loading ? (
            <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200, color: C.dim }}>加载中...</div>
          ) : widgets.length === 0 ? (
            <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.4 }}>🏠</div>
              <div style={{ fontSize: 14, color: C.dim }}>工作台还是空的</div>
              <div style={{ fontSize: 12, color: C.faint, marginTop: 8 }}>去主系统添加组件</div>
            </div>
          ) : (
            widgets.map(w => {
              const renderer = WIDGET_RENDERERS[w.widget_type]
              const config = parseConfig(w)
              const title = CARD_TITLES[w.widget_type] || w.title
              const footer = CARD_FOOTERS[w.widget_type]
              return (
                <div key={w.id} style={{
                  background: C.cardBg, border: `1px solid ${C.border}`, borderRadius: 10,
                  overflow: 'hidden', transition: 'border-color 0.2s', cursor: 'default',
                }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = C.hoverBorder }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = C.border }}
                >
                  {/* Card Header */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '12px 16px', borderBottom: `1px solid ${C.border}`,
                    fontSize: 13, fontWeight: 500, cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.background = C.headerHover }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <span style={{ fontSize: 15 }}>{w.widget_type === 'weather' ? '🌤️' : w.widget_type === 'todo' ? '✅' : w.widget_type === 'news' ? '📰' : w.widget_type === 'game' ? '🎮' : w.widget_type === 'analysis' ? '📊' : w.widget_type === 'git' ? '🔨' : w.widget_type === 'stock' ? '📈' : w.widget_type === 'shopping' ? '🛒' : '📦'}</span>
                    {title}
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                      <button style={{ background: 'none', border: 'none', color: C.dim, cursor: 'pointer', fontSize: 13, padding: '2px 6px', borderRadius: 4 }}
                        onClick={e => { e.stopPropagation(); load() }}
                        onMouseEnter={e => { e.currentTarget.style.color = C.text; e.currentTarget.style.background = '#21262d' }}
                        onMouseLeave={e => { e.currentTarget.style.color = C.dim; e.currentTarget.style.background = 'none' }}
                      >🔄</button>
                    </div>
                  </div>
                  {/* Card Body */}
                  {renderer ? renderer(config) : (
                    <div style={{ padding: 32, textAlign: 'center', color: C.faint, fontSize: 13 }}>
                      未知组件: {w.widget_type}
                    </div>
                  )}
                  {/* Card Footer */}
                  {footer && (
                    <div style={{
                      borderTop: `1px solid ${C.border}`, padding: '10px 16px',
                      display: 'flex', alignItems: 'center', gap: 8,
                      fontSize: 12, color: C.dim, cursor: 'pointer',
                      transition: 'background 0.15s, color 0.15s',
                    }}
                      onMouseEnter={e => { e.currentTarget.style.background = C.headerHover; e.currentTarget.style.color = C.text }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = C.dim }}
                    >
                      <span>{footer}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 14, transition: 'transform 0.2s' }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'translateX(3px)' }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'translateX(0)' }}
                      >→</span>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ═══ Floating Chat Bar（原型对齐） ═══ */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        background: C.cardBg, borderTop: `1px solid ${C.border}`,
        padding: '12px 24px', display: 'flex', alignItems: 'center', gap: 10,
        zIndex: 200,
        transform: barExpanded ? 'translateY(0)' : 'translateY(calc(100% - 6px))',
        transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
      }}>
        {/* 收起/展开按钮 */}
        <div onClick={() => setBarExpanded(!barExpanded)} style={{
          position: 'absolute', top: -28, left: '50%', transform: 'translateX(-50%)',
          width: 48, height: 24,
          background: C.cardBg, border: `1px solid ${C.border}`, borderBottom: 'none',
          borderRadius: '8px 8px 0 0', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: barExpanded ? C.dim : C.text, fontSize: 11,
        }} title="收起/展开">{barExpanded ? '▲' : '▼'}</div>

        <input
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') sendWorkbenchChat(inputVal); }}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          style={{
            flex: 1, background: C.bg,
            border: inputFocused ? '1px solid #c8a84e' : `1px solid ${C.border}`,
            borderRadius: 8, padding: '14px 16px', color: C.text, fontSize: 14,
            fontFamily: 'inherit', outline: 'none',
            minHeight: 48, lineHeight: 1.6, transition: 'border-color 0.2s',
          }} placeholder={"💬 跟坐山客说你想看什么...（例如：加一个 Github Trending 卡片）"} />

        <button onClick={() => sendWorkbenchChat(inputVal)} style={{
          background: 'linear-gradient(135deg, #e6c84a 0%, #c8a84e 50%, #a08030 100%)',
          color: '#0d1117', border: 'none', borderRadius: 8,
          padding: '10px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer',
          textShadow: '0 1px 0 rgba(255,255,255,0.15)', whiteSpace: 'nowrap',
        }}>发送</button>

        <span style={{ fontSize: 12, color: C.faint, whiteSpace: 'nowrap' }}>⌘K 唤起</span>
      </div>
    </div>
  )
}

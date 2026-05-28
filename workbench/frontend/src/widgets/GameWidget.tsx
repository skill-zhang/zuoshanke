import React from 'react'
import { WidgetProps } from './index'

interface GameConfig {
  url?: string
  title?: string
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    padding: 24,
    textAlign: 'center',
    boxSizing: 'border-box',
    background: '#161b22',
    borderRadius: 8,
    position: 'relative',
    overflow: 'hidden',
  },
  icon: {
    fontSize: 64,
    lineHeight: 1,
    marginBottom: 16,
  },
  title: {
    fontSize: 16,
    fontWeight: 600,
    color: '#e6edf3',
    marginBottom: 8,
    lineHeight: 1.4,
  },
  subtitle: {
    fontSize: 13,
    color: '#8b949e',
    marginBottom: 20,
  },
  playBtn: {
    padding: '10px 28px',
    fontSize: 15,
    fontWeight: 600,
    background: '#238636',
    border: 'none',
    borderRadius: 6,
    color: '#ffffff',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  placeholder: {
    fontSize: 14,
    color: '#484f58',
    fontStyle: 'italic',
  },
}

export default function GameWidget({ config }: WidgetProps) {
  const { url, title } = config as GameConfig

  const handlePlay = () => {
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  if (!url) {
    return (
      <div style={s.container}>
        <div style={s.icon}>🎮</div>
        <div style={s.title}>{title || '游戏'}</div>
        <div style={s.placeholder}>等待配置</div>
      </div>
    )
  }

  return (
    <div style={s.container}>
      <div style={s.icon}>🎮</div>
      <div style={s.title}>{title || '游戏'}</div>
      {url && (
        <button
          style={s.playBtn}
          onClick={handlePlay}
          onMouseOver={e => {
            ;(e.currentTarget as HTMLButtonElement).style.background = '#2ea043'
          }}
          onMouseOut={e => {
            ;(e.currentTarget as HTMLButtonElement).style.background = '#238636'
          }}
        >
          ▶ 开始游戏
        </button>
      )}
    </div>
  )
}

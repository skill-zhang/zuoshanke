/** Logo SVG 组件 */
export function LogoSvg() {
  return (
    <svg viewBox="0 0 40 40">
      <polygon points="20,3 38,35 2,35" fill="none" stroke="#58a6ff" strokeWidth="2.5" strokeLinejoin="round"/>
      <polygon points="20,11 31,32 9,32" fill="rgba(88,166,255,0.12)" stroke="#58a6ff" strokeWidth="1.5" strokeLinejoin="round"/>
      <line x1="20" y1="20" x2="20" y2="27" stroke="#58a6ff" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="20" cy="18" r="2.5" fill="#58a6ff"/>
    </svg>
  );
}

/** 文件夹 SVG */
export function FolderSvg({ color = '#58a6ff' }: { color?: string }) {
  return (
    <svg viewBox="0 0 20 16" width="24" height="20" style={{ verticalAlign: 'middle', marginRight: 6 }}>
      <path d="M1 3a1 1 0 011-1h5l2.5 2.5H19a1 1 0 011 1v10a1 1 0 01-1 1H2a1 1 0 01-1-1V3z" fill="none" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
}

/** 频道列表图标 */
export function ChannelSvg() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16">
      <rect x="1" y="2" width="14" height="12" rx="1" fill="none" stroke="#58a6ff" strokeWidth="1.2"/>
      <line x1="4" y1="6" x2="12" y2="6" stroke="#58a6ff" strokeWidth="1"/>
      <line x1="4" y1="9" x2="10" y2="9" stroke="#58a6ff" strokeWidth="1"/>
    </svg>
  );
}

/** 大脑图标 — Thinking Map 按钮 */
export function BrainSvg() {
  return (
    <svg viewBox="0 0 20 20" width="16" height="16" style={{ verticalAlign: 'middle', marginRight: 4 }}>
      <path d="M10 2C7.5 2 5.5 4 5.5 6.5c0 .8.2 1.5.5 2.2C4.5 9.5 3 11 3 13c0 2 1.5 3.5 3.5 3.5.5 0 1-.1 1.5-.3.8 1 2 1.8 3.5 1.8s2.7-.8 3.5-1.8c.5.2 1 .3 1.5.3 2 0 3.5-1.5 3.5-3.5 0-2-1.5-3.5-3-4.3.3-.7.5-1.4.5-2.2C17.5 4 15.5 2 13 2c-1 0-1.8.4-2.5 1L10 3.5 9.5 3C8.8 2.4 8 2 7 2z"
        fill="none" stroke="#bc8cff" strokeWidth="1.3" strokeLinejoin="round"/>
      <path d="M9 9c0-1 .8-2 1.5-2.5" fill="none" stroke="#bc8cff" strokeWidth="1" strokeLinecap="round"/>
      <path d="M11 9c0-1-.8-2-1.5-2.5" fill="none" stroke="#bc8cff" strokeWidth="1" strokeLinecap="round"/>
    </svg>
  );
}

/** 项目文件夹图标 */
export function ProjectFolderSvg() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16">
      <path d="M1 3a1 1 0 011-1h4l2 2h7a1 1 0 011 1v8a1 1 0 01-1 1H2a1 1 0 01-1-1V3z" fill="none" stroke="#58a6ff" strokeWidth="1.2"/>
    </svg>
  );
}

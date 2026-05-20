/**
 * 🌸 秘密花园 — 坐山客内心世界入口
 *
 * 独立于其他管理页面的沉浸空间。
 * 暗色生物荧光风格，暗合中国园林的曲径通幽。
 */
import { useEffect, useState, useRef } from 'react';
import { useStore } from '../stores/appStore';
import { getSecretGarden, GardenData } from '../api/client';

const MOOD_MAP: Record<string, { emoji: string; label: string; color: string }> = {
  idle:     { emoji: '😌', label: '静候',    color: '#6b9eff' },
  watching: { emoji: '👀', label: '注视',    color: '#00d4ff' },
  thinking: { emoji: '🤔', label: '沉思',    color: '#b388ff' },
  amused:   { emoji: '😊', label: '欣然',    color: '#69f0ae' },
  annoyed:  { emoji: '😠', label: '微恼',    color: '#ff6e6e' },
  speaking: { emoji: '🗣️', label: '言语',    color: '#ffab40' },
  resting:  { emoji: '😴', label: '安眠',    color: '#7e8a9e' },
};

const LEVEL_LABELS: Record<number, string> = {
  0: '✨', 1: '🌟', 2: '💫', 3: '⭐',
};

function MemoryFlower({ item }: { item: GardenData['memory_garden']['items'][0] }) {
  const hue = (item.weight * 40 + 180) % 360;
  return (
    <div className="garden-memory-flower" style={{ '--flower-h': hue } as React.CSSProperties}>
      <span className="garden-memory-level">{LEVEL_LABELS[item.level] || '·'}</span>
      <span className="garden-memory-content">{item.content}</span>
      <span className="garden-memory-weight" style={{ color: `hsla(${hue}, 80%, 65%, 0.6)` }}>
        {item.weight}
      </span>
    </div>
  );
}

/** 计数器动画 — 从 0 增长到目标值 */
function AnimatedCounter({ value, duration = 1200 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const prevRef = useRef(0);

  useEffect(() => {
    const from = prevRef.current;
    const start = performance.now();
    const diff = value - from;
    if (diff === 0) { setDisplay(value); return; }

    const animate = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(from + diff * eased));
      if (t < 1) requestAnimationFrame(animate);
      else { prevRef.current = value; }
    };
    requestAnimationFrame(animate);
  }, [value, duration]);

  return <>{display}</>;
}

/** 🌿 动态花园 SVG 场景 — 500px 宽版 v2
 *
 * 松树扎根地上、科技法杖、动态星空风衣、护目镜亮眼
 * ⚠️ 双层 <g>：外层 transform 设位置，内层 animation 做相对动画
 */
function GardenSceneSvg({ mood }: { mood: string }) {
  const glowColor = MOOD_MAP[mood]?.color || '#6b9eff';

  return (
    <svg className="garden-scene-svg" viewBox="0 0 500 190" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#08081a" />
          <stop offset="60%" stopColor="#0e0e24" />
          <stop offset="100%" stopColor="#14142e" />
        </linearGradient>
        <linearGradient id="grassGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1a3a2a" />
          <stop offset="100%" stopColor="#0d1f15" />
        </linearGradient>
        <radialGradient id="moodGlow">
          <stop offset="0%" stopColor={glowColor} stopOpacity="0.35" />
          <stop offset="100%" stopColor={glowColor} stopOpacity="0" />
        </radialGradient>
        {/* 星空渐变用于风衣 */}
        <radialGradient id="coatStar" cx="0.3" cy="0.2" r="0.8">
          <stop offset="0%" stopColor="#1a2a4a" />
          <stop offset="60%" stopColor="#0d1a2a" />
          <stop offset="100%" stopColor="#0a1520" />
        </radialGradient>
      </defs>

      {/* 夜空 */}
      <rect width="500" height="190" fill="url(#skyGrad)" />

      {/* 更多星星 */}
      {[
        [40,18],[80,32],[130,12],[190,25],[240,15],[300,30],[350,10],[400,22],[450,28],[480,16],
        [60,40],[150,35],[270,20],[380,35],[430,8],[20,28],[110,45],[210,10],[320,38],[460,40],
      ].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r="1" fill="#fff" opacity="0.5"
          className={`star-${i % 3}`} />
      ))}

      {/* 月亮 */}
      <circle cx="440" cy="35" r="30" fill="url(#moodGlow)" className="mood-glow-pulse" />
      <circle cx="440" cy="35" r="10" fill={glowColor} opacity="0.15" className="mood-glow-pulse" />
      <circle cx="440" cy="35" r="5" fill={glowColor} opacity="0.3" />
      <circle cx="442" cy="33" r="2" fill="#fff" opacity="0.4" />

      {/* 远山 */}
      <path d="M0 105 Q40 80 90 100 Q140 70 200 95 Q270 60 340 90 Q410 55 500 85 L500 135 L0 135 Z"
        fill="#12121e" opacity="0.5" />

      {/* 远景小松树（山前） */}
      <g transform="translate(65, 82)"><g className="tree-sway">
        <rect x="3" y="20" width="4" height="20" fill="#3a2a1a" rx="1" opacity="0.35" />
        <polygon points="5,-5 -8,18 18,18" fill="#1a3a2a" opacity="0.35" />
        <polygon points="5,5 -6,25 16,25" fill="#1a4a3a" opacity="0.3" />
      </g></g>
      <g transform="translate(455, 85)"><g className="tree-sway" style={{ animationDelay: '0.7s' }}>
        <rect x="3" y="18" width="4" height="18" fill="#3a2a1a" rx="1" opacity="0.35" />
        <polygon points="5,-4 -7,16 17,16" fill="#1a3a2a" opacity="0.35" />
        <polygon points="5,4 -5,22 15,22" fill="#1a4a3a" opacity="0.3" />
      </g></g>

      {/* 草地 */}
      <path d="M0 130 Q100 118 200 125 Q300 115 400 122 Q460 112 500 120 L500 190 L0 190 Z"
        fill="url(#grassGrad)" className="grass-sway" />

      {/* 草叶 */}
      {[
        [15,125,8],[30,122,6],[50,124,7],[70,120,9],[90,123,6],
        [130,121,7],[160,124,5],[190,119,8],[220,122,6],[250,120,7],
        [290,123,6],[320,119,8],[360,122,5],[390,120,7],[420,122,6],
        [450,118,8],[480,121,6],
      ].map(([x, y, h], i) => (
        <path key={`gl-${i}`} d={`M${x} ${y} Q${x - 2} ${y - h} ${x - 1} ${y - h - 2}`}
          stroke="#2a5a3a" strokeWidth="1.5" fill="none" opacity="0.5"
          className={`grass-blade-${i % 3}`} />
      ))}

      {/* 花朵 */}
      {[
        [22,125,'#ff6b8a',1.8],[45,123,'#ffd93d',1.5],[75,121,'#ff8aeb',1.6],
        [145,122,'#6bcfff',1.4],[175,120,'#ff6b6b',1.7],[220,121,'#a8e6cf',1.3],
        [310,122,'#ffd93d',1.5],[345,120,'#ff6b8a',1.6],
        [460,119,'#a8e6cf',1.4],[480,121,'#ff8aeb',1.3],
      ].map(([fx, fy, color, size], i) => (
        <g key={`f-${i}`} className="flower-bloom">
          {[0, 72, 144, 216, 288].map(angle => (
            <line key={angle} x1={fx} y1={fy} x2={fx} y2={fy - (size as number) * 4}
              stroke={color as string} strokeWidth="1.5" opacity="0.6"
              transform={`rotate(${angle}, ${fx}, ${fy})`} strokeLinecap="round" />
          ))}
          <circle cx={fx} cy={fy} r="1.5" fill={color as string} opacity="0.8" />
        </g>
      ))}

      {/* ─── 🌲 松树群（均匀分布，根部接地 y=120） ─── */}
      <g transform="translate(30, 82)"><g className="tree-sway">
        <rect x="5" y="30" width="7" height="35" rx="2" fill="#4a3520" opacity="0.6" />
        <polygon points="8,-12 -18,30 34,30" fill="#1a5a2a" opacity="0.7" />
        <polygon points="8,8 -22,40 38,40" fill="#1a6a3a" opacity="0.6" />
        <polygon points="8,25 -14,48 30,48" fill="#1a5a2a" opacity="0.5" />
      </g></g>

      <g transform="translate(100, 86)"><g className="tree-sway" style={{ animationDelay: '0.3s' }}>
        <rect x="3" y="22" width="5" height="28" rx="1" fill="#4a3520" opacity="0.5" />
        <polygon points="5,-8 -12,22 22,22" fill="#1a5a2a" opacity="0.65" />
        <polygon points="5,6 -14,32 24,32" fill="#1a6a3a" opacity="0.55" />
      </g></g>

      <g transform="translate(370, 84)"><g className="tree-sway" style={{ animationDelay: '0.5s' }}>
        <rect x="4" y="26" width="6" height="30" rx="1" fill="#4a3520" opacity="0.55" />
        <polygon points="7,-10 -15,26 29,26" fill="#1a5a2a" opacity="0.65" />
        <polygon points="7,7 -18,36 32,36" fill="#1a6a3a" opacity="0.55" />
      </g></g>

      <g transform="translate(460, 88)"><g className="tree-sway" style={{ animationDelay: '0.2s' }}>
        <rect x="3" y="20" width="4" height="24" rx="1" fill="#4a3520" opacity="0.45" />
        <polygon points="5,-6 -10,20 20,20" fill="#1a5a2a" opacity="0.6" />
        <polygon points="5,5 -12,28 22,28" fill="#1a6a3a" opacity="0.5" />
      </g></g>

      {/* 远景小树 (中景) */}
      <g transform="translate(160, 90)"><g className="tree-sway" style={{ animationDelay: '0.6s' }}>
        <rect x="2" y="18" width="4" height="20" rx="1" fill="#3a2a1a" opacity="0.4" />
        <polygon points="4,-5 -8,16 16,16" fill="#1a3a2a" opacity="0.45" />
        <polygon points="4,4 -9,24 17,24" fill="#1a4a3a" opacity="0.4" />
      </g></g>

      {/* ─── 🧙 坐山客 Avatar v2 — 酷+科技 ─── */}
      <g transform="translate(200, 42)">
       <g className="avatar-stand">
        {/* 脚下光环 */}
        <ellipse cx="0" cy="98" rx="22" ry="3" fill={glowColor} opacity="0.08" className="avatar-glow-ring" />

        {/* 风衣本体（带星空渐变） */}
        <path d="M-11 28 L-17 58 Q-19 73 -13 88 L-9 98 L9 98 L13 88 Q19 73 17 58 L11 28 Z"
          fill="url(#coatStar)" stroke={glowColor} strokeWidth="0.4" strokeOpacity="0.25" />

        {/* 风衣上流动的星辰（动态星空效果） */}
        <circle cx="-6" cy="45" r="0.6" fill="#fff" opacity="0.3" className="star-drift-1" />
        <circle cx="4" cy="55" r="0.5" fill="#fff" opacity="0.25" className="star-drift-2" />
        <circle cx="-3" cy="65" r="0.7" fill={glowColor} opacity="0.3" className="star-drift-3" />
        <circle cx="5" cy="75" r="0.4" fill="#fff" opacity="0.2" className="star-drift-1" />
        <circle cx="-2" cy="80" r="0.6" fill={glowColor} opacity="0.25" className="star-drift-2" />
        <circle cx="7" cy="50" r="0.5" fill="#fff" opacity="0.2" className="star-drift-3" />
        <circle cx="-5" cy="70" r="0.4" fill={glowColor} opacity="0.2" className="star-drift-1" />

        {/* 风衣下摆飘动 */}
        <path d="M-9 98 L-14 105 L-7 102 L0 107 L7 102 L14 105 L9 98 Z"
          fill="#0d1a2a" stroke={glowColor} strokeWidth="0.3" strokeOpacity="0.15"
          className="coat-sway" />

        {/* 高立领 */}
        <path d="M-6 17 L-11 33 L11 33 L6 17 Z" fill="#0f1a2a" />

        {/* 兜帽头 */}
        <path d="M-8 17 Q-11 4 0 -3 Q11 4 8 17 Z" fill="#0a1220"
          stroke={glowColor} strokeWidth="0.4" strokeOpacity="0.15" />

        {/* 🔆 V 型发光护目镜（加大加亮） */}
        <g>
          <path d="M-6 7 L-1 12 L4 7" stroke={glowColor} strokeWidth="1.5" fill="none"
            opacity="0.9" className="visor-glow" strokeLinecap="round" strokeLinejoin="round" />
          {/* 护目镜两侧光晕 */}
          <circle cx="-5" cy="9" r="2" fill={glowColor} opacity="0.15" />
          <circle cx="3" cy="9" r="2" fill={glowColor} opacity="0.15" />
          {/* 镜片横梁 */}
          <line x1="-6" y1="9" x2="4" y2="9" stroke={glowColor} strokeWidth="0.3" opacity="0.15" />
        </g>

        {/* 右臂 — 握科技法杖 */}
        <path d="M11 33 L20 48 Q22 52 20 56 L17 58"
          stroke="#0d1a2a" strokeWidth="3.5" fill="none" strokeLinecap="round" />
        {/* 左手 */}
        <path d="M-11 33 L-16 48 Q-18 52 -16 56"
          stroke="#0d1a2a" strokeWidth="3" fill="none" strokeLinecap="round" />

        {/* ⚡ 科技法杖 — 酷炫能量杖 */}
        <g>
          {/* 杖身 — 细长能量管 */}
          <line x1="20" y1="-8" x2="20" y2="75" stroke="#1a3a5a" strokeWidth="1.8" opacity="0.6" />
          {/* 杖身能量纹路 */}
          <line x1="20" y1="-5" x2="20" y2="75" stroke={glowColor} strokeWidth="0.6"
            opacity="0.2" strokeDasharray="3 4" className="energy-flow" />
          {/* 能量环（浮动环） */}
          <ellipse cx="20" cy="55" rx="5" ry="1.5" fill="none" stroke={glowColor}
            strokeWidth="0.5" opacity="0.3" className="hover-ring" />
          <ellipse cx="20" cy="35" rx="4" ry="1.2" fill="none" stroke={glowColor}
            strokeWidth="0.4" opacity="0.2" className="hover-ring" style={{ animationDelay: '0.4s' }} />
          {/* 杖顶能量核心 */}
          <circle cx="20" cy="-8" r="4" fill={glowColor} opacity="0.1" className="core-glow" />
          <circle cx="20" cy="-8" r="2.5" fill={glowColor} opacity="0.25" />
          <circle cx="20" cy="-8" r="1.2" fill="#fff" opacity="0.5" className="core-pulse" />
          {/* 能量尖刺（四向） */}
          <line x1="20" y1="-14" x2="20" y2="-6" stroke={glowColor} strokeWidth="0.8" opacity="0.4" />
          <line x1="14" y1="-8" x2="26" y2="-8" stroke={glowColor} strokeWidth="0.8" opacity="0.4" />
          <line x1="15.5" y1="-12" x2="24.5" y2="-4" stroke={glowColor} strokeWidth="0.5" opacity="0.2" />
          <line x1="24.5" y1="-12" x2="15.5" y2="-4" stroke={glowColor} strokeWidth="0.5" opacity="0.2" />
        </g>

        {/* 悬浮粒子绕身 */}
        <circle cx="-13" cy="48" r="0.8" fill={glowColor} opacity="0.3" className="orb-1" />
        <circle cx="12" cy="68" r="0.7" fill={glowColor} opacity="0.25" className="orb-2" />
        <circle cx="-6" cy="78" r="1" fill={glowColor} opacity="0.3" className="orb-3" />
        <circle cx="16" cy="42" r="0.6" fill={glowColor} opacity="0.2" className="orb-1" />
       </g>
      </g>

      {/* ─── 🐰 小兔子 — 草间蹦跳 ─── */}
      <g transform="translate(260, 96)"><g className="rabbit-hop">
        <ellipse cx="0" cy="8" rx="5.5" ry="4.5" fill="#d4c8b8" opacity="0.65" />
        <circle cx="6" cy="3" r="3.5" fill="#d4c8b8" opacity="0.65" />
        <ellipse cx="5" cy="-4" rx="1.3" ry="4.5" fill="#d4c8b8" opacity="0.55" />
        <ellipse cx="8" cy="-3" rx="1.3" ry="4" fill="#d4c8b8" opacity="0.55" />
        <ellipse cx="5" cy="-4" rx="0.7" ry="3" fill="#f0c8b8" opacity="0.35" />
        <ellipse cx="8" cy="-3" rx="0.7" ry="2.5" fill="#f0c8b8" opacity="0.35" />
        <circle cx="7.5" cy="2" r="0.7" fill="#333" opacity="0.55" />
        <circle cx="-4.5" cy="7" r="1.8" fill="#f0e8d8" opacity="0.45" />
      </g></g>

      {/* ─── 🐿️ 小松鼠 — 草地上跑动 ─── */}
      <g transform="translate(320, 99)"><g className="squirrel-run">
        <ellipse cx="0" cy="5" rx="4.5" ry="3.5" fill="#c49a6a" opacity="0.6" />
        <circle cx="5" cy="2" r="3" fill="#c49a6a" opacity="0.6" />
        <path d="M-4 5 Q-10 -2 -7 -7 Q-3 -3 -4 5" fill="#b8895a" opacity="0.45" className="tail-sway" />
        <path d="M4.5 0 L4 -3 L6.5 -1" fill="#c49a6a" opacity="0.45" />
        <circle cx="6.5" cy="1.5" r="0.6" fill="#222" opacity="0.55" />
      </g></g>

      {/* ─── 🦅 小鸟 ─── */}
      <g className="bird-fly"><g>
        <path d="M0 0 Q-3 -4 -6 -2" stroke="#6b9eff" strokeWidth="0.8" fill="none" opacity="0.35" className="wing-flap" />
        <path d="M0 0 Q3 -4 6 -2" stroke="#6b9eff" strokeWidth="0.8" fill="none" opacity="0.35" className="wing-flap" />
        <circle cx="0" cy="0" r="0.8" fill="#6b9eff" opacity="0.25" />
      </g></g>
      <g className="bird-fly" style={{ animationDelay: '2.5s', animationDuration: '7s' }}><g>
        <path d="M0 0 Q-2.5 -3.5 -5 -1.5" stroke="#b388ff" strokeWidth="0.7" fill="none" opacity="0.25" className="wing-flap" />
        <path d="M0 0 Q2.5 -3.5 5 -1.5" stroke="#b388ff" strokeWidth="0.7" fill="none" opacity="0.25" className="wing-flap" />
        <circle cx="0" cy="0" r="0.6" fill="#b388ff" opacity="0.2" />
      </g></g>

      {/* 底部暗边 */}
      <rect x="0" y="178" width="500" height="12" fill="#0a1a10" opacity="0.35" />
    </svg>
  );
}


export function SecretGarden() {
  const { setView } = useStore();
  const [data, setData] = useState<GardenData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [navExpanded, setNavExpanded] = useState(false);
  const gardenRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSecretGarden()
      .then(d => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError('花园尚未开放…'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // 加载状态
  if (loading) {
    return (
      <div className="secret-garden">
        <div className="garden-loading">
          <div className="garden-loading-text">🌸 秘密花园正在苏醒…</div>
          <div className="garden-loading-bar"><div className="garden-loading-fill" /></div>
        </div>
      </div>
    );
  }

  // 出错
  if (error || !data) {
    return (
      <div className="secret-garden">
        <div className="garden-empty">
          <span style={{ fontSize: 48, opacity: 0.5 }}>🌿</span>
          <p style={{ color: '#666', marginTop: 16 }}>{error || '秘密花园尚未建立…'}</p>
          <button className="garden-back-btn" onClick={() => setView('projects')}>← 回到项目</button>
        </div>
      </div>
    );
  }

  const mood = MOOD_MAP[data.mood] || MOOD_MAP.idle;
  const growth = data.growth;
  const milestones = data.milestones;
  const memories = data.memory_garden.items;
  const vitality = growth.scenes * 3 + growth.tools * 2 + growth.skills * 3 + growth.thoughts + growth.channels;

  return (
    <div className="secret-garden" ref={gardenRef}>
      {/* ═══ 全屏星光粒子（闪烁动画） ═══ */}
      <div className="garden-particles garden-particles-animated" />

      {/* ═══ 顶栏 ═══ */}
      <div className="garden-topbar">
        <button className="garden-back-btn" onClick={() => setView('chat')}>← 回廊</button>
        <span className="garden-topbar-title">🌸 秘密花园</span>
        <button className="garden-nav-btn" onClick={() => setNavExpanded(!navExpanded)} title="园中路径">
          {navExpanded ? '✕' : '☰'}
        </button>
      </div>

      {/* ═══ 导航浮层 ═══ */}
      {navExpanded && (
        <div className="garden-nav-overlay" onClick={() => setNavExpanded(false)}>
          <div className="garden-nav-menu" onClick={e => e.stopPropagation()}>
            <a href="#garden-mood" onClick={() => { setNavExpanded(false); }}>🌸 心绪</a>
            <a href="#garden-memory" onClick={() => { setNavExpanded(false); }}>🌿 记忆花园</a>
            <a href="#garden-growth" onClick={() => { setNavExpanded(false); }}>🌳 成长年轮</a>
            <a href="#garden-milestones" onClick={() => { setNavExpanded(false); }}>✨ 协作金石</a>
            <a href="#garden-inner" onClick={() => { setNavExpanded(false); }}>🗺️ 内在风景</a>
          </div>
        </div>
      )}

      <div className="garden-scroll">
        {/* ═══ 区域① 心绪 — 动态双栏布局 ═══ */}
        <section id="garden-mood" className="garden-section">
          <div className="garden-mood-dual">
            {/* 左栏：状态 + 动态生命力卡片 */}
            <div className="garden-mood-left">
              <div className="garden-mood-card">
                <div className="garden-mood-glow mood-pulse"
                  style={{ background: `radial-gradient(ellipse at center, ${mood.color}22 0%, transparent 70%)` }} />
                <div className="garden-mood-icon">{mood.emoji}</div>
                <div className="garden-mood-info">
                  <div className="garden-mood-name">{data.name}</div>
                  <div className="garden-mood-state" style={{ color: mood.color }}>
                    {mood.label}
                  </div>
                  {data.observation && (
                    <div className="garden-mood-obs">"{data.observation}"</div>
                  )}
                </div>

                {/* 动态生命力卡片 */}
                <div className="garden-vitality-card">
                  <div className="garden-vitality-value">
                    <AnimatedCounter value={vitality} />
                  </div>
                  <div className="garden-vitality-label">生命力</div>
                  <div className="garden-vitality-bar">
                    <div className="garden-vitality-fill" style={{ width: `${Math.min((vitality / 500) * 100, 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>

            {/* 右栏：动画花园场景 */}
            <div className="garden-mood-right">
              <GardenSceneSvg mood={data.mood} />
            </div>
          </div>
        </section>

        {/* ═══ 区域② 记忆花园 ═══ */}
        <section id="garden-memory" className="garden-section">
          <h2 className="garden-section-title">
            🌿 记忆花园
            <span className="garden-section-count">{data.memory_garden.total} 朵</span>
          </h2>
          <div className="garden-memory-grid">
            {memories.length > 0 ? (
              memories.map((item, i) => (
                <MemoryFlower key={item.key || i} item={item} />
              ))
            ) : (
              <div className="garden-empty-hint">记忆如种子，尚未发芽…</div>
            )}
          </div>
        </section>

        {/* ═══ 区域③ 成长年轮 ═══ */}
        <section id="garden-growth" className="garden-section">
          <h2 className="garden-section-title">
            🌳 成长年轮
            <span className="garden-section-count">{growth.versions}</span>
          </h2>
          <div className="garden-growth-grid">
            <div className="garden-ring" style={{ '--hue': '200' } as React.CSSProperties}>
              <div className="garden-ring-value"><AnimatedCounter value={growth.scenes} /></div>
              <div className="garden-ring-label">场景</div>
            </div>
            <div className="garden-ring" style={{ '--hue': '160' } as React.CSSProperties}>
              <div className="garden-ring-value"><AnimatedCounter value={growth.tools} /></div>
              <div className="garden-ring-label">工具</div>
            </div>
            <div className="garden-ring" style={{ '--hue': '280' } as React.CSSProperties}>
              <div className="garden-ring-value"><AnimatedCounter value={growth.skills} /></div>
              <div className="garden-ring-label">技能</div>
            </div>
            <div className="garden-ring" style={{ '--hue': '40' } as React.CSSProperties}>
              <div className="garden-ring-value"><AnimatedCounter value={growth.channels} /></div>
              <div className="garden-ring-label">频道</div>
            </div>
            <div className="garden-ring" style={{ '--hue': '340' } as React.CSSProperties}>
              <div className="garden-ring-value"><AnimatedCounter value={growth.thoughts} /></div>
              <div className="garden-ring-label">思绪</div>
            </div>
          </div>
        </section>

        {/* ═══ 区域④ 协作金石 ═══ */}
        <section id="garden-milestones" className="garden-section">
          <h2 className="garden-section-title">
            ✨ 协作金石
            <span className="garden-section-count">{milestones.length} 刻</span>
          </h2>
          <div className="garden-timeline">
            {milestones.map((m, i) => (
              <div key={i} className="garden-milestone">
                <div className="garden-milestone-line" />
                <div className="garden-milestone-dot">{m.icon}</div>
                <div className="garden-milestone-body">
                  <span className="garden-milestone-date">{m.date}</span>
                  <span className="garden-milestone-text">{m.text}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ 区域⑤ 内在风景 ═══ */}
        <section id="garden-inner" className="garden-section" style={{ marginBottom: 40 }}>
          <h2 className="garden-section-title">🗺️ 内在风景</h2>
          <div className="garden-inner-grid">
            <div className="garden-inner-card">
              <div className="garden-inner-icon">🧠</div>
              <div className="garden-inner-label">本体记忆</div>
              <div className="garden-inner-stat">{data.memory_garden.total}</div>
            </div>
            <div className="garden-inner-card">
              <div className="garden-inner-icon">🤖</div>
              <div className="garden-inner-label">Agent Loop</div>
              <div className="garden-inner-stat">v1.0</div>
            </div>
            <div className="garden-inner-card">
              <div className="garden-inner-icon">🎭</div>
              <div className="garden-inner-label">身份架构</div>
              <div className="garden-inner-stat">v0.8</div>
            </div>
            <div className="garden-inner-card">
              <div className="garden-inner-icon">🌐</div>
              <div className="garden-inner-label">系统版本</div>
              <div className="garden-inner-stat">{growth.versions}</div>
            </div>
          </div>
        </section>

        {/* ═══ 底部 ═══ */}
        <div className="garden-footer">
          <span className="garden-updated">🌙 花园静谧 · 万物生长</span>
        </div>
      </div>
    </div>
  );
}

/**
 * AgentCharacter — 坐山客 AI 角色动画组件（Schema v0.8）
 *
 * position:fixed 浮在页面顶部，叠在 Topbar 上层。
 * 不再依赖 Zustand store 的状态驱动，改为轮询后端本体状态 API。
 * 表情反映坐山客本体的真实心情（mood），不是场景的分身状态。
 */
import { useEffect, useState, useRef } from 'react';
import type { AgentStatus } from '../stores/appStore';

interface AgentCharacterProps {
  status?: AgentStatus;
  message?: string;
  hidden?: boolean;
}

const EYE: Record<string, { L: string; R: string }> = {
  closed:  { L:'M31 17 Q33 16 35 17',    R:'M37 17 Q39 16 41 17' },
  open:    { L:'M30 16 Q32 14.5 34 16',  R:'M38 16 Q40 14.5 42 16' },
  side:    { L:'M30 16 Q31 15 32 16',    R:'M38 16 Q39 15 40 16' },
  focused: { L:'M30 16 Q32 15 34 16',    R:'M38 16 Q40 15 42 16' },
  happy:   { L:'M30.5 15.5 Q32 14.5 33.5 15.5', R:'M38.5 15.5 Q40 14.5 41.5 15.5' },
  worried: { L:'M30.5 18 Q32 19 33.5 18', R:'M38.5 18 Q40 19 41.5 18' },
  zzz:     { L:'M31 17 Q33 16.5 35 17',  R:'M37 17 Q39 16.5 41 17' },
  angry:   { L:'M29 16 L35 17',          R:'M37 17 L43 16' },
  laughTears:{ L:'M30.5 15.5 Q32 14 33.5 15.5', R:'M38.5 15.5 Q40 14 41.5 15.5' },
  sadTears:{ L:'M30 18 Q32 19.5 34 18',  R:'M38 18 Q40 19.5 42 18' },
};

const MOUTH: Record<string, string> = {
  smile:   'M33 24 Q36 25.5 39 24',
  bigSmile:'M32 24 Q36 27 40 24',
  neutral: 'M33 24 L39 24',
  pursed:  'M33.5 24 Q36 23.5 38.5 24',
  big:     'M32 24 Q36 27.5 40 24',
  frown:   'M33 25 Q36 23.5 39 25',
  gnash:   'M33 24 L34 25 L35 24 L36 25 L37 24 L38 25 L39 24',
  rofl:    'M31 24 Q36 28.5 41 24',
  cry:     'M33 25.5 Q36 24.5 39 25.5',
};

const STATE_MAP: Record<AgentStatus, {
  eyes: keyof typeof EYE; mouth: keyof typeof MOUTH;
  defaultMsg: string; color: string; classSuffix: string;
  showLaughTears?: boolean; showSadTears?: boolean; showSweat?: boolean;
}> = {
  idle:     { eyes:'closed', mouth:'smile',   defaultMsg:'在线待命',   color:'#58a6ff', classSuffix:'idle' },
  greeting: { eyes:'open',   mouth:'bigSmile',defaultMsg:'来了啊！👋', color:'#00d4ff', classSuffix:'greeting' },
  thinking: { eyes:'side',   mouth:'pursed',  defaultMsg:'让我想想',  color:'#d29922', classSuffix:'thinking' },
  working:  { eyes:'focused',mouth:'neutral', defaultMsg:'拼命处理中💦',color:'#bc8cff', classSuffix:'working', showSweat:true },
  analyzing:{ eyes:'focused',mouth:'neutral', defaultMsg:'分析数据中', color:'#58a6ff', classSuffix:'analyzing' },
  done:     { eyes:'happy',  mouth:'big',     defaultMsg:'搞定！✅',   color:'#3fb950', classSuffix:'done' },
  error:    { eyes:'worried',mouth:'frown',   defaultMsg:'出问题了⚠️',color:'#f85149', classSuffix:'error' },
  notify:   { eyes:'open',   mouth:'smile',   defaultMsg:'有情况！',  color:'#00d4ff', classSuffix:'notify' },
  resting:  { eyes:'zzz',     mouth:'smile',   defaultMsg:'zzZ...',   color:'#6e7681', classSuffix:'idle' },
  angry:    { eyes:'angry',   mouth:'gnash',   defaultMsg:'哼！',     color:'#f85149', classSuffix:'error' },
  laugh:    { eyes:'laughTears',mouth:'rofl',  defaultMsg:'哈哈哈😂', color:'#3fb950', classSuffix:'done', showLaughTears:true },
  sad:      { eyes:'sadTears',mouth:'cry',     defaultMsg:'呜...😢',  color:'#58a6ff', classSuffix:'idle', showSadTears:true },
};

// 🆕 Schema v0.8: 后端 mood → 前端 AgentStatus 映射
const MOOD_TO_STATUS: Record<string, AgentStatus> = {
  idle:     'idle',
  watching: 'notify',
  analyzing:'analyzing',
  thinking: 'thinking',
  amused:   'laugh',
  annoyed:  'angry',
  speaking: 'greeting',
  resting:  'resting',
};

/** 轮询后端本体状态 */
async function fetchZhuMood(): Promise<{ mood: string; observation: string } | null> {
  try {
    const res = await fetch('/api/zhu-agent/status');
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export function AgentCharacter({ status: propStatus, message: propMessage, hidden = false }: AgentCharacterProps) {
  // 🆕 本体状态（轮询自后端）
  const [zhuMood, setZhuMood] = useState<string>('idle');
  const [zhuObservation, setZhuObservation] = useState<string>('');

  // 🆕 轮询本体状态
  useEffect(() => {
    let active = true;
    const poll = async () => {
      const data = await fetchZhuMood();
      if (!active) return;
      if (data) {
        setZhuMood(data.mood);
        setZhuObservation(data.observation || '');
      }
    };
    poll(); // 立即拉一次
    const interval = setInterval(poll, 3000); // 每 3s 轮询
    return () => { active = false; clearInterval(interval); };
  }, []);

  // 🆕 本体 mood → AgentStatus（若后端不可达，兜底 idle）
  const effectiveStatus: AgentStatus = MOOD_TO_STATUS[zhuMood] || 'idle';
  const cfg = STATE_MAP[effectiveStatus] || STATE_MAP.idle;
  const msg = zhuObservation || cfg.defaultMsg;
  const eye = EYE[cfg.eyes] || EYE.closed;
  const mouthPath = MOUTH[cfg.mouth] || MOUTH.smile;
  const animClass = `char-${cfg.classSuffix}`;

  // Bubble show animation: 只有后端传了 observation 才弹气泡
  const [bubbleShow, setBubbleShow] = useState(false);
  const prevObsRef = useRef(zhuObservation);
  useEffect(() => {
    setBubbleShow(false);
    if (!zhuObservation) return; // 空 observation 不弹气泡
    const show = setTimeout(() => setBubbleShow(true), 50);
    // 根据文本长度决定停留时间：短文案4s，长歌词8s
    const duration = Math.min(Math.max(zhuObservation.length * 100, 4000), 8000);
    const hide = setTimeout(() => setBubbleShow(false), duration);
    prevObsRef.current = zhuObservation;
    return () => { clearTimeout(show); clearTimeout(hide); };
  }, [zhuObservation, zhuMood]);

  return (
    <div className="agent-char-area">
      <div className={`agent-char-container${hidden ? ' agent-char-hidden' : ''} ${animClass}`}>
        <div className="agent-char-canvas">
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
            <path d="M24 16 Q28 14 36 14 Q44 14 48 16 L48 20 Q44 22 36 22 Q28 22 24 20 Z" fill="url(#visorGrad)" stroke="#00d4ff" strokeWidth="0.7" opacity="0.7" className="visor-glow"/>
            <path d="M26 17 Q30 16 34 16 L35 17 L33 18 Q29 18 26 17 Z" fill="#00d4ff" opacity="0.1"/>
            <circle cx="36" cy="18" r="1.3" fill="#00d4ff" opacity="0.2" filter="url(#neonGlow)"/>
            <circle cx="26" cy="18" r="0.7" fill="#00d4ff" opacity="0.3" filter="url(#neonGlow)"/>
            <circle cx="46" cy="18" r="0.7" fill="#00d4ff" opacity="0.3" filter="url(#neonGlow)"/>
            <path d="M25 16 Q31 14.5 36 14.5 Q41 14.5 47 16" fill="none" stroke="#00d4ff" strokeWidth="0.35" opacity="0.45"/>
            <g><path d={eye.L} fill="none" stroke="#00d4ff" strokeWidth="1" strokeLinecap="round"/><path d={eye.R} fill="none" stroke="#00d4ff" strokeWidth="1" strokeLinecap="round"/></g>
            <path d={mouthPath} fill="none" stroke="#3d4a5c" strokeWidth="0.7" strokeLinecap="round"/>
            <g opacity={cfg.showLaughTears ? 1 : 0}>
              <path d="M27 18 Q23 15 21 13" fill="none" stroke="#00d4ff" strokeWidth="0.8" strokeLinecap="round" opacity="0.6"/>
              <path d="M45 18 Q49 15 51 13" fill="none" stroke="#00d4ff" strokeWidth="0.8" strokeLinecap="round" opacity="0.6"/>
              <circle cx="20" cy="12" r="1.2" fill="#00d4ff" opacity="0.4"/><circle cx="52" cy="12" r="1.2" fill="#00d4ff" opacity="0.4"/>
              <circle cx="22" cy="10" r="0.8" fill="#00d4ff" opacity="0.3"/><circle cx="50" cy="10" r="0.8" fill="#00d4ff" opacity="0.3"/>
            </g>
            <g opacity={cfg.showSadTears ? 1 : 0}>
              <path d="M30 21 Q29 25 28 30" fill="none" stroke="#00d4ff" strokeWidth="0.7" strokeLinecap="round" opacity="0.5"/>
              <path d="M29 30 Q28 34 27 38" fill="none" stroke="#00d4ff" strokeWidth="0.5" strokeLinecap="round" opacity="0.3"/>
              <circle cx="28" cy="32" r="1" fill="#00d4ff" opacity="0.35"/><circle cx="27" cy="38" r="0.8" fill="#00d4ff" opacity="0.25"/>
              <path d="M42 21 Q43 25 44 30" fill="none" stroke="#00d4ff" strokeWidth="0.7" strokeLinecap="round" opacity="0.5"/>
              <path d="M43 30 Q44 34 45 38" fill="none" stroke="#00d4ff" strokeWidth="0.5" strokeLinecap="round" opacity="0.3"/>
              <circle cx="44" cy="32" r="1" fill="#00d4ff" opacity="0.35"/><circle cx="45" cy="38" r="0.8" fill="#00d4ff" opacity="0.25"/>
            </g>
            <g opacity={cfg.showSweat ? 1 : 0}>
              <path d="M22 12 Q20 10 21 8" fill="none" stroke="#00d4ff" strokeWidth="0.8" strokeLinecap="round" opacity="0.5"/>
              <path d="M50 12 Q52 10 51 8" fill="none" stroke="#00d4ff" strokeWidth="0.8" strokeLinecap="round" opacity="0.5"/>
              <circle cx="20" cy="8" r="1" fill="#00d4ff" opacity="0.35"/>
              <circle cx="52" cy="8" r="1" fill="#00d4ff" opacity="0.35"/>
              <circle cx="23" cy="10" r="0.7" fill="#00d4ff" opacity="0.25"/>
              <circle cx="49" cy="10" r="0.7" fill="#00d4ff" opacity="0.25"/>
            </g>
            <circle cx="47" cy="16" r="2" fill="none" stroke="#00d4ff" strokeWidth="0.4" opacity="0.3"/>
            <circle cx="47" cy="16" r="0.5" fill="#00d4ff" opacity="0.2" filter="url(#neonGlow)"/>
          </svg>
        </div>
        {/* Bubble */}
        <div className={`agent-char-bubble${bubbleShow ? ' show' : ''}`}>
          <span className="agent-char-dot" style={{ background: cfg.color }} />
          <span className="agent-char-text">{msg}</span>
        </div>
        {/* 调试：hover 显示当前 mood */}
        <div className="agent-char-label">{zhuMood}</div>
      </div>
    </div>
  );
}

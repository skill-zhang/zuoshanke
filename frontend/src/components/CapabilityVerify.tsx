/** 🧪 能力验证 — 展示 Agent Loop 里程碑成就 */
import { useEffect, useState, useRef } from 'react';
import { showAlert } from '../stores/dialogStore';

// ── 里程碑数据类型 ──
export interface Milestone {
  id: string;
  title: string;
  description: string;
  icon: string;
  date: string;
  status: 'verified' | 'pending' | 'failed';
  artifactPath?: string;   // 验证产物路径（前端可访问）
  artifactType?: 'html' | 'image' | 'text' | 'url';
  steps: number;           // Agent Loop 执行的步数
  llmModel: string;
}

// ── 预设里程碑（硬编码？不！后面提到 config 去） ──
const DEFAULT_MILESTONES: Milestone[] = [
  {
    id: 'snake-game',
    title: '🐍 贪吃蛇游戏',
    description: 'Agent Loop 自主编写了一个完整的贪吃蛇游戏（352行/11KB pygame），包括检查环境→安装依赖→编码→语法验证，全程无人干预。随后自主将其转换为网页版（11.9KB 单文件 HTML+Canvas），可直接在浏览器中游玩。',
    icon: '🐍',
    date: '2026-05-18',
    status: 'verified',
    artifactPath: '/snake-game.html',
    artifactType: 'html',
    steps: 14,
    llmModel: 'deepseek-v4-flash',
  },
  {
    id: 'agent-village-adventure',
    title: '🏘️ [Agent自造] 小村庄大冒险',
    description: 'Agent Loop 自主构建的像素风RPG游戏（484行/22KB单文件HTML）。包含50×50地图(山脉/河流/桥/村庄)、3个NPC(对话/给剑)、5种怪物(回合制战斗/掉落)、救援系统(打怪→入队)、背包/装备/升级、胜利条件。全程LLM自主编码，25步分批写入18个文件片段后拼接完成。',
    icon: '🤖',
    date: '2026-05-19',
    status: 'verified',
    artifactPath: '/adventure-game-agent.html',
    artifactType: 'html',
    steps: 25,
    llmModel: 'deepseek-v4-flash',
  },
  {
    id: 'hand-village-adventure',
    title: '🎮 [手工] 小村庄大冒险',
    description: '手动编写(非Agent Loop)的像素风RPG游戏（1473行/43KB单文件HTML）。相同规格：50×50地图、3个NPC、6种怪物、救援系统、回合制战斗、物品掉落、自动装备、背包(数字键用药)、村庄休息回血、全屏放大、胜利条件。功能更丰富但无Agent自主构建过程。对比Agent自造版本展示AI vs 手工的差异。',
    icon: '✍️',
    date: '2026-05-19',
    status: 'verified',
    artifactPath: '/village-adventure.html',
    artifactType: 'html',
    steps: 1,
    llmModel: 'deepseek-v4-flash',
  },
];

export function CapabilityVerify() {
  const [milestones, setMilestones] = useState<Milestone[]>(DEFAULT_MILESTONES);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [artifactContent, setArtifactContent] = useState<string | null>(null);
  const [fullscreenId, setFullscreenId] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const selected = milestones.find(m => m.id === selectedId);
  const fullscreenMilestone = milestones.find(m => m.id === fullscreenId);

  // ── Escape 键关闭全屏 ──
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && fullscreenId) setFullscreenId(null);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [fullscreenId]);

  // ── 加载产物 ──
  const loadArtifact = async (m: Milestone) => {
    setSelectedId(m.id);
    setArtifactContent(null);

    if (m.artifactType === 'html' && m.artifactPath) {
      // 直接用 iframe 加载
      return;
    }
    if (m.artifactType === 'text' && m.artifactPath) {
      try {
        const res = await fetch(m.artifactPath);
        setArtifactContent(await res.text());
      } catch {
        setArtifactContent('⚠️ 加载失败');
      }
    }
  };

  // ── 运行验证（触发 Agent Loop 重新验证） ──
  const runVerify = async (m: Milestone) => {
    // TODO: 后面调 Agent Loop API 来重新验证
    await showAlert(`🔄 重跑验证：${m.title}\n（Agent Loop 引擎还没打通前端调用，先展示已有的成果）`);
  };

  return (<>
    <div className="capability-verify" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* ═══ 顶部说明 ═══ */}
      <div style={{ padding: '16px 24px', flexShrink: 0 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 6px', color: '#e6edf3', display: 'flex', alignItems: 'center', gap: 10 }}>
          🧪 能力验证
        </h2>
        <p style={{ fontSize: 13, color: '#8b949e', margin: 0 }}>
          坐山客 Agent Loop 自主完成的里程碑。每个验证项目均由 LLM 自主编码、执行、调试，无人干预。
        </p>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* ═══ 左侧：里程碑列表 ═══ */}
        <div style={{ width: 320, flexShrink: 0, overflowY: 'auto', borderRight: '1px solid #21262d', padding: '0 12px 12px' }}>
          {milestones.map(m => (
            <div key={m.id}
              className={`milestone-card${selectedId === m.id ? ' active' : ''}`}
              onClick={() => loadArtifact(m)}
              style={{
                padding: 14, marginTop: 8, borderRadius: 10, cursor: 'pointer',
                background: selectedId === m.id ? '#1c2128' : '#161b22',
                border: selectedId === m.id ? '1px solid #30363d' : '1px solid transparent',
                transition: 'all .15s',
              }}
              onMouseEnter={e => { if (selectedId !== m.id) { e.currentTarget.style.borderColor = '#21262d'; e.currentTarget.style.background = '#1c2128'; }}}
              onMouseLeave={e => { if (selectedId !== m.id) { e.currentTarget.style.borderColor = 'transparent'; e.currentTarget.style.background = '#161b22'; }}}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{ fontSize: 28, lineHeight: 1 }}>{m.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#e6edf3', marginBottom: 4 }}>{m.title}</div>
                  <div style={{ fontSize: 12, color: '#8b949e', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {m.description}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 11, color: '#6e7681' }}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                  padding: '2px 6px', borderRadius: 4,
                  background: m.status === 'verified' ? '#23863633' : m.status === 'pending' ? '#d2992233' : '#f8514933',
                  color: m.status === 'verified' ? '#3fb950' : m.status === 'pending' ? '#d29922' : '#f85149',
                }}>
                  {m.status === 'verified' ? '✅ 已验证' : m.status === 'pending' ? '⏳ 待验证' : '❌ 失败'}
                </span>
                <span>{m.steps} 步</span>
                <span style={{ marginLeft: 'auto' }}>{m.date}</span>
              </div>
            </div>
          ))}

          {/* 空状态 */}
          {milestones.length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: '#6e7681' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🧪</div>
              <div style={{ fontSize: 14, marginBottom: 6 }}>暂无验证记录</div>
              <div style={{ fontSize: 12, color: '#8b949e' }}>Agent Loop 完成首个任务后将自动出现在这里</div>
            </div>
          )}
        </div>

        {/* ═══ 右侧：详情/产物展示 ═══ */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
          {!selected && (
            <div style={{ textAlign: 'center', padding: 60, color: '#6e7681' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🧪</div>
              <div style={{ fontSize: 15, marginBottom: 8 }}>选择一个验证项目查看详情</div>
              <div style={{ fontSize: 13, color: '#8b949e' }}>左侧列表是 Agent Loop 自主完成的里程碑</div>
            </div>
          )}

          {selected && (
            <div>
              {/* 头部 */}
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
                <span style={{ fontSize: 40, lineHeight: 1 }}>{selected.icon}</span>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 6px', color: '#e6edf3' }}>{selected.title}</h3>
                  <p style={{ fontSize: 14, color: '#8b949e', lineHeight: 1.6, margin: 0 }}>{selected.description}</p>
                </div>
              </div>

              {/* 元数据 */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                <MetaBadge label="状态" value={selected.status === 'verified' ? '✅ 已验证' : selected.status === 'pending' ? '⏳ 待验证' : '❌ 失败'} color={selected.status === 'verified' ? '#3fb950' : selected.status === 'pending' ? '#d29922' : '#f85149'} />
                <MetaBadge label="执行步数" value={`${selected.steps} 步`} color="#58a6ff" />
                <MetaBadge label="LLM 模型" value={selected.llmModel} color="#58a6ff" />
                <MetaBadge label="完成日期" value={selected.date} color="#6e7681" />
              </div>

              {/* 操作按钮 */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                <button className="btn" onClick={() => runVerify(selected)}
                  style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #30363d', background: '#21262d', color: '#e6edf3', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                  🔄 重新验证
                </button>
                {selected.artifactType === 'html' && selected.artifactPath && (
                  <button className="btn" onClick={() => setFullscreenId(selected.id)}
                    style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #00d4ff44', background: '#00d4ff11', color: '#00d4ff', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                    ⛶ 全屏游玩
                  </button>
                )}
              </div>

              {/* 产物展示 */}
              {selected.status === 'verified' && (
                <div style={{ border: '1px solid #21262d', borderRadius: 10, overflow: 'hidden', background: '#0d1117' }}>
                  <div style={{ padding: '10px 14px', background: '#161b22', borderBottom: '1px solid #21262d', fontSize: 13, fontWeight: 500, color: '#8b949e', display: 'flex', alignItems: 'center', gap: 8 }}>
                    📦 验证产物
                    {selected.artifactType === 'html' && <span style={{ fontSize: 11, color: '#6e7681', marginLeft: 'auto' }}>交互式 · 可直接操作</span>}
                  </div>

                  <div style={{ padding: selected.artifactType === 'html' ? 0 : 16, minHeight: 200 }}>
                    {/* HTML 产物用 iframe */}
                    {selected.artifactType === 'html' && selected.artifactPath && (
                      <iframe
                        key={selectedId}
                        ref={iframeRef}
                        src={selected.artifactPath}
                        style={{ width: '100%', height: 500, border: 'none', background: '#fff' }}
                        title={selected.title}
                        sandbox="allow-scripts"
                      />
                    )}

                    {/* 文本产物 */}
                    {selected.artifactType === 'text' && artifactContent && (
                      <pre style={{ fontSize: 13, lineHeight: 1.6, color: '#8b949e', whiteSpace: 'pre-wrap', fontFamily: "'SF Mono','Fira Code',monospace", margin: 0 }}>
                        {artifactContent}
                      </pre>
                    )}

                    {/* 还没产物的占位 */}
                    {!selected.artifactPath && (
                      <div style={{ textAlign: 'center', padding: 40, color: '#6e7681' }}>
                        <div style={{ fontSize: 32, marginBottom: 10 }}>🔜</div>
                        <div style={{ fontSize: 14 }}>还未生成可在线预览的产物</div>
                        <div style={{ fontSize: 12, marginTop: 4 }}>点击「重新验证」让 Agent Loop 生成网页版</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 待验证状态 */}
              {selected.status === 'pending' && (
                <div style={{ border: '1px solid #d2992233', borderRadius: 10, padding: 24, background: '#161b22', textAlign: 'center' }}>
                  <div style={{ fontSize: 32, marginBottom: 10 }}>⏳</div>
                  <div style={{ fontSize: 14, color: '#8b949e' }}>此验证项目尚未运行，点击「重新验证」触发 Agent Loop</div>
                </div>
              )}

              {/* 失败状态 */}
              {selected.status === 'failed' && (
                <div style={{ border: '1px solid #f8514933', borderRadius: 10, padding: 24, background: '#161b22', textAlign: 'center' }}>
                  <div style={{ fontSize: 32, marginBottom: 10 }}>❌</div>
                  <div style={{ fontSize: 14, color: '#f85149', marginBottom: 4 }}>验证失败</div>
                  <div style={{ fontSize: 13, color: '#8b949e' }}>点击「重新验证」重试</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
    {/* 全屏弹层 */}
    {fullscreenMilestone && fullscreenMilestone.artifactPath && (
      <FullscreenOverlay key={fullscreenId} milestone={fullscreenMilestone} onClose={() => setFullscreenId(null)} />
    )}
  </>);

  // ═══ 全屏弹层 ═══
}

function FullscreenOverlay({ milestone, onClose }: { milestone: Milestone; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#0d1117', overflow: 'hidden',
      display: 'flex', justifyContent: 'center', alignItems: 'center',
    }}>
      <button onClick={onClose}
        style={{
          position: 'absolute', top: 16, right: 16, zIndex: 10000,
          padding: '10px 20px', borderRadius: 8,
          border: '1px solid #444', background: 'rgba(0,0,0,0.7)', color: '#fff',
          cursor: 'pointer', fontSize: 15, display: 'flex', alignItems: 'center', gap: 6,
        }}>
        ✕ 关闭 (Esc)
      </button>
      <iframe
        src={milestone.artifactPath}
        style={{
          width: '100vw', height: '100vh',
          border: 'none', display: 'block', overflow: 'hidden',
        }}
        title={milestone.title}
        sandbox="allow-scripts"
        scrolling="no"
      />
    </div>
  );
}

// ═══ 小部件：元数据标签 ═══
function MetaBadge({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '6px 12px', borderRadius: 6,
      border: '1px solid #21262d', background: '#161b22',
      fontSize: 12,
    }}>
      <span style={{ color: '#6e7681' }}>{label}</span>
      <span style={{ color }}>{value}</span>
    </div>
  );
}

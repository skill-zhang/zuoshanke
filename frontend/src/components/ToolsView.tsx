/** 🛠️ 工具管理视图 — 全页卡片网格 + 详情弹窗 + 测试面板 */
import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import { showAlert } from '../stores/dialogStore';
import {
  listTools, getTool, createTool, updateTool, deleteTool,
  updatePreexecute, putToolSkill, deleteToolSkill,
  type ToolSummary, type ToolDetail, type ToolParam,
} from '../api/client';

// ── 分类配置 ──
const CATEGORIES = [
  { key: 'all', icon: '🔍', label: '全部' },
  { key: 'search', icon: '🌐', label: '搜索' },
  { key: 'data', icon: '📊', label: '数据' },
  { key: 'system', icon: '⚙️', label: '系统' },
  { key: 'unverified', icon: '⚠️', label: '未验证' },
];

// ── Emoji 图标映射 ──
const ICON_MAP: Record<string, string> = {
  get_weather: '🌤', recommend_attractions: '🏛', get_equipment_checklist: '🎒',
  web_search: '🔍', todo_list: '📋', todo_add: '➕', todo_update: '📝',
  todo_delete: '🗑', todo_stats: '📊', session_search: '🕰', session_list: '💬',
  run_code: '⚙️', rustdesk_generate_setup: '🖥️', cloudflare_tunnel_setup: '☁️', frp_generate_setup: '🚀', geo_geocode: '📍', geo_reverse_geocode: '🗺',
  geo_search_poi: '🏪', geo_route: '🚗', extract_text: '📄', prophet_forecast: '📈',
  extract_text_from_pdf: '📎', analyze_image: '🖼', text_to_speech: '🎤', translate: '🌐', news_summary: '📰', generate_qrcode: '📱', daily_quote: '💬', recipe: '🍳', calculator: '🧮', baike: '📚', image_gen: '🎨', send_email: '📧',
};
function getIcon(name: string) { return ICON_MAP[name] || '🛠'; }

export function ToolsView() {
  const { setView } = useStore();

  // ── 状态 ──
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedTool, setSelectedTool] = useState<ToolDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [unregOpen, setUnregOpen] = useState(false);
  const [unregName, setUnregName] = useState('');

  // ── 加载工具列表 ──
  const load = useCallback(async (cat?: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await listTools(cat === 'all' ? undefined : cat);
      setTools(res.data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── 分类过滤 + 搜索（前端过滤） ──
  const filtered = tools.filter(t => {
    if (category === 'unverified' && t.verified) return false;
    if (category !== 'all' && category !== 'unverified' && t.category !== category) return false;
    if (search) {
      const q = search.toLowerCase();
      return t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);
    }
    return true;
  });

  // ── 详情 ──
  const openDetail = async (name: string) => {
    try {
      const res = await getTool(name);
      setSelectedTool(res.data);
      setDetailOpen(true);
    } catch (e: any) {
      setError(e.message || '加载详情失败');
    }
  };
  const closeDetail = () => { setDetailOpen(false); setSelectedTool(null); };

  // ── 注销 ──
  const showUnreg = (name: string) => { setUnregName(name); setUnregOpen(true); };
  const doUnreg = async () => {
    try {
      await deleteTool(unregName);
      setUnregOpen(false);
      closeDetail();
      await load();
    } catch (e: any) {
      setError(e.message || '注销失败');
      setUnregOpen(false);
    }
  };

  // ── 测试（模拟） ──
  const runTest = (name: string, params: Record<string, any>) => {
    // 模拟延迟后返回结果
    const mockResults: Record<string, (p: Record<string, any>) => string> = {
      get_weather: (p) => {
        const days = Math.min(Math.max(Number(p.forecast_days) || 3, 1), 7);
        const labels = ['明天', '后天', '大后天', '第四天', '第五天', '第六天', '第七天'];
        const temps = ['22°C', '20°C', '16°C', '18°C', '24°C', '21°C', '19°C'];
        const icons = ['☀️', '⛅', '🌧', '☀️', '⛅', '🌧', '☀️'];
        const rows = Array.from({ length: days }, (_, i) =>
          `| ${labels[i]} | ${temps[i]} | ${icons[i]} 晴${i === 0 ? '' : i === 2 ? '雨' : i % 2 ? '转阴' : ''} |`
        ).join('\n');
        return `## 🌤 ${p.city || '北京'} 天气\n\n**当前**：18°C，小雨，湿度 65%，东北风 3级\n\n**未来 ${days} 天预报**：\n| 日期 | 温度 | 天气 |\n|------|------|------|\n${rows}\n\n> 💡 建议：今天出门带伞${days >= 2 ? '，明天适合户外活动' : ''}`;
      },
      web_search: (p) => `## 🔍 搜索结果：${p.query || '今天新闻'}\n\n**共找到 3 条结果**（来源：SearXNG + DuckDuckGo）\n\n---\n\n### 1. 全球科技巨头宣布新一代AI芯片\n> 某科技公司今日发布新一代AI训练芯片，性能提升3倍...\n[查看原文](https://example.com/news/1)\n\n### 2. 今日财经：股市全线飘红\n> 受利好消息影响，三大指数集体上涨...\n[查看原文](https://example.com/news/2)\n\n### 3. 天气预报：未来三天全国大部晴好\n> 中央气象台发布最新预报...\n[查看原文](https://example.com/news/3)`,
      todo_list: (p) => `## 📋 我的任务（2项待办）\n\n| 状态 | 内容 | 优先级 |\n|------|------|--------|\n| 🔄 进行中 | 完成工具管理界面 | 高 |\n| ⏳ 待办 | 提交代码评审 | 中 |\n| ✅ 已完成 | 修复天气工具bug | 高 |\n| ✅ 已完成 | 更新registry.json | 低 |\n\n**进度**：2/4 ✅`,
      geo_route: (p) => `## 🚗 路线规划\n\n**${p.origin || '北京站'} → ${p.destination || '天安门'}**\n**方式**：🚗 驾车\n\n| 指标 | 数据 |\n|------|------|\n| 距离 | 5.2 km |\n| 预计时间 | 15 分钟 |\n| 路线 | 沿长安街直行 |\n\n> 🅿️ 目的地附近有停车场`,
    };
    return mockResults[name]?.(params) ?? `## ✅ 工具执行成功\n\n**工具**：\`${name}\`\n\n> 返回数据已就绪，可在对话中使用`;
  };

  // ── 渲染 ──
  return (
    <div className="tools-view" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* ═══ 分类 Tabs ═══ */}
      <div style={{ display: 'flex', gap: 6, padding: '16px 24px 0', overflowX: 'auto', flexShrink: 0 }}>
        {CATEGORIES.map(c => (
          <div key={c.key}
            className={`category-tab${category === c.key ? ' active' : ''}`}
            onClick={() => { setCategory(c.key); load(c.key === 'all' ? undefined : c.key); }}
            style={{
              padding: '6px 16px', borderRadius: 20, background: category === c.key ? '#1f6feb33' : 'transparent',
              color: category === c.key ? '#58a6ff' : '#8b949e', cursor: 'pointer', whiteSpace: 'nowrap',
              fontSize: 13, border: category === c.key ? '1px solid #1f6feb66' : '1px solid transparent',
              transition: 'all .15s',
            }}
          >{c.icon} {c.label}</div>
        ))}
      </div>

      {/* ═══ 工具栏 ═══ */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 24px', flexShrink: 0, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, padding: '6px 12px', width: 280, gap: 8 }}>
          <span>🔍</span>
          <input type="text" placeholder="搜索工具..." value={search} onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', color: '#e6edf3', fontSize: 13, outline: 'none', flex: 1, fontFamily: 'inherit' }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setRegisterOpen(true)} style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>➕ 注册新工具</button>
        </div>
      </div>

      {/* ═══ 工具卡片网格 ═══ */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, alignContent: 'start' }}>
        {loading && <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>🔄 加载中...</div>}
        {error && <div style={{ gridColumn: '1/-1', padding: 16, color: '#f85149', textAlign: 'center' }}>❌ {error}</div>}
        {!loading && !error && filtered.length === 0 && (
          <div className="empty-state" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 60, color: '#6e7681' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
            <div style={{ fontSize: 15, marginBottom: 8 }}>没有匹配的工具</div>
            <div style={{ fontSize: 13, color: '#8b949e' }}>试试其他搜索词或分类</div>
          </div>
        )}
        {filtered.map(t => (
          <div key={t.name} className="tool-card"
            onClick={() => openDetail(t.name)}
            style={{
              background: '#161b22', border: '1px solid #30363d', borderRadius: 10, padding: 20, cursor: 'pointer',
              transition: 'all .15s', display: 'flex', flexDirection: 'column',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = '#6e7681'; e.currentTarget.style.background = '#1c2128'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = '#30363d'; e.currentTarget.style.background = '#161b22'; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
          >
            <div style={{ fontSize: 32, lineHeight: 1, marginBottom: 10 }}>{getIcon(t.name)}</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 3, display: 'flex', alignItems: 'center', gap: 8 }}>
              <code style={{ fontFamily: "'SF Mono','Fira Code',monospace" }}>{t.name}</code>
              <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: t.verified ? '#23863633' : '#d2992233', color: t.verified ? '#3fb950' : '#d29922' }}>{t.verified ? '✅' : '⚠️'}</span>
            </div>
            <div style={{ fontSize: 12, color: '#8b949e', lineHeight: 1.5, flex: 1, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{t.description}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 10, paddingTop: 8, borderTop: '1px solid #21262d', fontSize: 11, color: '#6e7681' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#21262d', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', display: 'inline-block', background: t.preexecute_enabled ? '#3fb950' : '#6e7681' }}></span>
                {t.preexecute_enabled ? `🔥 ${t.preexecute_triggers_count}触发词` : '⚪ 手动'}
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#21262d', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                {t.category === 'search' ? '🌐' : t.category === 'data' ? '📊' : '⚙️'} {t.category}
              </span>
              {t.has_skill && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, background: '#21262d', padding: '2px 6px', borderRadius: 4, fontSize: 11, color: '#58a6ff' }}>📄 有手册</span>}
            </div>
          </div>
        ))}
      </div>

      {/* ═══ 详情 Modal ═══ */}
      {detailOpen && selectedTool && <DetailModal tool={selectedTool} onClose={closeDetail} onUnreg={showUnreg} onTest={runTest} />}

      {/* ═══ 注册 Modal ═══ */}
      {registerOpen && <RegisterModal onClose={() => setRegisterOpen(false)} onCreated={() => { setRegisterOpen(false); load(); }} />}

      {/* ═══ 注销确认 Modal ═══ */}
      {unregOpen && (
        <div className="modal-overlay show" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={e => { if (e.target === e.currentTarget) setUnregOpen(false); }}>
          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12, width: 420, padding: 24 }}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              ⚠️ 确认注销工具
              <button className="modal-close" onClick={() => setUnregOpen(false)} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', padding: '4px 0 16px' }}>
              <span style={{ fontSize: 40, lineHeight: 1 }}>🗑️</span>
              <div>
                <div style={{ fontSize: 15, fontWeight: 500, color: '#e6edf3', marginBottom: 6 }}>「{unregName}」</div>
                <div style={{ fontSize: 13, color: '#8b949e', lineHeight: 1.6 }}>
                  注销后，该工具将从 registry 中移除，<br />
                  不再出现在工具列表，也无法在对话中调用。
                </div>
                <div style={{ marginTop: 10, background: '#f8514915', border: '1px solid #f8514933', borderRadius: 6, padding: 10, fontSize: 13, color: '#f85149' }}>
                  ⚠️ 此操作不可撤销。如需重新使用，必须重新注册。
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
              <button className="btn" onClick={() => setUnregOpen(false)} style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13 }}>取消</button>
              <button className="btn" onClick={doUnreg} style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #f85149', background: '#f85149', color: '#fff', cursor: 'pointer', fontSize: 13 }}>确认注销</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══ 详情 Modal 子组件 ═══

function DetailModal({ tool, onClose, onUnreg, onTest }: {
  tool: ToolDetail; onClose: () => void; onUnreg: (name: string) => void;
  onTest: (name: string, params: Record<string, any>) => string;
}) {
  const [testParams, setTestParams] = useState<Record<string, string>>({});
  const [testResult, setTestResult] = useState<{ md: string; elapsed: string } | null>(null);
  const [testRunning, setTestRunning] = useState(false);

  const runTest = () => {
    setTestRunning(true);
    setTestResult(null);
    const params: Record<string, any> = {};
    tool.parameters.forEach(p => {
      const val = testParams[p.name] || '';
      if (val) {
        params[p.name] = p.type === 'integer' || p.type === 'number' ? Number(val) : val;
      }
    });
    const start = Date.now();
    setTimeout(() => {
      const elapsed = ((Date.now() - start) / 1000).toFixed(2);
      const md = onTest(tool.name, params);
      setTestResult({ md, elapsed });
      setTestRunning(false);
    }, 600);
  };

  return (
    <div className="modal-overlay show" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12, width: 620, maxHeight: '85vh', overflowY: 'auto', padding: 24 }}>
        {/* 标题 */}
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>{getIcon(tool.name)} {tool.name}</span>
          <button className="modal-close" onClick={onClose} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>

        {/* 基本信息 */}
        <Section title="📝 基本信息">
          <Row label="描述" value={tool.description} />
          <Row label="文件" value={<code style={{ background: '#21262d', padding: '1px 5px', borderRadius: 3, fontSize: 12 }}>{tool.file}</code>} />
          <Row label="函数" value={<code style={{ background: '#21262d', padding: '1px 5px', borderRadius: 3, fontSize: 12 }}>{tool.function}()</code>} />
          <Row label="分类" value={<span>{tool.category === 'search' ? '🌐 搜索' : tool.category === 'data' ? '📊 数据' : '⚙️ 系统'} &nbsp; <span style={{ color: tool.verified ? '#3fb950' : '#d29922' }}>{tool.verified ? '✅ 已验证' : '⚠️ 未验证'}</span></span>} />
        </Section>

        {/* 参数表 */}
        {tool.parameters.length > 0 && (
          <Section title="📋 参数">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr><th style={{ textAlign: 'left', color: '#8b949e', fontWeight: 500, fontSize: 12, padding: '4px 8px', borderBottom: '1px solid #21262d' }}>参数名</th>
                  <th style={{ textAlign: 'left', color: '#8b949e', fontWeight: 500, fontSize: 12, padding: '4px 8px', borderBottom: '1px solid #21262d' }}>类型</th>
                  <th style={{ textAlign: 'left', color: '#8b949e', fontWeight: 500, fontSize: 12, padding: '4px 8px', borderBottom: '1px solid #21262d' }}>必填</th>
                  <th style={{ textAlign: 'left', color: '#8b949e', fontWeight: 500, fontSize: 12, padding: '4px 8px', borderBottom: '1px solid #21262d' }}>说明</th>
                </tr>
              </thead>
              <tbody>
                {tool.parameters.map(p => (
                  <tr key={p.name}>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid #21262d' }}><code style={{ background: '#21262d', padding: '1px 5px', borderRadius: 3 }}>{p.name}</code></td>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid #21262d', color: '#58a6ff', fontSize: 12 }}>{p.type}</td>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid #21262d', fontSize: 12, color: p.required ? '#3fb950' : '#6e7681' }}>{p.required ? '✅ 必填' : '❌ 可选'}</td>
                    <td style={{ padding: '6px 8px', borderBottom: '1px solid #21262d', color: '#8b949e' }}>{p.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        )}

        {/* 返回值 */}
        {tool.returns && <Section title="📤 返回值"><div style={{ fontSize: 13, color: '#8b949e' }}>{tool.returns}</div></Section>}

        {/* 预执行 */}
        <Section title="⚡ 预执行配置">
          <Row label="状态" value={tool.preexecute.enabled ? <span style={{ color: '#3fb950' }}>🟢 已启用</span> : <span style={{ color: '#6e7681' }}>⚪ 已禁用</span>} />
          {tool.preexecute.enabled && (
            <>
              <Row label="触发词" value={
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {tool.preexecute.triggers.map((tr, i) => (
                    <span key={i} style={{ background: '#1f6feb22', color: '#58a6ff', padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>{tr}</span>
                  ))}
                </div>
              } />
              <Row label="需要城市" value={tool.preexecute.requires_city ? '✅ 是' : '❌ 否'} />
            </>
          )}
        </Section>

        {/* 使用手册 */}
        <Section title="📄 使用手册（SKILL.md）">
          {tool.has_skill ? (
            <>
              <div style={{ marginBottom: 8, fontSize: 13, color: '#3fb950' }}>✅ 已创建 &nbsp; <code style={{ fontSize: 12, background: '#21262d', padding: '1px 5px', borderRadius: 3 }}>tools/{tool.name}/SKILL.md</code></div>
              <div style={{ background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: 12, fontSize: 13, lineHeight: 1.6, color: '#8b949e', maxHeight: 160, overflowY: 'auto', whiteSpace: 'pre-wrap', fontFamily: "'SF Mono','Fira Code',monospace" }}>{tool.skill_content}</div>
            </>
          ) : (
            <div style={{ color: '#6e7681', fontStyle: 'italic', fontSize: 13 }}>❌ 未创建使用手册</div>
          )}
        </Section>

        {/* 🧪 测试工具 */}
        <Section title="🧪 测试工具">
          <div style={{ background: '#0d1117', border: '1px solid #30363d', borderRadius: 8, padding: 14 }}>
            {tool.parameters.map(p => (
              <div key={p.name} style={{ marginBottom: 8 }}>
                <label style={{ fontSize: 12, color: '#8b949e', display: 'flex', alignItems: 'center', gap: 4, marginBottom: 3 }}>
                  <code style={{ fontFamily: "'SF Mono','Fira Code',monospace" }}>{p.name}</code>
                  <span style={{ color: p.required ? '#3fb950' : '#6e7681', fontSize: 11 }}>{p.required ? '必填' : '可选'}</span>
                  <span style={{ color: '#6e7681', fontSize: 11 }}>{p.type}</span>
                </label>
                <input
                  value={testParams[p.name] ?? (p.name === 'city' ? '北京' : p.name === 'query' ? '今天新闻' : p.name === 'forecast_days' ? '3' : p.name === 'origin' ? '北京站' : p.name === 'destination' ? '天安门' : '')}
                  onChange={e => setTestParams(prev => ({ ...prev, [p.name]: e.target.value }))}
                  placeholder={p.description}
                  style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
                />
              </div>
            ))}
            {tool.parameters.length === 0 && <div style={{ color: '#6e7681', fontSize: 13, marginBottom: 8 }}>该工具无参数，直接运行即可</div>}

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button onClick={runTest} disabled={testRunning}
                style={{ padding: '6px 16px', borderRadius: 6, background: testRunning ? '#1f6feb' : '#238636', border: '1px solid #2ea043', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
                {testRunning ? '⏳ 运行中...' : '▶️ 运行'}
              </button>
            </div>

            {testResult && (
              <div style={{ marginTop: 10, border: '1px solid #21262d', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: '#21262d', fontSize: 13, fontWeight: 500 }}>
                  <span style={{ color: '#3fb950' }}>✅ 执行成功</span>
                  <span style={{ fontSize: 11, color: '#6e7681' }}>{testResult.elapsed}s</span>
                </div>
                <div style={{ padding: 14, fontSize: 14, lineHeight: 1.7, color: '#e6edf3', background: '#161b22', maxHeight: 280, overflowY: 'auto', whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                  {testResult.md}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* 操作按钮 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
          <button className="btn btn-sm" onClick={async () => { await showAlert('工具编辑功能待实现'); }} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 4, border: '1px solid #30363d', background: 'transparent', color: '#8b949e', cursor: 'pointer' }}>✏️ 编辑工具</button>
          <button className="btn btn-sm" onClick={async () => { await showAlert('预执行配置编辑待实现'); }} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 4, border: '1px solid #30363d', background: 'transparent', color: '#8b949e', cursor: 'pointer' }}>⚙️ 预执行</button>
          <button className="btn btn-sm" onClick={async () => { await showAlert('SKILL.md编辑待实现'); }} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 4, border: '1px solid #30363d', background: 'transparent', color: '#8b949e', cursor: 'pointer' }}>📄 编辑手册</button>
          <button className="btn btn-sm" onClick={() => onUnreg(tool.name)}
            style={{ padding: '4px 10px', fontSize: 12, borderRadius: 4, border: '1px solid #f85149', background: 'transparent', color: '#f85149', cursor: 'pointer' }}>🗑 注销</button>
        </div>
      </div>
    </div>
  );
}

// ═══ 注册 Modal 子组件 ═══

function RegisterModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [file, setFile] = useState('');
  const [func, setFunc] = useState('');
  const [category, setCategory] = useState('data');
  const [returns, setReturns] = useState('');
  const [params, setParams] = useState<{ name: string; type: string; required: boolean }[]>([]);
  const [preexecEnabled, setPreexecEnabled] = useState(false);
  const [triggers, setTriggers] = useState('');
  const [requiresCity, setRequiresCity] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const addParam = () => setParams([...params, { name: '', type: 'string', required: true }]);
  const removeParam = (i: number) => setParams(params.filter((_, idx) => idx !== i));
  const updateParam = (i: number, field: string, value: any) => {
    const next = [...params];
    (next[i] as any)[field] = value;
    setParams(next);
  };

  const handleSave = async () => {
    if (!name.trim() || !desc.trim() || !file.trim() || !func.trim()) {
      setError('请填写所有必填项');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await createTool({
        name: name.trim(),
        description: desc.trim(),
        file: file.trim(),
        function: func.trim(),
        category,
        returns: returns.trim(),
        parameters: params.filter(p => p.name.trim()).map(p => ({ name: p.name.trim(), type: p.type, required: p.required, description: '' })),
        preexecute: { enabled: preexecEnabled, triggers: triggers.split(/[,，]/).map(s => s.trim()).filter(Boolean), requires_city: requiresCity },
      });
      onCreated();
    } catch (e: any) {
      setError(e.message || '注册失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay show" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12, width: 600, maxHeight: '85vh', overflowY: 'auto', padding: 24 }}>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          📦 注册新工具
          <button className="modal-close" onClick={onClose} style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>

        {error && <div style={{ color: '#f85149', fontSize: 13, marginBottom: 12, padding: 8, background: '#f8514915', borderRadius: 6 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>工具名称 *</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="get_weather"
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>分类 *</label>
            <select value={category} onChange={e => setCategory(e.target.value)}
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }}>
              <option value="search">🌐 搜索</option>
              <option value="data">📊 数据</option>
              <option value="system">⚙️ 系统</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>描述 *</label>
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="工具的简短说明"
            style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>文件路径 *</label>
            <input value={file} onChange={e => setFile(e.target.value)} placeholder="tools/weather.py"
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>函数名 *</label>
            <input value={func} onChange={e => setFunc(e.target.value)} placeholder="get_weather"
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>返回值说明</label>
          <input value={returns} onChange={e => setReturns(e.target.value)} placeholder="天气数据（温度、湿度、风力、描述、预报）"
            style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
        </div>

        {/* 参数 */}
        <div style={{ fontSize: 12, fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8, paddingBottom: 4, borderBottom: '1px solid #21262d' }}>📋 参数</div>
        {params.map((p, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <div style={{ flex: 2 }}><input value={p.name} onChange={e => updateParam(i, 'name', e.target.value)} placeholder="参数名"
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} /></div>
            <div style={{ flex: 1 }}><select value={p.type} onChange={e => updateParam(i, 'type', e.target.value)}
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }}>
              <option>string</option><option>integer</option><option>number</option><option>boolean</option>
            </select></div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#8b949e', whiteSpace: 'nowrap' }}>
              <input type="checkbox" checked={p.required} onChange={e => updateParam(i, 'required', e.target.checked)} /> 必填
            </label>
            <button onClick={() => removeParam(i)} style={{ flexShrink: 0, padding: '4px 8px', fontSize: 12, borderRadius: 4, border: '1px solid #30363d', background: 'transparent', color: '#8b949e', cursor: 'pointer' }}>✕</button>
          </div>
        ))}
        <button onClick={addParam} style={{ marginBottom: 14, padding: '4px 10px', fontSize: 12, borderRadius: 4, border: '1px solid #30363d', background: 'transparent', color: '#8b949e', cursor: 'pointer' }}>+ 添加参数</button>

        {/* 预执行 */}
        <div style={{ fontSize: 12, fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8, paddingBottom: 4, borderBottom: '1px solid #21262d' }}>⚡ 预执行配置（可选）</div>
        <div style={{ marginBottom: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#8b949e' }}>
            <input type="checkbox" checked={preexecEnabled} onChange={e => setPreexecEnabled(e.target.checked)} /> 🟢 启用预执行
          </label>
        </div>
        {preexecEnabled && (
          <div style={{ marginBottom: 8 }}>
            <label style={{ display: 'block', fontSize: 13, color: '#8b949e', marginBottom: 6, fontWeight: 500 }}>触发词（逗号分隔）</label>
            <input value={triggers} onChange={e => setTriggers(e.target.value)} placeholder="天气, 温度, 下雨"
              style={{ width: '100%', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', color: '#e6edf3', fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#8b949e', marginTop: 8 }}>
              <input type="checkbox" checked={requiresCity} onChange={e => setRequiresCity(e.target.checked)} /> 📍 需要城市名
            </label>
          </div>
        )}

        {/* 操作按钮 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, paddingTop: 14, borderTop: '1px solid #21262d' }}>
          <button onClick={onClose} style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #30363d', background: 'transparent', color: '#e6edf3', cursor: 'pointer', fontSize: 13 }}>取消</button>
          <button onClick={handleSave} disabled={saving}
            style={{ padding: '6px 16px', borderRadius: 6, background: '#238636', border: '1px solid #2ea043', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
            {saving ? '注册中...' : '💾 注册'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══ 辅助组件 ═══

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8, paddingBottom: 4, borderBottom: '1px solid #21262d' }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '4px 0', fontSize: 13 }}>
      <span style={{ color: '#8b949e', minWidth: 80, flexShrink: 0, fontSize: 12 }}>{label}</span>
      <span style={{ color: '#e6edf3', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

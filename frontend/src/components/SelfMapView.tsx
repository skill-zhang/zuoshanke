/** 🗺️ 坐山客自省地图 — 三栏布局（左树 + 中图 + 右侧详情） */
import { useState, useCallback, useRef, useEffect } from 'react';

// ═══ 数据结构 ═══

interface TreeNode {
  id: string;
  icon: string;
  label: string;
  sublabel?: string;
  children?: TreeNode[];
  hasDiagram?: boolean;
  detail?: NodeDetail;
}

interface NodeDetail {
  description: string;
  rows?: [string, string][];
  codePath?: string;
}

// ═══ 树数据 ═══

const TREE_DATA: TreeNode[] = [
  {
    id: 'frontend', icon: '🖥️', label: '前端层',
    hasDiagram: true,
    detail: {
      description: 'React SPA 单页应用。基于 Vite + TypeScript + Zustand 状态管理。采用组件化架构，动态路由通过 Zustand store 控制，无传统路由库。',
      rows: [
        ['框架', 'React 18 + Vite'],
        ['状态管理', 'Zustand (appStore)'],
        ['CSS', 'index.css + 行内样式'],
        ['构建工具', 'Vite + pnpm'],
        ['端口', '5173（开发）/ 4173（预览）'],
        ['入口', 'frontend/src/App.tsx'],
      ],
      codePath: 'frontend/src/'
    },
    children: [
      {
        id: 'frontend-chat', icon: '💬', label: 'ChatView',
        detail: {
          description: '核心聊天视图，支持场景和频道的流式/非流式消息。集成 Thinking Map 面板、DelegationMonitor、ToolCards 展示。',
          rows: [
            ['路径', 'frontend/src/components/ChatView.tsx'],
            ['关键状态', 'messages, currentToolCards, isGenerating'],
            ['消息流', 'SSE stream → tool_cards → text delta → done'],
          ],
          codePath: 'frontend/src/components/ChatView.tsx',
        },
      },
      {
        id: 'frontend-sidebar', icon: '📋', label: 'Sidebar',
        detail: {
          description: '侧边栏导航。频道列表 + 场景广场/工坊（分类折叠）+ 系统工具（可拖拽排序）。区域折叠状态持久化。',
          rows: [
            ['路径', 'frontend/src/components/Sidebar.tsx'],
            ['系统工具', '工具管理/能力验证/记忆/技能/产出/子Agent成果'],
          ],
          codePath: 'frontend/src/components/Sidebar.tsx',
        },
      },
      {
        id: 'frontend-garden', icon: '🌸', label: '秘密花园',
        hasDiagram: true,
        detail: {
          description: '坐山客内心世界入口。沉浸式 UI，6 个区域：心绪→记忆花园→成长年轮→协作金石→内在风景→起居室。本体对话入口。',
          rows: [
            ['路径', 'frontend/src/components/SecretGarden.tsx'],
            ['区域数', '6 个 section'],
            ['心情状态', '7 态（idle/watching/thinking/amused/annoyed/speaking/resting）'],
          ],
          codePath: 'frontend/src/components/SecretGarden.tsx',
        },
      },
      {
        id: 'frontend-store', icon: '🏪', label: 'appStore (Zustand)',
        detail: {
          description: '全局状态管理。涵盖场景/频道/消息/Thinking Map/Action Map/工具/Session 管理等全部前端状态。',
          rows: [
            ['库', 'Zustand (create)'],
            ['ViewPage 类型', '12 种视图'],
            ['状态字段', '~60 个字段'],
          ],
          codePath: 'frontend/src/stores/appStore.ts',
        },
      },
    ],
  },
  {
    id: 'backend', icon: '⚙️', label: '后端层',
    hasDiagram: true,
    detail: {
      description: 'FastAPI 后端。RESTful API + SSE 流式响应。18 个路由模块，Agent Core 引擎，双重记忆池。',
      rows: [
        ['框架', 'FastAPI + Uvicorn'],
        ['数据库', 'SQLite + SQLAlchemy + WAL 模式'],
        ['ORM', 'SQLAlchemy DeclarativeBase'],
        ['端口', '8000'],
        ['入口', 'backend/main.py'],
        ['路由模块', '18 个'],
      ],
      codePath: 'backend/'
    },
    children: [
      {
        id: 'backend-router', icon: '🌐', label: '路由层',
        detail: {
          description: '18 个 APIRouter 模块，覆盖场景/频道/消息/Session/记忆/工具/技能/仪表盘/本体/产出/起居室等全部 API。',
          rows: [
            ['路由注册', 'backend/router/__init__.py'],
            ['场景流式', 'scene_stream.py (SSE Agent Loop 主入口)'],
            ['本体', 'zhu_agent.py (坐山客本体)'],
          ],
          codePath: 'backend/router/',
        },
      },
      {
        id: 'backend-core', icon: '🧠', label: 'Agent Core',
        hasDiagram: true,
        detail: {
          description: 'AI 代理核心引擎。包含 Agent Loop 执行、上下文构建、记忆管理、收敛引擎、Delegation 子 Agent。',
          rows: [
            ['路径', 'backend/agent_core/'],
            ['引擎数', '12 个模块'],
            ['Agent Loop', 'agent_loop.py（工具路由 + LLM 调用）'],
            ['Context', 'context_composer.py（7层组合）'],
            ['Delegate', 'delegate_engine.py（子 Agent 并行执行）'],
          ],
          codePath: 'backend/agent_core/',
        },
        children: [
          {
            id: 'core-agentloop', icon: '🔄', label: 'Agent Loop',
            detail: {
              description: '核心执行循环：工具定义 → LLM 调用 → 工具执行 → 结果注入 → 循环/终止。支持 clarify 拦截、死循环检测、收敛触发。',
              rows: [
                ['路径', 'backend/agent_core/agent_loop.py'],
                ['最大步数', '25'],
                ['死循环检测', '连续 6 次纯工具调用后提示'],
              ],
              codePath: 'backend/agent_core/agent_loop.py',
            },
          },
          {
            id: 'core-context', icon: '📦', label: 'Context 组合器',
            hasDiagram: true,
            detail: {
              description: '7 层上下文组合（Schema v1.0）。依次注入：Prompt Memory → Document Summary → Config → Skill → History → Work Output → Tool Layer。',
              rows: [
                ['路径', 'backend/agent_core/context_composer.py'],
                ['层数', '7 层'],
                ['组合策略', '顺序注入，每层可跳过'],
              ],
              codePath: 'backend/agent_core/context_composer.py',
            },
          },
          {
            id: 'core-memory', icon: '💾', label: '记忆系统',
            hasDiagram: true,
            detail: {
              description: '双重记忆池（Schema v2）。本体记忆永不休眠不衰减，分身记忆正常衰减。权重驱动 + 缓存层 + 写穿透。',
              rows: [
                ['路径', 'backend/agent_core/memory_manager.py + memory_cache.py'],
                ['池数', '2（zhu + scene/channel）'],
                ['去重', 'Jaccard 相似度 ≥ 0.50'],
                ['权重公式', '动态计算（不存静态值）'],
              ],
              codePath: 'backend/agent_core/memory_manager.py',
            },
          },
          {
            id: 'core-delegate', icon: '🧩', label: 'Delegate 引擎',
            detail: {
              description: '子 Agent 并行执行引擎。ThreadPoolExecutor 池化，最多 3 个并行，300s 超时。三层 Context：L1 任务 / L2 契约 / L3 项目。',
              rows: [
                ['路径', 'backend/agent_core/delegate_engine.py'],
                ['最大并行', '3'],
                ['超时', '300s/子任务'],
              ],
              codePath: 'backend/agent_core/delegate_engine.py',
            },
          },
          {
            id: 'core-converge', icon: '🎯', label: '收敛引擎',
            detail: {
              description: 'Thinking Map 收敛/发散引擎。双路径触发：LLM 自主调用 或 系统自动定量（叶子 ≥ 分支 × 阈值）。',
              rows: [
                ['路径', 'backend/agent_core/converge_engine.py'],
                ['阈值', '2.0（叶子/分支比）'],
                ['发散回合', '默认 2 轮 AI 回复后'],
              ],
              codePath: 'backend/agent_core/converge_engine.py',
            },
          },
        ],
      },
      {
        id: 'backend-db', icon: '🗄️', label: '数据层',
        detail: {
          description: 'SQLite 数据库，35+ 个表。含场景/频道/消息/Thinking Map/Session/记忆/工具/产出/配置等。WAL 模式提升并发。',
          rows: [
            ['数据库', 'SQLite (zuoshanke.db)'],
            ['表数', '35+'],
            ['ORM', 'SQLAlchemy ORM'],
            ['迁移', '零破坏（ALTER TABLE ADD COLUMN）'],
          ],
          codePath: 'backend/models.py',
        },
      },
    ],
  },
  {
    id: 'gateway', icon: '🚪', label: '网关层',
    detail: {
      description: '多平台网关，支持微信/Telegram/Discord 等。独立的 GatewaySession 管理，5 分钟 idle 超时回退频道。',
      rows: [
        ['端口', '8099'],
        ['会话', 'GatewaySession（独立表）'],
        ['超时', '5 分钟 idle → 回退频道'],
      ],
      codePath: 'backend/router/gateway.py',
    },
    children: [
      {
        id: 'gateway-wechat', icon: '💬', label: '微信通道',
        detail: {
          description: '微信消息通道。支持文本/图片消息收发，SSE 流式响应。DeepSeek 模型路由。',
          codePath: 'backend/router/gateway.py',
        },
      },
    ],
  },
  {
    id: 'llm', icon: '🤖', label: 'LLM 引擎',
    hasDiagram: true,
    detail: {
      description: '多模型推理引擎。主路由 DeepSeek Flash，本地 Qwen3-8B (llama-server:8083) 作为后备。Temperature 0.7 偏好。',
      rows: [
        ['主模型', 'DeepSeek Flash (deepseek-v4-flash)'],
        ['本地后备', 'Qwen3-8B Q4_K_M (llama-server:8083)'],
        ['温度', '默认 0.7'],
        ['路由', '两阶段：light route pre-execution → registry'],
        ['Tokenizer', 'BytePair / 模型自带'],
      ],
      codePath: 'backend/ai_engine.py',
    },
  },
  {
    id: 'tools', icon: '🔧', label: '工具系统',
    detail: {
      description: '四层工具注册与发现体系。L1 registry.json → L2 LLM Function Calling → L3 Prompt 文本 → L4 前端 UI。当前 36+ 工具。',
      rows: [
        ['工具数', '36+'],
        ['注册', 'tools/registry.json'],
        ['发现层级', '4 层'],
        ['拨测工具', 'browser_dial_test / dial_style / dial_assert'],
      ],
      codePath: 'tools/',
    },
  },
  {
    id: 'session', icon: '⏱️', label: 'Session 管理',
    detail: {
      description: 'Schema v1.1 WebSession 系统。每个场景/频道独立上下文 session，3h 超时兜底，后台每 5 分钟扫描。Token 累加与核算。',
      rows: [
        ['路径', 'backend/router/sessions.py'],
        ['超时', '3 小时（可配置）'],
        ['扫描', '后台 daemon 线程，每 5 分钟'],
        ['Token 跟踪', 'prompt/completion/total_tokens 累加'],
      ],
      codePath: 'backend/router/sessions.py',
    },
  },
];

// ═══ 流程图数据 ═══

interface DiagramNode {
  id: string; x: number; y: number; w: number; h: number;
  icon: string; label: string; sub?: string; style: string;
}

interface DiagramDef {
  title: string; nodes: DiagramNode[]; edges: [string, string][];
}

const DIAGRAMS: Record<string, DiagramDef> = {
  frontend: {
    title: '前端 → 后端通信流',
    nodes: [
      { id: 'app', x: 80, y: 10, w: 130, h: 42, icon: '📱', label: 'App.tsx', sub: '入口', style: 'layer' },
      { id: 'store', x: 80, y: 80, w: 130, h: 42, icon: '🏪', label: 'Zustand', sub: '全局状态', style: 'process' },
      { id: 'api', x: 80, y: 150, w: 130, h: 42, icon: '🌐', label: 'API Client', sub: 'fetch/base', style: 'process' },
      { id: 'server', x: 80, y: 220, w: 130, h: 42, icon: '⚙️', label: 'FastAPI', sub: 'REST + SSE', style: 'highlight' },
      { id: 'db', x: 80, y: 290, w: 130, h: 42, icon: '🗄️', label: 'SQLite', sub: 'WAL', style: 'db' },
    ],
    edges: [['app', 'store'], ['store', 'api'], ['api', 'server'], ['server', 'db']],
  },
  'backend-core': {
    title: 'Agent Core 模块依赖',
    nodes: [
      { id: 'loop', x: 20, y: 10, w: 120, h: 42, icon: '🔄', label: 'Agent Loop', sub: '执行引擎', style: 'highlight' },
      { id: 'ctx', x: 20, y: 80, w: 120, h: 42, icon: '📦', label: 'Context 组合', sub: '7 层', style: 'layer' },
      { id: 'mem', x: 170, y: 80, w: 120, h: 42, icon: '💾', label: '记忆管理器', sub: '双重池', style: 'db' },
      { id: 'delegate', x: 170, y: 10, w: 120, h: 42, icon: '🧩', label: 'Delegate', sub: '子 Agent', style: 'process' },
      { id: 'conv', x: 320, y: 10, w: 120, h: 42, icon: '🎯', label: '收敛引擎', sub: '阈值 2.0', style: 'process' },
    ],
    edges: [['loop', 'ctx'], ['loop', 'mem'], ['loop', 'delegate'], ['loop', 'conv']],
  },
  'frontend-garden': {
    title: '秘密花园区域布局',
    nodes: [
      { id: 'mood', x: 10, y: 10, w: 110, h: 40, icon: '🌸', label: '心绪', sub: '心情+生命力', style: 'highlight' },
      { id: 'inner', x: 140, y: 10, w: 110, h: 40, icon: '🗺️', label: '内在风景', sub: '自省地图', style: 'layer' },
      { id: 'memory', x: 270, y: 10, w: 110, h: 40, icon: '🌿', label: '记忆花园', sub: '回忆之花', style: 'process' },
      { id: 'growth', x: 10, y: 80, w: 110, h: 40, icon: '🌳', label: '成长年轮', sub: '统计', style: 'process' },
      { id: 'mile', x: 140, y: 80, w: 110, h: 40, icon: '✨', label: '协作金石', sub: '里程碑', style: 'process' },
      { id: 'chat', x: 270, y: 80, w: 110, h: 40, icon: '🛋️', label: '起居室', sub: '对话本体', style: 'highlight' },
    ],
    edges: [['mood', 'inner'], ['inner', 'memory'], ['mood', 'growth'], ['inner', 'mile'], ['memory', 'chat']],
  },
  'core-memory': {
    title: '双重记忆池 · 写穿透',
    nodes: [
      { id: 'm1', x: 20, y: 10, w: 120, h: 42, icon: '✍️', label: '写入', sub: 'add+reinforce', style: 'highlight' },
      { id: 'm2', x: 20, y: 80, w: 120, h: 42, icon: '🔗', label: 'Jaccard 去重', sub: '≥0.50', style: 'process' },
      { id: 'm3', x: 170, y: 10, w: 120, h: 42, icon: '⬆️', label: 'reinforce', sub: '已有+1', style: 'process' },
      { id: 'm4', x: 170, y: 80, w: 120, h: 42, icon: '🆕', label: '新建记忆', sub: 'weight=3', style: 'process' },
      { id: 'm5', x: 320, y: 40, w: 130, h: 50, icon: '🗄️', label: 'agent_memory 表', sub: '持久化', style: 'db' },
      { id: 'm6', x: 320, y: 120, w: 130, h: 42, icon: '⚡', label: 'memory_cache', sub: '内存加速', style: 'db' },
    ],
    edges: [['m1', 'm2'], ['m2', 'm3'], ['m2', 'm4'], ['m3', 'm5'], ['m4', 'm5'], ['m5', 'm6']],
  },
  'core-context': {
    title: '7 层 Context 组合 · 双列汇聚',
    nodes: [
      { id: 'c1', x: 20, y: 5,  w: 130, h: 40, icon: '1', label: 'Prompt Memory', sub: '2.4K', style: 'layer' },
      { id: 'c2', x: 20, y: 60, w: 130, h: 40, icon: '2', label: 'Memory 注入', sub: '1.8K', style: 'layer' },
      { id: 'c3', x: 20, y: 115, w: 130, h: 40, icon: '3', label: 'Document Summary', sub: '3.2K', style: 'layer' },
      { id: 'c4', x: 180, y: 5,  w: 130, h: 40, icon: '4', label: 'Config', sub: '0.5K', style: 'layer' },
      { id: 'c5', x: 180, y: 60, w: 130, h: 40, icon: '5', label: 'Skill', sub: '1.2K', style: 'layer' },
      { id: 'c6', x: 180, y: 115, w: 130, h: 40, icon: '6', label: 'History', sub: '4.6K', style: 'layer' },
      { id: 'c7', x: 180, y: 170, w: 130, h: 40, icon: '7', label: 'Work Output', sub: '1.5K', style: 'layer' },
      { id: 'cc', x: 60, y: 210, w: 200, h: 46, icon: '🔀', label: 'Context Composer', sub: '7 层合并注入', style: 'highlight' },
      { id: 'cl', x: 100, y: 280, w: 130, h: 42, icon: '🧠', label: 'LLM', sub: '模型推理', style: 'external' },
    ],
    edges: [['c1', 'c2'], ['c2', 'c3'], ['c4', 'c5'], ['c5', 'c6'], ['c6', 'c7'], ['c3', 'cc'], ['c7', 'cc'], ['cc', 'cl']],
  },
};

// ═══ React 组件 ═══

const STYLE_CLASSES: Record<string, string> = {
  highlight: '#22d3ee',
  layer: '#34d399',
  process: '#64748b',
  db: '#a78bfa',
};

function DetailDrawer({ node, onClose }: { node: TreeNode | null; onClose: () => void }) {
  if (!node?.detail) {
    return (
      <div className="d-empty" style={{ color: '#475569', fontSize: 12, textAlign: 'center', padding: '40px 16px', lineHeight: 1.8 }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
        <div>点击节点查看详情</div>
      </div>
    );
  }
  const d = node.detail;
  return (
    <>
      <div className="d-header" style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 10, borderBottom: '1px solid #1e293b', marginBottom: 12 }}>
        <span style={{ fontSize: 22, width: 32, textAlign: 'center' }}>{node.icon}</span>
        <div style={{ flex: 1 }}>
          <div className="d-title" style={{ fontSize: 14, fontWeight: 600 }}>{node.label}</div>
          <div className="d-sub" style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{(node.children?.length || 0) > 0 ? `${node.children!.length} 个子模块` : '叶子节点'}</div>
        </div>
        <button onClick={onClose} className="d-close" style={{ background: 'none', border: 'none', color: '#475569', fontSize: 14, cursor: 'pointer', padding: '2px 4px', borderRadius: 3 }}>✕</button>
      </div>
      <div className="d-section" style={{ marginBottom: 12 }}>
        <h3 style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>描述</h3>
        <div className="d-desc" style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>{d.description}</div>
      </div>
      {d.rows && d.rows.length > 0 && (
        <div className="d-section" style={{ marginBottom: 12 }}>
          <h3 style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>关键信息</h3>
          <table className="d-table" style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
            <tbody>
              {d.rows.map(([k, v], i) => (
                <tr key={i}>
                  <td style={{ padding: '4px 6px', borderBottom: '1px solid #1e293b', color: '#64748b', width: 80, whiteSpace: 'nowrap', fontSize: 10 }}>{k}</td>
                  <td style={{ padding: '4px 6px', borderBottom: '1px solid #1e293b', color: '#e2e8f0' }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d.codePath && (
        <div className="d-section" style={{ marginBottom: 12 }}>
          <h3 style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>代码路径</h3>
          <div className="d-code" style={{ fontSize: 11, color: '#22d3ee', background: 'rgba(34,211,238,0.05)', padding: '8px 12px', borderRadius: 5, border: '1px solid rgba(34,211,238,0.12)' }}>
            {d.codePath}
          </div>
        </div>
      )}
    </>
  );
}

function DiagramView({ diagram }: { diagram: DiagramDef | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!diagram || !containerRef.current) return;
    const container = containerRef.current;
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    if (cw === 0 || ch === 0) return;

    // 计算所有节点的包围盒
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of diagram.nodes) {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + n.w);
      maxY = Math.max(maxY, n.y + n.h);
    }
    const dw = maxX - minX;
    const dh = maxY - minY;

    // 居中偏移
    setOffset({
      x: Math.max(20, (cw - dw) / 2 - minX),
      y: Math.max(20, (ch - dh) / 2 - minY),
    });
  }, [diagram]);

  if (!diagram) {
    return (
      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', textAlign: 'center', color: '#475569', fontSize: 12 }}>
        <div style={{ fontSize: 32, marginBottom: 6 }}>🗺️</div>
        <div>选择左侧节点查看流程图</div>
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', opacity: 0.2 }}>
        <defs>
          <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
            <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#1e293b" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
      {diagram.edges.map(([from, to], i) => {
        const f = diagram.nodes.find(n => n.id === from);
        const t = diagram.nodes.find(n => n.id === to);
        if (!f || !t) return null;
        return (
          <svg key={`e${i}`} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}>
            <line x1={f.x + offset.x + f.w / 2} y1={f.y + offset.y + f.h} x2={t.x + offset.x + t.w / 2} y2={t.y + offset.y}
              stroke="#1e293b" strokeWidth="1" strokeDasharray="4 3" />
            <polygon points={`${t.x + offset.x + t.w / 2 - 4},${t.y + offset.y + 4} ${t.x + offset.x + t.w / 2 + 4},${t.y + offset.y + 4} ${t.x + offset.x + t.w / 2},${t.y + offset.y - 2}`}
              fill="#1e293b" />
          </svg>
        );
      })}
      {diagram.nodes.map(n => (
        <div key={n.id} style={{
          position: 'absolute', left: n.x + offset.x, top: n.y + offset.y, width: n.w, height: n.h,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2,
          borderRadius: 8, border: `1.5px solid ${STYLE_CLASSES[n.style] || '#64748b'}`,
          background: n.style === 'highlight' ? 'rgba(34,211,238,0.1)' :
                       n.style === 'layer' ? 'rgba(6,78,59,0.3)' :
                       n.style === 'db' ? 'rgba(76,29,149,0.3)' :
                       n.style === 'external' ? 'rgba(30,41,59,0.4)' :
                       'rgba(30,41,59,0.4)',
          fontSize: 12, cursor: 'pointer', padding: '2px 6px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontSize: 16, lineHeight: 1 }}>{n.icon}</span>
            <span style={{ fontWeight: 600, whiteSpace: 'nowrap', color: '#e2e8f0', fontSize: 12 }}>{n.label}</span>
          </div>
          {n.sub && <span style={{ fontSize: 9, color: '#64748b', lineHeight: 1.1, marginTop: 1 }}>{n.sub}</span>}
        </div>
      ))}
    </div>
  );
}

function TreeNodeItem({
  node, depth, selectedId, onSelect, expandedSet, onToggle,
}: {
  node: TreeNode; depth: number; selectedId: string | null;
  onSelect: (n: TreeNode) => void;
  expandedSet: Set<string>; onToggle: (id: string) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedSet.has(node.id);
  const isSelected = selectedId === node.id;

  return (
    <li style={{ position: 'relative', padding: '1px 0', listStyle: 'none' }}>
      <div
        className={`node ${isSelected ? 'selected' : ''}`}
        onClick={() => onSelect(node)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: '3px 8px 3px 4px', borderRadius: 4, cursor: 'pointer',
          border: `1px solid ${isSelected ? 'rgba(34,211,238,0.3)' : 'transparent'}`,
          background: isSelected ? 'rgba(34,211,238,0.1)' : undefined,
          fontSize: 11, lineHeight: 1.3, width: 'calc(100% - 4px)',
          transition: 'all 0.12s',
        }}
      >
        <span
          className={`toggle ${hasChildren ? (isExpanded ? 'expanded' : '') : 'empty'}`}
          onClick={(e) => { e.stopPropagation(); if (hasChildren) onToggle(node.id); }}
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 12, height: 12, fontSize: 7, color: '#475569',
            transform: isExpanded ? 'rotate(90deg)' : undefined,
            transition: 'transform 0.2s', flexShrink: 0,
            visibility: hasChildren ? 'visible' : 'hidden',
          }}
        >▶</span>
        <span className="icon" style={{ fontSize: 12, width: 16, textAlign: 'center', flexShrink: 0 }}>{node.icon}</span>
        <span className="label" style={{ color: '#e2e8f0', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {node.label}
        </span>
        {node.hasDiagram && (
          <span className="diagram-badge" style={{
            fontSize: 8, padding: '1px 6px', borderRadius: 8, marginLeft: 4, whiteSpace: 'nowrap', flexShrink: 0,
            background: 'linear-gradient(135deg, rgba(167,139,250,0.2), rgba(139,92,246,0.15))',
            color: '#a78bfa', border: '1px solid rgba(167,139,250,0.25)',
            fontWeight: 500, letterSpacing: 0.3,
          }}>流程图</span>
        )}
      </div>
      {hasChildren && isExpanded && (
        <ul style={{ listStyle: 'none', paddingLeft: 16 }}>
          {node.children!.map(child => (
            <TreeNodeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedSet={expandedSet}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ── 查找节点 ──
function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      const found = findNode(n.children, id);
      if (found) return found;
    }
  }
  return null;
}

// ── 查找流程图 ──
function findDiagramForNode(node: TreeNode): DiagramDef | null {
  if (DIAGRAMS[node.id]) return DIAGRAMS[node.id];
  // 递归向上查找祖先的流程图
  return null;
}

export function SelfMapView({ onBack }: { onBack: () => void }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedSet, setExpandedSet] = useState<Set<string>>(new Set(['frontend', 'backend', 'backend-core']));
  const [searchQuery, setSearchQuery] = useState('');
  const [leftWidth, setLeftWidth] = useState(260);
  const [rightWidth, setRightWidth] = useState(0);
  const resizing = useRef<'left' | 'right' | null>(null);

  const selected = selectedId ? findNode(TREE_DATA, selectedId) : null;
  const diagram = selected ? findDiagramForNode(selected) : null;

  const toggleExpand = useCallback((id: string) => {
    setExpandedSet(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSelect = useCallback((node: TreeNode) => {
    setSelectedId(node.id);
    setRightWidth(340);
  }, []);

  const closeDetail = useCallback(() => {
    setRightWidth(0);
  }, []);

  // 拖拽调整宽度
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (resizing.current === 'left') {
        setLeftWidth(Math.max(180, Math.min(400, e.clientX)));
      } else if (resizing.current === 'right') {
        const newW = Math.max(0, Math.min(500, window.innerWidth - e.clientX));
        setRightWidth(newW);
      }
    };
    const handleMouseUp = () => { resizing.current = null; document.body.style.cursor = ''; document.body.style.userSelect = ''; };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => { window.removeEventListener('mousemove', handleMouseMove); window.removeEventListener('mouseup', handleMouseUp); };
  }, []);

  const startResize = (side: 'left' | 'right') => (e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = side;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  // 搜索过滤
  const filterNodes = (nodes: TreeNode[], query: string): TreeNode[] => {
    if (!query.trim()) return nodes;
    return nodes.filter(n => {
      const match = n.label.includes(query) || (n.detail?.description || '').includes(query);
      const childMatch = n.children ? filterNodes(n.children, query).length > 0 : false;
      return match || childMatch;
    }).map(n => {
      if (!n.children) return n;
      return { ...n, children: filterNodes(n.children, query) };
    });
  };

  const filteredTree = searchQuery ? filterNodes(TREE_DATA, searchQuery) : TREE_DATA;

  // 自动展开搜索命中的节点
  useEffect(() => {
    if (searchQuery.trim()) {
      const collectParentIds = (nodes: TreeNode[], query: string, parents: string[] = []): string[] => {
        const results: string[] = [];
        for (const n of nodes) {
          const match = n.label.includes(query) || (n.detail?.description || '').includes(query);
          if (match) results.push(...parents);
          if (n.children) {
            const childResults = collectParentIds(n.children, query, [...parents, n.id]);
            results.push(...childResults);
          }
        }
        return results;
      };
      const parentIds = collectParentIds(TREE_DATA, searchQuery);
      if (parentIds.length > 0) setExpandedSet(prev => new Set([...prev, ...parentIds]));
    }
  }, [searchQuery]);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#020617', color: '#e2e8f0',
      display: 'flex', flexDirection: 'column',
      fontFamily: "'JetBrains Mono', 'Noto Sans SC', monospace",
    }}>
      {/* 顶栏 */}
      <div style={{ padding: '10px 16px', borderBottom: '1px solid #1e293b', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={onBack} className="garden-back-btn" style={{ background: 'none', border: '1px solid #1e293b', borderRadius: 6, padding: '4px 12px', color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>← 返回花园</button>
        <span style={{ fontSize: 16, fontWeight: 600, background: 'linear-gradient(135deg, #22d3ee, #34d399)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>⛰️ 坐山客 · 自省地图</span>
        <span style={{ fontSize: 11, color: '#475569', marginLeft: 'auto' }}>左树 · 中图 · 右侧详情</span>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左栏: 树 */}
        <div style={{ width: leftWidth, minWidth: 180, borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column', overflow: 'hidden', flexShrink: 0 }}>
          <input
            placeholder="搜索…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              background: '#0f172a', border: 'none', borderBottom: '1px solid #1e293b',
              padding: '8px 12px', color: '#e2e8f0', fontSize: 11,
              fontFamily: 'inherit', outline: 'none', flexShrink: 0,
            }}
          />
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0 20px 10px' }}>
            <ul className="tree" style={{ listStyle: 'none' }}>
              {filteredTree.map(node => (
                <TreeNodeItem
                  key={node.id}
                  node={node}
                  depth={0}
                  selectedId={selectedId}
                  onSelect={handleSelect}
                  expandedSet={expandedSet}
                  onToggle={toggleExpand}
                />
              ))}
            </ul>
          </div>
        </div>

        {/* 左分隔条 */}
        <div
          onMouseDown={startResize('left')}
          style={{ width: 3, cursor: 'col-resize', flexShrink: 0, background: 'transparent' }}
        />

        {/* 中栏: 流程图 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
          <div style={{
            padding: '8px 16px', borderBottom: '1px solid #1e293b', flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 8, minHeight: 36,
          }}>
            <span style={{ fontSize: 15 }}>{selected?.icon || '🏛️'}</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{selected?.label || '坐山客系统'}</span>
            <span style={{ fontSize: 10, color: '#64748b' }}>{diagram?.title || '选择左侧节点查看流程图'}</span>
            {diagram ? (
              <span style={{ marginLeft: 'auto', fontSize: 9, padding: '2px 6px', borderRadius: 6, background: 'rgba(34,211,238,0.1)', color: '#22d3ee', border: '1px solid rgba(34,211,238,0.2)' }}>
                有图
              </span>
            ) : (
              <span style={{ marginLeft: 'auto', fontSize: 9, padding: '2px 6px', borderRadius: 6, background: 'rgba(71,85,105,0.15)', color: '#475569', border: '1px solid #1e293b' }}>
                无图
              </span>
            )}
          </div>
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            <DiagramView diagram={diagram} />
          </div>
        </div>

        {/* 右分隔条 */}
        <div
          onMouseDown={startResize('right')}
          style={{ width: 3, cursor: 'col-resize', flexShrink: 0, background: 'transparent' }}
        />

        {/* 右栏: 详情抽屉 */}
        <div style={{
          width: rightWidth, overflow: 'hidden', display: 'flex', flexDirection: 'column',
          transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          background: '#0a0f1e', borderLeft: '1px solid #1e293b',
        }}>
          <div style={{ width: 340, minWidth: 280, flex: 1, overflowY: 'auto', padding: 16 }}>
            <DetailDrawer node={selected} onClose={closeDetail} />
          </div>
        </div>
      </div>
    </div>
  );
}

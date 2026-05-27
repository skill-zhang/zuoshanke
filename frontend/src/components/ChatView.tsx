import { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Message, ToolCard, ToolLog, Scene, Attachment } from '../api/client';
import { getActionMap, updateScene, uploadFile } from '../api/client';
import AgentLoopDashboard from './AgentLoopDashboard';  // 🆕 Schema v0.7
import { showConfirm, showAlert } from '../stores/dialogStore';
import { DelegationMonitor } from './DelegationMonitor';

// ══════════════════════════════════════════════════
//  工具卡片组件
// ══════════════════════════════════════════════════

/** 天气卡片 */
function WeatherCard({ data }: { data: Record<string, any> }) {
  const { city, desc, temp, humidity, wind, hourly } = data;
  // 当前日期（展示用）
  const now = new Date();
  const dateLabel = `${now.getMonth() + 1}月${now.getDate()}日`;
  const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
  const weekday = weekDays[now.getDay()];

  // hourly 柱状图计算
  let minT = 0, maxT = 40;
  if (hourly && hourly.length > 0) {
    const temps = hourly.map((h: any) => parseFloat(h.temp_c)).filter((t: number) => !isNaN(t));
    if (temps.length > 0) {
      minT = Math.min(...temps);
      maxT = Math.max(...temps);
      // 留点余量，让柱子有差异感
      if (maxT - minT < 5) { const mid = (maxT + minT) / 2; minT = mid - 5; maxT = mid + 5; }
    }
  }
  const barMin = 36, barMax = 100;

  const getTempColor = (t: number) => {
    if (t >= 30) return '#ff8c00';      // 🔥 炎热 → 橙色
    if (t >= 20) return '#ffd93d';      // ☀️ 温暖 → 浅黄
    if (t >= 10) return '#fdf0cc';      // 🌿 清凉 → 米白偏黄
    return '#b8d4f0';                   // ❄️ 冰 → 浅蓝偏白
  };

  const descToIcon = (d: string) => {
    if (d.includes('晴') || d.includes('Sunny')) return '☀';
    if (d.includes('雨') || d.includes('Rain')) return '🌧';
    if (d.includes('云') || d.includes('Cloud') || d.includes('阴')) return '☁';
    if (d.includes('雾') || d.includes('Mist') || d.includes('Fog')) return '🌫';
    return '🌤';
  };

  return (
    <div className="tool-card tool-card-weather">
      <div className="weather-card-body">
        <div className="weather-current">
          <div className="tool-card-header">
            <span className="tool-card-icon">🌤</span>
            <span className="tool-card-title">天气 · {city || '未知城市'}</span>
          </div>
          <div className="weather-date">{dateLabel} 周{weekday}</div>
          <div className="weather-main">
            <span className="weather-temp">{temp || 'N/A'}</span>
            <span className="weather-desc">{desc || ''}</span>
          </div>
          <div className="weather-details">
            {humidity && <span>💧 湿度 {humidity}</span>}
            {wind && <span>🌬 风力 {wind}</span>}
          </div>
        </div>
        {hourly && hourly.length > 0 && (
          <div className="weather-hourly">
            <div className="hourly-chart">
              {hourly.map((h: any, i: number) => {
                const t = parseFloat(h.temp_c);
                const hVal = isNaN(t) ? 50 : barMin + ((t - minT) / (maxT - minT || 1)) * (barMax - barMin);
                return (
                  <div key={i} className="hourly-bar-col">
                    <span className="hb-icon">{descToIcon(h.desc)}</span>
                    <div className="hb-bar-wrapper">
                      <div
                        className="hb-bar"
                        style={{ height: `${hVal}px`, background: getTempColor(isNaN(t) ? 20 : t) }}
                      >
                        <span className="hb-temp-label">{h.temp.replace('°C', '°')}</span>
                      </div>
                    </div>
                    <span className="hb-time">{h.time}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** 景点推荐卡片 */
function AttractionsCard({ data }: { data: Record<string, any> }) {
  const items: any[] = data.items || [];
  return (
    <div className="tool-card tool-card-attractions">
      <div className="tool-card-header">
        <span className="tool-card-icon">🎯</span>
        <span className="tool-card-title">
          景点推荐 · {data.city || ''}
          <span className="tool-card-badge">{data.category_label || ''}</span>
        </span>
      </div>
      <div className="tool-card-subtitle">
        {data.default_category && <>推荐类型: {data.default_category}</>}
        {data.total_matched != null && <> · 匹配 {data.total_matched} 个景点</>}
      </div>
      {items.length > 0 && (
        <div className="attractions-list">
          {items.slice(0, 6).map((item, i) => (
            <div key={i} className="attraction-item">
              <span className={`attraction-icon ${item.indoor ? 'indoor' : 'outdoor'}`}>
                {item.indoor ? '🏠' : '🌳'}
              </span>
              <div className="attraction-info">
                <span className="attraction-name">{item.name}</span>
                {item.note && <span className="attraction-note">{item.note}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 装备清单卡片 */
function EquipmentCard({ data }: { data: Record<string, any> }) {
  const items: any[] = data.items || [];
  const getNecessityColor = (n: string) => {
    if (n === '必带') return '#f85149';
    if (n === '推荐') return '#d29922';
    return '#8b949e';
  };
  const grouped = items.reduce((acc: Record<string, any[]>, item) => {
    const key = item.necessity || '可选';
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
  const necessityOrder = ['必带', '推荐', '可选'];

  return (
    <div className="tool-card tool-card-equipment">
      <div className="tool-card-header">
        <span className="tool-card-icon">{data.icon || '🎒'}</span>
        <span className="tool-card-title">
          装备建议 · {data.label || ''}
          <span className="tool-card-badge">{data.default_category || ''}</span>
        </span>
      </div>
      <div className="tool-card-subtitle">
        共 {data.total || 0} 项 · 
        <span style={{ color: '#f85149' }}>必带 {data.must_have || 0}</span> · 
        <span style={{ color: '#d29922' }}>推荐 {data.recommended || 0}</span> · 
        <span style={{ color: '#8b949e' }}>可选 {data.optional || 0}</span>
      </div>
      {necessityOrder.map(key => {
        const group = grouped[key];
        if (!group || group.length === 0) return null;
        return (
          <div key={key} className="equip-group">
            <div className="equip-group-title" style={{ color: getNecessityColor(key) }}>
              {key === '必带' ? '🔴' : key === '推荐' ? '🟡' : '⚪'} {key} ({group.length})
            </div>
            {group.slice(0, 8).map((item, i) => (
              <div key={i} className="equip-item">
                <span className="equip-item-name">{item.name}</span>
                {item.note && <span className="equip-item-note">{item.note}</span>}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** 工具卡片渲染器 */
function ToolCardsRenderer({ cards }: { cards: ToolCard[] }) {
  if (!cards || cards.length === 0) return null;
  return (
    <div className="tool-cards-container">
      {cards.map((card, i) => {
        if (card.type === 'weather') return <WeatherCard key={i} data={card.data} />;
        if (card.type === 'attractions') return <AttractionsCard key={i} data={card.data} />;
        if (card.type === 'equipment') return <EquipmentCard key={i} data={card.data} />;
        return null;
      })}
    </div>
  );
}


// ══════════════════════════════════════════════════
//  工具执行记录条（纯前端，不存库）
// ══════════════════════════════════════════════════

function ToolLogBar({ logs }: { logs: ToolLog[] }) {
  if (!logs || logs.length === 0) return null;
  const last = logs[logs.length - 1];
  const icon = last.status === 'running'
    ? (last.tool === '_analysis' ? '🤔' : '⏳')
    : last.status === 'error' ? '❌' : (last.success ? '✅' : '⚠️');
  return (
    <div className="tool-log-bar">
      {logs.map((log, i) => (
        <div key={i} className={`tool-log-item tool-log-${log.status}`}>
          <span className="tool-log-icon">
            {log.status === 'running'
              ? (log.tool === '_analysis' ? '🤔' : '⏳')
              : log.status === 'error' ? '❌' : (log.success ? '✅' : '⚠️')}
          </span>
          <span className="tool-log-label">{log.tool === '_analysis' ? '' : `[${log.tool}] `}</span>
          <span className="tool-log-msg">{log.message}</span>
        </div>
      ))}
    </div>
  );
}


// ══════════════════════════════════════════════════
//  消息气泡
// ══════════════════════════════════════════════════

function MessageBubble({ msg, toolCards, toolLogs, onDelete, onRegenerate, onOpenActionMap, selectMode, selected, onToggleSelect }: {
  msg: Message;
  toolCards?: ToolCard[];
  toolLogs?: ToolLog[];
  onDelete: (id: string) => void;
  onRegenerate: (id: string) => void;
  onOpenActionMap: (actionMapId: string) => void;
  selectMode: boolean;
  selected: boolean;
  onToggleSelect: (id: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`chat-msg ${msg.role} ${selected ? 'chat-msg-selected' : ''}`}>
      {selectMode && (
        <div className="chat-msg-check" onClick={() => onToggleSelect(msg.id)}>
          <div className={`check-box ${selected ? 'check-box-on' : ''}`}>
            {selected ? '✓' : ''}
          </div>
        </div>
      )}
      <div className="chat-msg-content">
        {/* 工具卡片（AI 消息渲染在 markdown 上方） */}
        {msg.role === 'ai' && toolCards && toolCards.length > 0 && (
          <ToolCardsRenderer cards={toolCards} />
        )}
        {/* 工具执行记录（仅临时消息显示） */}
        {msg.id.startsWith('temp-ai-') && toolLogs && toolLogs.length > 0 && (
          <ToolLogBar logs={toolLogs} />
        )}
        {/* 🆕 场景资产卡片 */}
        {msg.asset && (
          <div className="asset-card">
            <div className="asset-card-header">
              <span className="asset-card-icon">
                {msg.asset.type === 'checklist' ? '📋' : msg.asset.type === 'guide' ? '📖' : msg.asset.type === 'table' ? '📊' : '📄'}
              </span>
              <span className="asset-card-title">{msg.asset.title}</span>
            </div>
            <div className="asset-card-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {msg.asset.content}
              </ReactMarkdown>
            </div>
            <div className="asset-card-footer">
              <button className="asset-download-btn" onClick={() => {
                const blob = new Blob([msg.asset!.content], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = `${msg.asset!.title}.md`;
                a.click(); URL.revokeObjectURL(url);
              }}>
                📥 下载 Markdown
              </button>
            </div>
          </div>
        )}
        {/* 🆕 自动 HTML 产出卡片 */}
        {msg.outputRef && (
          <div className="output-ref-card">
            <div className="output-ref-header">
              <span className="output-ref-icon">📄</span>
              <span className="output-ref-title">{msg.outputRef.title}</span>
            </div>
            <button className="output-ref-open-btn" onClick={() => {
              window.open(`http://localhost:9001/outputs/${msg.outputRef!.filePath}`, '_blank');
            }}>
              ↗ 打开
            </button>
          </div>
        )}
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children} ↗
              </a>
            ),
          }}
        >
          {msg.content}
        </ReactMarkdown>
        {/* 🆕 文件/图片附件渲染 */}
        {msg.attachments && msg.attachments.length > 0 && (
          <div className="msg-attachment-list">
            {msg.attachments.map((att, i) => {
              const fileUrl = att.url.startsWith('/uploads/')
                ? `http://localhost:9001${att.url}`
                : att.url;
              if (att.file_type === 'image') {
                return (
                  <img
                    key={i}
                    src={fileUrl}
                    alt={att.filename}
                    className="msg-attachment-image"
                    onClick={() => window.open(fileUrl, '_blank')}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                );
              }
              return (
                <div key={i} className="msg-file-card">
                  <div className="msg-file-card-left">
                    <span className="msg-file-icon">📄</span>
                    <span className="msg-file-name">{att.filename}</span>
                  </div>
                  <button className="msg-file-open-btn" onClick={() => window.open(fileUrl, '_blank')}>
                    ↗ 打开
                  </button>
                </div>
              );
            })}
          </div>
        )}
        {msg.map_ref && (
          <div style={{ marginTop: '10px' }}>
            <button
              className="msg-action-btn"
              style={{
                background: 'rgba(63,185,80,0.1)', borderColor: '#3fb950', color: '#3fb950',
                fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
              }}
              onClick={() => onOpenActionMap(msg.map_ref!)}
            >
              ⚡ 查看 Action Map
            </button>
          </div>
        )}
        {msg.role === 'ai' && msg.model && (
          <div style={{
            marginTop: '8px', fontSize: '11px', color: '#8b949e',
            display: 'flex', alignItems: 'center', gap: '4px',
            borderTop: '1px solid rgba(139,148,158,0.15)', paddingTop: '6px',
          }}>
            <span style={{
              background: 'rgba(88,166,255,0.1)', color: '#58a6ff',
              padding: '1px 6px', borderRadius: '3px', fontSize: '10px',
            }}>⚙ {msg.model}</span>
          </div>
        )}
      </div>

      {!selectMode && (
        <div className="chat-msg-actions">
          <button className="msg-action-btn" onClick={handleCopy} title="复制">
            {copied ? '✅ 已复制' : '📋 复制'}
          </button>
          <button className="msg-action-btn" onClick={() => {}} title="语音朗读（即将支持）">
            🔊 朗读
          </button>
          <button className="msg-action-btn" onClick={() => {}} title="分享（即将支持）">
            📤 分享
          </button>
          {msg.role === 'ai' && (
            <button className="msg-action-btn" onClick={() => onRegenerate(msg.id)} title="重新生成">
              🔄 重新生成
            </button>
          )}
          <button className="msg-action-btn msg-action-delete" onClick={() => onDelete(msg.id)} title="删除">
            🗑 删除
          </button>
          <span className="msg-time">
            {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      )}
    </div>
  );
}

/** 空状态提示 */
function EmptyState({ isChannel }: { isChannel: boolean }) {
  return (
    <div className="chat-empty">
      <div className="chat-empty-icon">💬</div>
      <div className="chat-empty-text">
        {isChannel ? '在闲聊频道随便聊聊，AI 是你的聊天伙伴' : '选择左侧场景开始讨论需求，AI 帮你构建 Thinking Map'}
      </div>
      <div className="chat-empty-hint">
        {isChannel ? '按 Enter 发送，Shift+Enter 换行' : '说「梳理需求」让 AI 帮你分析'}
      </div>
    </div>
  );
}

export function ChatView() {
  const {
    messages, channelMessages,
    currentScene, currentChannel,
    sendSceneMsg, sendChannelMsg,
    deleteMsg, regenerateMsg, newSceneSession,
    batchDeleteMsgs, clearSceneMsgs, clearChannelHistory,
    sessions, loadSceneSessions, loadSceneMessages, switchSceneSession,
    currentSessionId,
    loadOlderMessages, loadOlderChannelMessages,
    hasOlderMessages, channelHasOlder,
    messagesLoading, channelMessagesLoading,
    messageTotalCount, channelMessageTotalCount,
    isGenerating,
    generatingEntityId,
    currentModelName,
    contextUsage,
    capacityWarning,
    currentToolCards,
    currentToolLogs,
    userContext, saveUserContext,
    compressChannel,
  } = useStore();

  // 当前实体（场景/频道）是否在生成中 — 不影响其他实体的发送按钮
  const currentEntityId = currentScene?.id || currentChannel?.id;
  const entityGenerating = isGenerating && generatingEntityId === currentEntityId;

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  // 🆕 文件上传状态
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // 用户输入背景设定
  const [ucExpanded, setUcExpanded] = useState(false);
  const [ucText, setUcText] = useState('');
  const [ucSaving, setUcSaving] = useState(false);
  const [ucEditMode, setUcEditMode] = useState(false);  // 是否正在编辑
  const [compressing, setCompressing] = useState(false);
  const ucSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ucTextareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);

  // 输入区折叠状态
  const [inputCollapsed, setInputCollapsed] = useState(false);

  // ═══ 分页加载状态 ═══
  const [showBackToBottom, setShowBackToBottom] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevMessageLenRef = useRef(0);
  const wasAtBottomRef = useRef(true);       // 用户是否在底部（更新前快照）
  const initialScrollDoneRef = useRef(false); // 首次加载是否已完成滚底
  const loadMoreSentinelRef = useRef<HTMLDivElement>(null);

  // ═══ 参数调测 ═══
  const [tempModalOpen, setTempModalOpen] = useState(false);
  const [tempValue, setTempValue] = useState(0.3);

  // ═══ 输入框拖拽调整高度 ═══
  const [inputHeight, setInputHeight] = useState(72);
  const resizingInput = useRef(false);
  const startResizeY = useRef(0);
  const startResizeH = useRef(72);

  const onInputResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingInput.current = true;
    startResizeY.current = e.clientY;
    startResizeH.current = textareaRef.current?.offsetHeight || 72;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!resizingInput.current || !textareaRef.current) return;
      const dy = e.clientY - startResizeY.current;
      const newH = Math.max(72, Math.min(400, startResizeH.current + dy));
      textareaRef.current.style.height = newH + 'px';
      setInputHeight(newH);
    };
    const onUp = () => {
      resizingInput.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // 多选模式
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 会话切换面板
  const [showSessionPanel, setShowSessionPanel] = useState(false);

  // 清空确认：两步确认防误触
  const [clearStep, setClearStep] = useState(0);

  // 判断当前模式
  const isChannel = !currentScene && !!currentChannel;
  const displayMessages: Message[] = isChannel ? channelMessages : messages;
  const contextLabel = isChannel
    ? `💬 ${currentChannel?.name || '闲聊'} · 自由聊天`
    : currentScene
      ? `🧠 ${currentScene.name} · AI 分析模式`
      : '';

  // 根据当前上下文推算默认模型（显示在输入框下方）
  const defaultModel = isChannel
    ? 'Qwen3.5 本地'
    : currentScene
      ? ({ 'light': 'Qwen3.5 本地', 'medium': 'DeepSeek Flash', 'heavy': 'DeepSeek Pro' } as Record<string, string>)[currentScene.complexity || ''] || 'Qwen3.5 本地'
      : null;
  const displayModel = currentModelName || defaultModel;

  // 组件卸载时重置生成状态，防止 SSE 断连后 isGenerating 卡死
  useEffect(() => {
    return () => {
      const store = useStore;
      if (store.getState().isGenerating) {
        store.setState({ isGenerating: false, generatingEntityId: null });
      }
    };
  }, []);

  // 在场景切换时加载会话列表
  useEffect(() => {
    if (currentScene) {
      loadSceneSessions(currentScene.id);
    } else {
      setSelectMode(false);
      setSelectedIds(new Set());
      setShowSessionPanel(false);
    }
  }, [currentScene?.id]);

  // 场景消息加载：等待 session ready 后才加载，避免无 session 过滤混入旧消息
  useEffect(() => {
    if (currentScene && currentSessionId) {
      loadSceneMessages(currentScene.id);
    }
  }, [currentScene?.id, currentSessionId]);

  // ═══ 自动滚动 — 初始化定位到底部，新消息来时仅在底部时自动滚动 ═══
  const scrollToBottom = useCallback((smooth = true) => {
    const container = messagesContainerRef.current;
    if (container) {
      requestAnimationFrame(() => {
        container.scrollTo({ top: container.scrollHeight, behavior: smooth ? 'smooth' : 'instant' });
      });
      setShowBackToBottom(false);
      setUnreadCount(0);
    }
  }, []);
  const isAtBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;
    const threshold = 120; // px from bottom
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }, []);

  // ═══ 自动滚动 — 消息变化时如果处于底部则自动滚到最新 ═══
  const prevLenRef = useRef(0);
  useEffect(() => {
    if (displayMessages.length === 0) return;

    // 首次加载消息（从空→有内容）：强制滚底
    if (!initialScrollDoneRef.current && displayMessages.length > 0) {
      initialScrollDoneRef.current = true;
      requestAnimationFrame(() => scrollToBottom(false));
      prevLenRef.current = displayMessages.length;
      return;
    }

    // 用户在底部 → 自动滚底（用 ref 快照而非实时 isAtBottom）
    if (wasAtBottomRef.current) {
      scrollToBottom(false);
    } else if (displayMessages.length > prevLenRef.current) {
      // 有新增消息且不在底部 → 显示浮标
      setShowBackToBottom(true);
      setUnreadCount(prev => prev + 1);
    }
    prevLenRef.current = displayMessages.length;
  }, [displayMessages, scrollToBottom]);

  // ═══ 发送消息时强制滚底 — 用户自己发的消息必须能看到 ═══
  const prevGeneratingRef = useRef(false);
  useEffect(() => {
    if (entityGenerating && !prevGeneratingRef.current) {
      // isGenerating 从 false → true：刚发送消息，强制滚到底
      scrollToBottom(false);
    }
    prevGeneratingRef.current = entityGenerating;
  }, [entityGenerating, scrollToBottom]);

  // 滚动监听：检测是否滚动到顶部（加载更早）或到底部（隐藏浮标）
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    // 记录用户是否在底部（内容更新前快照）
    wasAtBottomRef.current = container.scrollHeight - container.scrollTop - container.clientHeight < 120;

    // 向上滚到顶部 → 加载更早消息
    if (container.scrollTop < 80) {
      const isLoading = isChannel ? channelMessagesLoading : messagesLoading;
      const hasOlder = isChannel ? channelHasOlder : hasOlderMessages;
      const entityId = currentScene?.id || currentChannel?.id;
      if (!isLoading && hasOlder && entityId) {
        // 记录当前高度，用于 prepend 后保持滚动位置
        const oldScrollHeight = container.scrollHeight;
        const loadFn = isChannel ? loadOlderChannelMessages : loadOlderMessages;
        loadFn(entityId).then(() => {
          // prepend 后恢复滚动位置：新内容在顶部撑开
          const newScrollHeight = container.scrollHeight;
          container.scrollTop = newScrollHeight - oldScrollHeight;
        });
      }
    }

    // 检测是否在底部 → 隐藏浮标
    if (isAtBottom()) {
      setShowBackToBottom(false);
      setUnreadCount(0);
    }
  }, [isChannel, channelMessagesLoading, messagesLoading, channelHasOlder, hasOlderMessages,
      currentScene, currentChannel, loadOlderChannelMessages, loadOlderMessages, isAtBottom]);

  // 自动调整 textarea 高度（仅当内容超出现有高度时，不覆盖手动拖拽）
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta || resizingInput.current) return;
    const curH = ta.offsetHeight;
    ta.style.height = '0px';
    const scrollH = ta.scrollHeight;
    ta.style.height = curH + 'px';
    if (scrollH > curH + 4) {
      ta.style.height = Math.min(scrollH, 400) + 'px';
    }
  }, [input]);

  // ═══ 用户背景设定：同步 store → local ═══
  useEffect(() => {
    setUcText(userContext || '');
  }, [userContext]);

  // 组件卸载时清除防抖定时器
  useEffect(() => {
    return () => {
      if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    };
  }, []);

  // ═══ 用户背景设定：失焦自动保存 ═══
  const ucDoSave = useCallback(async (text: string) => {
    if (!currentScene) return;
    setUcSaving(true);
    await saveUserContext(currentScene.id, text);
    setUcSaving(false);
  }, [currentScene, saveUserContext]);

  const handleUcChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setUcText(val);
    // 防抖自动保存：1.5s 无输入后触发
    if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    ucSaveTimer.current = setTimeout(() => {
      ucDoSave(val);
    }, 1500);
  }, [ucDoSave]);

  const handleUcBlur = useCallback(() => {
    if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    ucDoSave(ucText);
  }, [ucDoSave, ucText]);

  const handleUcSave = useCallback(() => {
    if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    ucDoSave(ucText);
    setUcEditMode(false);
  }, [ucDoSave, ucText]);

  const handleUcDelete = useCallback(async () => {
    if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    setUcText('');
    setUcEditMode(false);
    if (currentScene) {
      setUcSaving(true);
      await saveUserContext(currentScene.id, '');
      setUcSaving(false);
    }
  }, [currentScene, saveUserContext]);

  const handleUcCopy = useCallback(() => {
    if (ucText) {
      navigator.clipboard.writeText(ucText).catch(() => {});
    }
  }, [ucText]);

  // 🆕 文件上传处理器
  const handleImageSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const result = await uploadFile(f);
        setAttachments(prev => [...prev, {
          url: result.url,
          file_type: result.file_type as 'image' | 'doc',
          filename: result.filename,
          size: result.size,
        }]);
      }
    } catch (err: any) {
      console.error('[upload] 图片上传失败:', err);
      await showAlert(err.message || '图片上传失败');
    } finally {
      setUploading(false);
      if (imageInputRef.current) imageInputRef.current.value = '';
    }
  }, []);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const result = await uploadFile(f);
        setAttachments(prev => [...prev, {
          url: result.url,
          file_type: result.file_type as 'image' | 'doc',
          filename: result.filename,
          size: result.size,
        }]);
      }
    } catch (err: any) {
      console.error('[upload] 文件上传失败:', err);
      await showAlert(err.message || '文件上传失败');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  }, []);

  const handleAttachImage = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const handleAttachFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // 生成附件预览 URL（用于缩略图渲染）
  const getPreviewUrl = (att: Attachment): string => {
    if (att.url.startsWith('/uploads/')) {
      return `http://localhost:9001${att.url}`;
    }
    return att.url;
  };

  const formatFileSize = (bytes?: number): string => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  // ═══ 上下文压缩 ═══
  const handleCompress = useCallback(async () => {
    if (!currentChannel || compressing) return;
    setCompressing(true);
    try {
      const summary = await compressChannel(currentChannel.id);
      if (summary) {
        console.log('[compress] 压缩完成:', summary.slice(0, 100));
      } else {
        console.warn('[compress] 压缩失败');
      }
    } catch (e) {
      console.error('[compress] error:', e);
    } finally {
      setCompressing(false);
    }
  }, [currentChannel, compressing, compressChannel]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || sending || entityGenerating) return;
    const currentAttachments = [...attachments];
    setInput('');
    setAttachments([]);
    setSending(true);

    try {
      if (isChannel && currentChannel) {
        sendChannelMsg(currentChannel.id, text, currentAttachments.length > 0 ? currentAttachments : undefined);
        setSending(false);
        return;
      } else if (currentScene) {
        sendSceneMsg(currentScene.id, text, currentAttachments.length > 0 ? currentAttachments : undefined);
        setSending(false);
        return;
      }
    } catch (e) {
      console.error('发送失败', e);
    } finally {
      setSending(false);
    }
  }, [input, sending, entityGenerating, isChannel, currentChannel, currentScene,
      sendChannelMsg, sendSceneMsg, attachments]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDelete = async (msgId: string) => {
    if (!await showConfirm('确定删除这条消息？')) return;
    await deleteMsg(msgId);
  };

  const handleNewSession = async () => {
    if (isChannel && currentChannel) {
      if (!await showConfirm('开始新对话？当前聊天记录将清空。')) return;
      await clearChannelHistory(currentChannel.id);
      return;
    }
    if (!currentScene) return;
    if (!await showConfirm('开始新对话？之前的聊天记录将保留但不再显示。')) return;
    setShowSessionPanel(false);
    await newSceneSession(currentScene.id);
  };

  const handleRegenerate = async (msgId: string) => {
    await regenerateMsg(msgId);
  };

  const handleOpenActionMap = useCallback(async (actionMapId: string) => {
    const store = useStore.getState();
    try {
      const amap = await getActionMap(actionMapId);
      if (store.thinkingMap) {
        await store.loadActionMaps(store.thinkingMap.id);
      }
      store.setCurrentActionMap(amap);
      store.openActionMapDrawer();
    } catch (e) {
      console.error('打开 Action Map 失败:', e);
    }
  }, []);

  // 多选操作
  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const enterSelectMode = () => {
    setSelectMode(true);
    setSelectedIds(new Set());
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!await showConfirm(`确定删除选中的 ${selectedIds.size} 条消息？`)) return;
    await batchDeleteMsgs(Array.from(selectedIds));
    exitSelectMode();
  };

  const handleClearAll = async () => {
    if (isChannel && currentChannel) {
      if (clearStep === 0) {
        setClearStep(1);
        return;
      }
      if (clearStep === 1) {
        if (!await showConfirm('⚠️ 此操作将永久删除该频道的所有聊天记录，不可恢复。确定继续？')) return;
        setClearStep(0);
        await clearChannelHistory(currentChannel.id);
      }
      return;
    }
    if (!currentScene) return;
    if (clearStep === 0) {
      setClearStep(1);
      return;
    }
    if (clearStep === 1) {
      if (!await showConfirm('⚠️ 此操作将永久删除场景的所有聊天记录，不可恢复。确定继续？')) return;
      setClearStep(0);
      await clearSceneMsgs(currentScene.id);
    }
  };

  const handleSwitchSession = async (sessionId: string | null) => {
    setShowSessionPanel(false);
    switchSceneSession(sessionId);
  };

  return (
    <div className="chat-overlay">
      <div className="chat-panel">
        {/* 上下文标签 */}
        {contextLabel && (
          <div className="chat-context-label">
            <span style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
              <span>{contextLabel}</span>
              {currentScene && !isChannel && (
                <span
                  className="temp-tune-btn"
                  onClick={() => {
                    const cfg = (currentScene as any).scene_config || {};
                    setTempValue(cfg.temperature ?? 0.3);
                    setTempModalOpen(true);
                  }}
                  title="参数调测"
                >⚙️ 参数</span>
              )}
            </span>
            <div className="chat-label-actions">
              <>
                {!isChannel && currentScene && (
                  <button className="new-session-btn" onClick={() => { setShowSessionPanel(!showSessionPanel); loadSceneSessions(currentScene.id); }} title="查看历史会话">
                    📋 记录
                  </button>
                )}
                {(currentScene || currentChannel) && (
                  <>
                    <button className="new-session-btn" onClick={handleNewSession} title="开始新对话">
                      🆕 新会话
                    </button>
                    <button className="new-session-btn" onClick={selectMode ? exitSelectMode : enterSelectMode} title={selectMode ? '退出选择' : '选择多条消息'}>
                      {selectMode ? '✅ 完成' : '☑️ 管理'}
                    </button>
                    <button
                      className={`new-session-btn ${clearStep > 0 ? 'danger-btn' : ''}`}
                      onClick={handleClearAll}
                      title="清空聊天记录"
                    >
                      {clearStep === 0 ? '🗑 清空' : '⚠️ 确认清空?'}
                    </button>
                  </>
                )}
              </>
            </div>
          </div>
        )}

        {/* 会话切换面板 */}
        {showSessionPanel && currentScene && (
          <div className="session-panel">
            <div className="session-panel-header">历史会话</div>
            <div className="session-panel-list">
              <div className="session-item" onClick={() => handleSwitchSession(null)}>
                <span className="session-item-name">📋 全部消息</span>
                <span className="session-item-count">{sessions.reduce((s, x) => s + x.message_count, 0)} 条</span>
              </div>
              {sessions.map(s => (
                <div key={s.session_id} className="session-item" onClick={() => handleSwitchSession(s.session_id)}>
                  <span className="session-item-name">🗂 会话</span>
                  <span className="session-item-info">
                    <span>{s.message_count} 条</span>
                    {s.last_active && <span> · {new Date(s.last_active).toLocaleString('zh-CN')}</span>}
                  </span>
                </div>
              ))}
              {sessions.length === 0 && <div className="session-empty">暂无历史会话</div>}
            </div>
          </div>
        )}

        {/* 多选操作栏 */}
        {selectMode && (
          <div className="select-mode-bar">
            <span>已选 {selectedIds.size} 条</span>
            <button
              className="select-delete-btn"
              onClick={handleBatchDelete}
              disabled={selectedIds.size === 0}
            >
              🗑 删除选中 ({selectedIds.size})
            </button>
            <button className="select-cancel-btn" onClick={exitSelectMode}>取消</button>
          </div>
        )}

        {/* 🆕 Schema v0.7: Agent Loop 仪表盘（仅场景模式） */}
        {currentScene && !currentChannel && (
          <AgentLoopDashboard />
        )}

        {/* 消息列表 */}
        <div className="chat-messages-wrapper">
          <div className="chat-messages" ref={messagesContainerRef} onScroll={handleScroll}>
          {/* 加载更早消息指示器 */}
          {(messagesLoading || channelMessagesLoading) && (
            <div style={{ textAlign: 'center', padding: '12px 0', color: '#8b949e', fontSize: 13 }}>
              ⏳ 加载更早消息...
            </div>
          )}
          {displayMessages.length === 0 && <EmptyState isChannel={isChannel} />}
          <DelegationMonitor />
          {displayMessages.map((msg, idx) => (
            msg.role === 'thought' ? (
              <div key={msg.id} className="msg-thought">
                💭 {msg.content}
              </div>
            ) : (
            <MessageBubble
              key={msg.id}
              msg={msg}
              // 流式生成中的最后一条 AI 消息显示当前工具卡片
              toolCards={
                msg.role === 'ai'
                  && idx === displayMessages.length - 1
                  ? (msg.toolCards || currentToolCards)
                  : undefined
              }
              // 工具执行记录（仅临时消息）
              toolLogs={
                msg.id.startsWith('temp-ai-')
                  ? currentToolLogs
                  : undefined
              }
              onDelete={handleDelete}
              onRegenerate={handleRegenerate}
              onOpenActionMap={handleOpenActionMap}
              selectMode={selectMode}
              selected={selectedIds.has(msg.id)}
              onToggleSelect={toggleSelect}
            />
            )
          ))}
          <div ref={bottomRef} />
        </div>
          {/* ═══ 回到最新消息浮标 ═══ */}
          {showBackToBottom && (
            <div className="back-to-bottom-btn" onClick={() => scrollToBottom(true)}>
              <span>↓ 回到最新</span>
              {unreadCount > 0 && <span className="back-to-bottom-badge">{unreadCount}</span>}
            </div>
          )}
        </div> {/* ═══ end chat-messages-wrapper ═══ */}

        {/* ═══ 参数调测弹窗 ═══ */}
        {tempModalOpen && currentScene && (
          <div className="modal-overlay show" onClick={() => setTempModalOpen(false)}>
            <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
              <div className="modal-title">
                <span>⚙️ 参数调测 · {currentScene.name}</span>
                <button className="modal-close" onClick={() => setTempModalOpen(false)}>✕</button>
              </div>
              <div className="form-group">
                <label className="form-label">Temperature</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <input
                    type="range" min="0.01" max="1" step="0.05"
                    value={tempValue}
                    onChange={e => setTempValue(parseFloat(e.target.value))}
                    style={{ flex: 1 }}
                  />
                  <span style={{ minWidth: 36, textAlign: 'right', color: '#e6edf3', fontSize: 14, fontWeight: 600 }}>
                    {tempValue.toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                  <span className="form-hint">保守 (0.1)</span>
                  <span className="form-hint">默认 (0.3)</span>
                  <span className="form-hint">创意 (0.7)</span>
                  <span className="form-hint">自由 (1.0)</span>
                </div>
              </div>
              <div className="modal-actions">
                <button className="btn" onClick={() => {
                  setTempValue((currentScene as any).scene_config?.temperature ?? 0.3);
                  setTempModalOpen(false);
                }}>取消</button>
                <button className="btn btn-primary" onClick={async () => {
                  const updated = await updateScene(currentScene.id, {
                    scene_config: { ...((currentScene as any).scene_config || {}), temperature: tempValue },
                  });
                  useStore.setState({ currentScene: updated as any });
                  // 刷新侧边栏场景列表，防止切回时读到旧缓存
                  useStore.getState().loadWorkshopScenes();
                  setTempModalOpen(false);
                }}>应用</button>
              </div>
            </div>
          </div>
        )}

        {/* ═══ 用户输入背景设定 ═══ */}
        {!isChannel && currentScene && (
          <div className="user-context-panel">
            <div className="user-context-header" onClick={() => { setUcExpanded(!ucExpanded); setUcEditMode(false); }}>
              <span>📝 用户输入背景设定</span>
              <span className="user-context-header-right">
                {ucText ? <span className="user-context-badge">已保存 {ucText.length} 字</span> : <span className="user-context-badge-empty">空</span>}
                <span className="user-context-chevron">{ucExpanded ? '▼' : '▶'}</span>
              </span>
            </div>
            {ucExpanded && (
              <div className="user-context-body">
                {ucEditMode ? (
                  <>
                    <textarea
                      ref={ucTextareaRef}
                      className="user-context-textarea"
                      value={ucText}
                      onChange={handleUcChange}
                      onBlur={handleUcBlur}
                      placeholder="在此输入你想让 AI 在本次对话中始终遵循的指令或背景信息，例如「每条推荐附具体链接」「用表格输出」「重点关注性价比选项」等"
                      maxLength={2000}
                      rows={4}
                    />
                    <div className="user-context-toolbar">
                      <span className="user-context-count">字数: {ucText.length}/2000</span>
                      <div className="user-context-actions">
                        <button className="uc-btn" onClick={handleUcDelete} title="清空内容">🗑 清空</button>
                        <button className="uc-btn" onClick={() => setUcEditMode(false)}>取消</button>
                        <button className="uc-btn uc-btn-primary" onClick={handleUcSave} disabled={ucSaving}>
                          {ucSaving ? '⏳' : '💾'} 保存
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '8px 12px' }}>
                    <div style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 6, padding: '8px 12px', minHeight: 40, maxHeight: 200, overflow: 'auto', fontSize: 13, lineHeight: 1.6, color: '#c9d1d9', marginBottom: 8 }}>
                      {ucText ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{ucText}</ReactMarkdown>
                      ) : (
                        <span style={{ color: '#484f58', fontStyle: 'italic' }}>未设置背景设定</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button className="uc-btn" onClick={() => setUcEditMode(true)}>✏️ 编辑</button>
                      <button className="uc-btn" onClick={handleUcCopy} title="复制到剪贴板">📋 复制</button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 输入区 */}
        <div className="chat-input-area" ref={inputAreaRef}>

          {/* ═══ 容量警告 ═══ */}
          {capacityWarning && (
            <div className="capacity-warning">
              <span>⚠️ {capacityWarning.message}</span>
              <button
                className="capacity-warning-btn"
                onClick={handleCompress}
                disabled={compressing}
                title="将历史对话压缩为摘要以释放上下文空间"
              >
                {compressing ? '⏳ 压缩中...' : '📝 压缩摘要'}
              </button>
            </div>
          )}

          <div className="chat-input-collapse-bar">
            <div className="chat-input-collapse-bar-left" />
            <div className="chat-input-collapse-bar-center" onClick={() => setInputCollapsed(!inputCollapsed)} title={inputCollapsed ? '展开输入区' : '收起输入区'}>
              <span className={`chat-input-chevron ${inputCollapsed ? 'collapsed' : ''}`}>▼</span>
            </div>
            <div className="chat-input-collapse-bar-right">
              <div className="chat-resize-handle" onMouseDown={onInputResizeStart} title="拖拽调整高度">
                <span className="chat-resize-dots">⠿</span>
              </div>
            </div>
          </div>
          {!inputCollapsed && (
            <>
              <div className="chat-input-wrapper">
                <textarea
                  ref={textareaRef}
                  className="chat-input"
                  placeholder={
                    isChannel
                      ? '随便聊聊...'
                      : '输入消息...（说「梳理需求」让 AI 帮你分析）'
                  }
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={sending || entityGenerating}
                  rows={2}
                />
                <div className="chat-input-toolbar">
                  <div className="chat-toolbar-left">
                    {/* 🆕 图片上传按钮 */}
                    <button
                      className="chat-toolbar-btn"
                      onClick={handleAttachImage}
                      disabled={uploading || sending || entityGenerating}
                      title="上传图片"
                    >
                      {uploading ? '⏳' : '🖼'}
                    </button>
                    {/* 🆕 文件上传按钮 */}
                    <button
                      className="chat-toolbar-btn"
                      onClick={handleAttachFile}
                      disabled={uploading || sending || entityGenerating}
                      title="上传文件"
                    >
                      {uploading ? '⏳' : '📎'}
                    </button>
                    {/* 隐藏的文件输入 */}
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/*"
                      multiple
                      style={{ display: 'none' }}
                      onChange={handleImageSelect}
                    />
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.txt,.json,.csv,.doc,.docx,.xls,.xlsx,.md,.zip"
                      multiple
                      style={{ display: 'none' }}
                      onChange={handleFileSelect}
                    />
                    {/* 🆕 附件预览条 */}
                    {attachments.length > 0 && (
                      <div className="chat-attachment-preview">
                        {attachments.map((att, i) => (
                          <div key={i} className="chat-attachment-item">
                            {att.file_type === 'image' ? (
                              <img
                                src={getPreviewUrl(att)}
                                alt={att.filename}
                                className="chat-attachment-thumb"
                                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                              />
                            ) : (
                              <span className="chat-attachment-icon">📄</span>
                            )}
                            <span className="chat-attachment-name">{att.filename}</span>
                            <span className="chat-attachment-remove" onClick={() => removeAttachment(i)}>✕</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    className="chat-send-btn"
                    onClick={handleSend}
                    disabled={sending || entityGenerating || (!input.trim() && attachments.length === 0)}
                  >
                    {sending || entityGenerating ? '⏳' : '发送'}
                  </button>
                </div>
              </div>
              <div className="chat-input-hint">
                  {contextUsage && (
                    <span
                      className="hint-token"
                      title={`上下文用量: ${contextUsage.usageStr} · 历史${contextUsage.historyCount}条消息 · ${contextUsage.percentage}%`}
                    >
                      ⚡ Token使用量：{contextUsage.usageStr}
                      <span className="hint-token-track">
                        <span
                          className={`hint-token-fill ${contextUsage.percentage >= 75 ? 'fill-danger' : contextUsage.percentage >= 50 ? 'fill-warn' : ''}`}
                          style={{ width: `${Math.min(contextUsage.percentage, 100)}%` }}
                        />
                      </span>
                    </span>
                  )}
                  {displayModel && (
                    <span>
                      <strong>当前模型:</strong> <strong><span className="chat-model-name">{displayModel}</span></strong>
                    </span>
                  )}
                  <span className="hint-hotkeys">
                    {(contextUsage || displayModel) ? ' · ' : ''}Enter 发送 · Shift+Enter 换行
                  </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

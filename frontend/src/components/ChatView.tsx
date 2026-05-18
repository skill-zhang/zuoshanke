import { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Message, ToolCard, ToolLog } from '../api/client';
import { getActionMap } from '../api/client';

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
    batchDeleteMsgs, clearSceneMsgs,
    sessions, loadSceneSessions, switchSceneSession,
    isGenerating,
    currentModelName,
    contextUsage,
    capacityWarning,
    currentToolCards,
    currentToolLogs,
    userContext, saveUserContext,
    compressChannel,
  } = useStore();

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploadMenu, setUploadMenu] = useState(false);
  // 用户输入背景设定
  const [ucExpanded, setUcExpanded] = useState(false);
  const [ucText, setUcText] = useState('');
  const [ucSaving, setUcSaving] = useState(false);
  const [compressing, setCompressing] = useState(false);
  const ucSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ucTextareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);

  // 输入区折叠状态
  const [inputCollapsed, setInputCollapsed] = useState(false);

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

  // 自动滚动
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMessages]);

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
  }, [ucDoSave, ucText]);

  const handleUcDelete = useCallback(async () => {
    if (ucSaveTimer.current) clearTimeout(ucSaveTimer.current);
    setUcText('');
    if (currentScene) {
      setUcSaving(true);
      await saveUserContext(currentScene.id, '');
      setUcSaving(false);
    }
  }, [currentScene, saveUserContext]);

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
    if (!text || sending || isGenerating) return;
    setInput('');
    setSending(true);

    try {
      if (isChannel && currentChannel) {
        sendChannelMsg(currentChannel.id, text);
        setSending(false);
        return;
      } else if (currentScene) {
        sendSceneMsg(currentScene.id, text);
        setSending(false);
        return;
      }
    } catch (e) {
      console.error('发送失败', e);
    } finally {
      setSending(false);
    }
  }, [input, sending, isGenerating, isChannel, currentChannel, currentScene, sendChannelMsg, sendSceneMsg]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDelete = async (msgId: string) => {
    if (!confirm('确定删除这条消息？')) return;
    await deleteMsg(msgId);
  };

  const handleNewSession = async () => {
    if (!currentScene) return;
    if (!confirm('开始新对话？之前的聊天记录将保留但不再显示。')) return;
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
    if (!confirm(`确定删除选中的 ${selectedIds.size} 条消息？`)) return;
    await batchDeleteMsgs(Array.from(selectedIds));
    exitSelectMode();
  };

  const handleClearAll = async () => {
    if (!currentScene) return;
    if (clearStep === 0) {
      setClearStep(1);
      return;
    }
    if (clearStep === 1) {
      if (!confirm('⚠️ 此操作将永久删除场景的所有聊天记录，不可恢复。确定继续？')) return;
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
            <span>{contextLabel}</span>
            <div className="chat-label-actions">
              {!isChannel && currentScene && (
                <>
                  <button className="new-session-btn" onClick={() => { setShowSessionPanel(!showSessionPanel); loadSceneSessions(currentScene.id); }} title="查看历史会话">
                    📋 记录
                  </button>
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

        {/* 消息列表 */}
        <div className="chat-messages">
          {displayMessages.length === 0 && <EmptyState isChannel={isChannel} />}
          {displayMessages.map((msg, idx) => (
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
          ))}
          <div ref={bottomRef} />
        </div>

        {/* ═══ 用户输入背景设定 ═══ */}
        {!isChannel && currentScene && (
          <div className="user-context-panel">
            <div className="user-context-header" onClick={() => setUcExpanded(!ucExpanded)}>
              <span>📝 用户输入背景设定</span>
              <span className="user-context-header-right">
                {ucText ? <span className="user-context-badge">已保存 {ucText.length} 字</span> : <span className="user-context-badge-empty">空</span>}
                <span className="user-context-chevron">{ucExpanded ? '▼' : '▶'}</span>
              </span>
            </div>
            {ucExpanded && (
              <div className="user-context-body">
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
                    <button className="uc-btn" onClick={handleUcDelete} title="清空内容">🗑 删除</button>
                    <button className="uc-btn uc-btn-primary" onClick={handleUcSave} disabled={ucSaving}>
                      {ucSaving ? '⏳' : '💾'} 保存
                    </button>
                  </div>
                </div>
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
                  disabled={sending || isGenerating}
                  rows={2}
                />
                <div className="chat-input-toolbar">
                  <div className="chat-toolbar-left">
                    <button
                      className="chat-toolbar-btn"
                      onClick={() => setUploadMenu(!uploadMenu)}
                      title="上传文件"
                    >
                      📎 文件
                    </button>
                    <button
                      className="chat-toolbar-btn"
                      onClick={() => setUploadMenu(!uploadMenu)}
                      title="上传图片"
                    >
                      🖼 图片
                    </button>
                    {uploadMenu && (
                      <div className="chat-upload-menu">
                        <div className="chat-upload-item" onClick={() => { alert('文件上传功能即将支持'); setUploadMenu(false); }}>
                          📄 上传文件
                        </div>
                        <div className="chat-upload-item" onClick={() => { alert('图片上传功能即将支持'); setUploadMenu(false); }}>
                          🖼 上传图片
                        </div>
                      </div>
                    )}
                  </div>
                  <button
                    className="chat-send-btn"
                    onClick={handleSend}
                    disabled={sending || isGenerating || !input.trim()}
                  >
                    {sending || isGenerating ? '⏳' : '发送'}
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

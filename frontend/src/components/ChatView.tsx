import { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Message } from '../api/client';
import { getActionMap } from '../api/client';

/** 单条消息气泡（支持多选模式） */
function MessageBubble({ msg, onDelete, onRegenerate, onOpenActionMap, selectMode, selected, onToggleSelect }: {
  msg: Message;
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
      </div>

      {!selectMode && (
        <div className="chat-msg-actions">
          <button className="msg-action-btn" onClick={handleCopy} title="复制">
            {copied ? '✅ 已复制' : '📋 复制'}
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
  } = useStore();

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploadMenu, setUploadMenu] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  // 自动调整 textarea 高度
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    }
  }, [input]);

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
          {displayMessages.map((msg) => (
            <MessageBubble
              key={msg.id}
              msg={msg}
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

        {/* 输入区 */}
        <div className="chat-input-area">
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
            Enter 发送 · Shift+Enter 换行
          </div>
        </div>
      </div>
    </div>
  );
}

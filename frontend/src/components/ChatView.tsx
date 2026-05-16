import { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Message } from '../api/client';
import { getActionMap } from '../api/client';

/** 单条消息气泡 */
function MessageBubble({ msg, onDelete, onRegenerate, onOpenActionMap }: {
  msg: Message;
  onDelete: (id: string) => void;
  onRegenerate: (id: string) => void;
  onOpenActionMap: (actionMapId: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTTS = () => {
    // TODO: 对接 TTS API
    alert('语音朗读功能即将支持');
  };

  const handleShare = () => {
    // TODO: 分享功能
    alert('分享功能即将支持');
  };

  return (
    <div className={`chat-msg ${msg.role}`}>
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

      <div className="chat-msg-actions">
        <button className="msg-action-btn" onClick={handleCopy} title="复制">
          {copied ? '✅ 已复制' : '📋 复制'}
        </button>
        <button className="msg-action-btn" onClick={handleTTS} title="语音朗读">
          🔊 朗读
        </button>
        <button className="msg-action-btn" onClick={handleShare} title="分享">
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
    deleteMsg, regenerateMsg,
    isGenerating,
  } = useStore();

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [uploadMenu, setUploadMenu] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 判断当前模式
  const isChannel = !currentScene && !!currentChannel;
  const displayMessages: Message[] = isChannel ? channelMessages : messages;
  const contextLabel = isChannel
    ? `💬 ${currentChannel?.name || '闲聊'} · 自由聊天`
    : currentScene
      ? `🧠 ${currentScene.name} · AI 分析模式`
      : '';

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
        // 频道流式模式：不 await，store 内部管理 isGenerating
        sendChannelMsg(currentChannel.id, text);
        setSending(false);
        return;
      } else if (currentScene) {
        // 场景流式模式：不 await，store 内部管理 isGenerating
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

  const handleRegenerate = async (msgId: string) => {
    await regenerateMsg(msgId);
  };

  const handleOpenActionMap = useCallback(async (actionMapId: string) => {
    const store = useStore.getState();
    try {
      const amap = await getActionMap(actionMapId);
      // 先加载列表，再设当前
      if (store.thinkingMap) {
        await store.loadActionMaps(store.thinkingMap.id);
      }
      store.setCurrentActionMap(amap);
      store.openActionMapDrawer();
    } catch (e) {
      console.error('打开 Action Map 失败:', e);
    }
  }, []);

  return (
    <div className="chat-overlay">
      <div className="chat-panel">
        {/* 上下文标签 */}
        {contextLabel && (
          <div className="chat-context-label">{contextLabel}</div>
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

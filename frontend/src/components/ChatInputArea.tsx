import { useState, useRef, useEffect, useCallback } from 'react';
import { useStore } from '../stores/appStore';
import { uploadFile } from '../api/client';
import { showAlert } from '../stores/dialogStore';
import type { Attachment } from '../api/client';

export function ChatInputArea() {
  const {
    currentScene,
    currentChannel,
    sendSceneMsg,
    sendChannelMsg,
    isGenerating,
    generatingEntityId,
    capacityWarning,
    currentModelName,
    contextUsage,
    compressChannel,
  } = useStore();

  const currentEntityId = currentScene?.id || currentChannel?.id;
  const entityGenerating = isGenerating && generatingEntityId === currentEntityId;
  const isChannel = !currentScene && !!currentChannel;

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);

  // 输入区折叠
  const [inputCollapsed, setInputCollapsed] = useState(false);

  // ═══ 输入框拖拽调整高度 ═══
  const resizingInput = useRef(false);
  const startResizeY = useRef(0);
  const startResizeH = useRef(72);
  const [compressing, setCompressing] = useState(false);

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

  // ═══ 文件上传 ═══
  const handleImageSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const result = await uploadFile(f);
        setAttachments((prev) => [
          ...prev,
          {
            url: result.url,
            file_type: result.file_type as 'image' | 'doc',
            filename: result.filename,
            size: result.size,
          },
        ]);
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
        setAttachments((prev) => [
          ...prev,
          {
            url: result.url,
            file_type: result.file_type as 'image' | 'doc',
            filename: result.filename,
            size: result.size,
          },
        ]);
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
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleAttachImage = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const handleAttachFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const getPreviewUrl = (att: Attachment): string => {
    if (att.url.startsWith('/uploads/')) {
      return `http://localhost:9001${att.url}`;
    }
    return att.url;
  };

  // ═══ 发送 ═══
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || sending || entityGenerating) return;
    const currentAttachments = [...attachments];
    setInput('');
    setAttachments([]);
    setSending(true);
    useStore.setState({ lastError: null });

    try {
      if (isChannel && currentChannel) {
        sendChannelMsg(
          currentChannel.id,
          text,
          currentAttachments.length > 0 ? currentAttachments : undefined
        );
        setSending(false);
        return;
      } else if (currentScene) {
        sendSceneMsg(
          currentScene.id,
          text,
          currentAttachments.length > 0 ? currentAttachments : undefined
        );
        setSending(false);
        return;
      }
    } catch (e) {
      console.error('发送失败', e);
    } finally {
      setSending(false);
    }
  }, [
    input,
    sending,
    entityGenerating,
    isChannel,
    currentChannel,
    currentScene,
    sendChannelMsg,
    sendSceneMsg,
    attachments,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 当前模型显示
  const defaultModel = isChannel
    ? 'Qwen3.5 本地'
    : currentScene
      ? (
          { light: 'Qwen3.5 本地', medium: 'DeepSeek Flash', heavy: 'DeepSeek Pro' } as Record<
            string,
            string
          >
        )[currentScene.complexity || ''] || 'Qwen3.5 本地'
      : null;
  const displayModel = currentModelName || defaultModel;

  return (
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
        <div
          className="chat-input-collapse-bar-center"
          onClick={() => setInputCollapsed(!inputCollapsed)}
          title={inputCollapsed ? '展开输入区' : '收起输入区'}
        >
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
                isChannel ? '随便聊聊...' : '输入消息...（说「梳理需求」让 AI 帮你分析）'
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending || entityGenerating}
              rows={2}
            />
            <div className="chat-input-toolbar">
              <div className="chat-toolbar-left">
                {/* 图片上传按钮 */}
                <button
                  className="chat-toolbar-btn"
                  onClick={handleAttachImage}
                  disabled={uploading || sending || entityGenerating}
                  title="上传图片"
                >
                  {uploading ? '⏳' : '🖼'}
                </button>
                {/* 文件上传按钮 */}
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
                {/* 附件预览条 */}
                {attachments.length > 0 && (
                  <div className="chat-attachment-preview">
                    {attachments.map((att, i) => (
                      <div key={i} className="chat-attachment-item">
                        {att.file_type === 'image' ? (
                          <img
                            src={getPreviewUrl(att)}
                            alt={att.filename}
                            className="chat-attachment-thumb"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <span className="chat-attachment-icon">📄</span>
                        )}
                        <span className="chat-attachment-name">{att.filename}</span>
                        <span
                          className="chat-attachment-remove"
                          onClick={() => removeAttachment(i)}
                        >
                          ✕
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <button
                className="chat-send-btn"
                onClick={handleSend}
                disabled={
                  sending || entityGenerating || (!input.trim() && attachments.length === 0)
                }
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
                <strong>当前模型:</strong>{' '}
                <strong>
                  <span className="chat-model-name">{displayModel}</span>
                </strong>
              </span>
            )}
            <span className="hint-hotkeys">
              {contextUsage || displayModel ? ' · ' : ''}Enter 发送 · Shift+Enter 换行
            </span>
          </div>
        </>
      )}
    </div>
  );
}

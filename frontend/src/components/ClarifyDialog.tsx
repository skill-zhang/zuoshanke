/** Clarify 弹窗 — 自开发场景中 LLM 问用户问题时显示 */
import { useEffect, useRef } from 'react';
import { useStore } from 'zustand';
import { clarifyStore } from '../stores/clarifyStore';

export function ClarifyDialog() {
  const { visible, info, submitting, customInput, setCustomInput, submitResponse, dismiss } = useStore(clarifyStore);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 轮询 pending clarify 请求
  useEffect(() => {
    if (visible) {
      // 正在显示时停止轮询
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    pollRef.current = setInterval(() => {
      clarifyStore.getState().checkPending();
    }, 800);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [visible]);

  // 可见时按 Esc 关闭
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, dismiss]);

  if (!visible || !info) return null;

  const handleChoice = (choice: string) => {
    submitResponse(choice);
  };

  const handleCustomSubmit = () => {
    if (customInput.trim()) {
      submitResponse(customInput.trim());
    }
  };

  const hasChoices = info.choices && info.choices.length > 0;

  return (
    <div className="modal-overlay show" onClick={dismiss}>
      <div className="modal" onClick={e => e.stopPropagation()}
           style={{ maxWidth: 480 }}>
        <div className="modal-title">
          <span>坐山客需要你确认 ↻</span>
          <button className="modal-close" onClick={dismiss}>✕</button>
        </div>

        <p style={{ margin: '12px 0 16px 0', color: '#c9d1d9', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
          {info.question}
        </p>

        {hasChoices ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}>
            {info.choices!.map((choice, i) => (
              <button
                key={i}
                className="btn"
                disabled={submitting}
                style={{
                  textAlign: 'left',
                  padding: '10px 14px',
                  fontSize: 13,
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 8,
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  opacity: submitting ? 0.6 : 1,
                }}
                onClick={() => handleChoice(choice)}
              >
                {choice}
              </button>
            ))}
            {/* 其他选项：手动输入 */}
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <input
                className="form-input"
                placeholder="其他（手动输入）..."
                value={customInput}
                onChange={e => setCustomInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleCustomSubmit(); }}
                disabled={submitting}
                style={{ flex: 1 }}
              />
              <button
                className="btn btn-primary"
                onClick={handleCustomSubmit}
                disabled={submitting || !customInput.trim()}
              >
                {submitting ? '发送中...' : '发送'}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input
              className="form-input"
              placeholder="输入你的回答..."
              value={customInput}
              onChange={e => setCustomInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCustomSubmit(); }}
              disabled={submitting}
              autoFocus
              style={{ flex: 1 }}
            />
            <button
              className="btn btn-primary"
              onClick={handleCustomSubmit}
              disabled={submitting || !customInput.trim()}
            >
              {submitting ? '发送中...' : '发送'}
            </button>
          </div>
        )}

        {submitting && (
          <p style={{ margin: 0, color: '#8b949e', fontSize: 12, textAlign: 'center' }}>
            等待坐山客继续...
          </p>
        )}
      </div>
    </div>
  );
}

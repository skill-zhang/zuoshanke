/** 统一对话框组件 — 弹窗形式替代系统 alert/confirm/prompt */
import { useEffect, useRef } from 'react';
import { useStore } from 'zustand';
import { dialogStore } from '../stores/dialogStore';

export function Dialog() {
  const { visible, type, title, message, confirmText, cancelText, inputValue } = useStore(dialogStore);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (visible && type === 'prompt') {
      setTimeout(() => inputRef.current?.focus(), 80);
      setTimeout(() => inputRef.current?.select(), 100);
    }
  }, [visible, type]);

  if (!visible) return null;

  const handleConfirm = () => {
    if (type === 'prompt') {
      dialogStore.getState().hide(inputValue);
    } else if (type === 'confirm') {
      dialogStore.getState().hide(true);
    } else {
      dialogStore.getState().hide(undefined);
    }
  };

  const handleCancel = () => {
    if (type === 'prompt') {
      dialogStore.getState().hide(null);
    } else if (type === 'confirm') {
      dialogStore.getState().hide(false);
    } else {
      dialogStore.getState().hide(undefined);
    }
  };

  const handleOverlayClick = () => {
    if (type !== 'alert') handleCancel();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleConfirm();
    if (e.key === 'Escape') handleCancel();
  };

  return (
    <div className="modal-overlay show" onClick={handleOverlayClick}>
      <div className={`modal ${type === 'alert' ? 'modal-sm' : ''}`} onClick={e => e.stopPropagation()} onKeyDown={handleKeyDown}>
        <div className="modal-title">
          <span>{title}</span>
          <button className="modal-close" onClick={handleCancel}>✕</button>
        </div>

        {type === 'prompt' ? (
          <div className="form-group">
            <label className="form-label">{message}</label>
            <input
              ref={inputRef}
              className="form-input"
              value={inputValue}
              onChange={e => dialogStore.getState().setInputValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleConfirm(); if (e.key === 'Escape') handleCancel(); }}
            />
          </div>
        ) : (
          <p style={{ margin: 0, color: '#c9d1d9', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
            {message}
          </p>
        )}

        <div className="modal-actions">
          {type !== 'alert' && (
            <button className="btn" onClick={handleCancel}>{cancelText}</button>
          )}
          <button className="btn btn-primary" onClick={handleConfirm}>
            {type === 'alert' ? '知道了' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 自定义对话框状态 — 替代系统 alert/confirm/prompt */
import { create } from 'zustand';

type DialogType = 'alert' | 'confirm' | 'prompt';

interface DialogOptions {
  title?: string;
  message: string;
  defaultValue?: string;
  confirmText?: string;
  cancelText?: string;
}

interface DialogState {
  visible: boolean;
  type: DialogType;
  title: string;
  message: string;
  defaultValue: string;
  confirmText: string;
  cancelText: string;
  inputValue: string;
  show: (type: DialogType, options: DialogOptions) => Promise<any>;
  hide: (result?: any) => void;
  setInputValue: (v: string) => void;
}

// 模块级 resolve 引用，避免非序列化数据进 zustand
let _resolve: ((value: any) => void) | null = null;
let _reject: ((reason: any) => void) | null = null;

export const dialogStore = create<DialogState>((set) => ({
  visible: false,
  type: 'alert',
  title: '',
  message: '',
  defaultValue: '',
  inputValue: '',
  confirmText: '确定',
  cancelText: '取消',

  show: (type, options) => {
    return new Promise<any>((resolve, reject) => {
      _resolve = resolve;
      _reject = reject;
      set({
        visible: true,
        type,
        title: options.title || (type === 'alert' ? '提示' : type === 'confirm' ? '确认' : '输入'),
        message: options.message,
        defaultValue: options.defaultValue || '',
        inputValue: options.defaultValue || '',
        confirmText: options.confirmText || '确定',
        cancelText: options.cancelText || '取消',
      });
    });
  },

  hide: (result) => {
    set({ visible: false, inputValue: '' });
    if (_resolve) {
      _resolve(result);
      _resolve = null;
      _reject = null;
    }
  },

  setInputValue: (v) => set({ inputValue: v }),
}));

// ─── 全局便捷函数（签名与原生 alert/confirm/prompt 一致）───

export function showAlert(message: string): Promise<void> {
  return dialogStore.getState().show('alert', { message });
}

export function showConfirm(message: string): Promise<boolean> {
  return dialogStore.getState().show('confirm', { message });
}

export function showPrompt(message: string, defaultValue?: string): Promise<string | null> {
  return dialogStore.getState().show('prompt', { message, defaultValue });
}

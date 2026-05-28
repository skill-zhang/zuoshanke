/**
 * 🛡️ ErrorBoundary — React 错误边界
 *
 * 捕获子组件渲染/生命周期中的 JS 错误，兜底展示 fallback UI，
 * 避免整个应用白屏。
 *
 * 用法：
 *   <ErrorBoundary>
 *     <WorkbenchView />
 *   </ErrorBoundary>
 *
 * 可自定义 fallback：
 *   <ErrorBoundary fallback={<CustomFallback />}>
 *     <WorkbenchView />
 *   </ErrorBoundary>
 */
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] 捕获错误:', error.message);
    console.error('[ErrorBoundary] 组件栈:', info.componentStack);
    this.props.onError?.(error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          background: '#0d1117',
          color: '#c9d1d9',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          padding: '32px',
          textAlign: 'center',
        }}>
          <div style={{
            fontSize: '64px',
            marginBottom: '16px',
            lineHeight: 1,
          }}>🛡️</div>
          <h2 style={{
            margin: '0 0 8px',
            fontSize: '20px',
            fontWeight: 600,
            color: '#e6edf3',
          }}>工作台加载失败</h2>
          <p style={{
            margin: '0 0 24px',
            fontSize: '14px',
            color: '#8b949e',
            maxWidth: '400px',
          }}>
            个人工作台遇到了一个意外错误，其他功能不受影响。
            {this.state.error && (
              <>
                <code style={{
                  display: 'block',
                  marginTop: '12px',
                  padding: '8px 12px',
                  background: '#161b22',
                  borderRadius: '6px',
                  fontSize: '12px',
                  color: '#f85149',
                  wordBreak: 'break-all',
                }}>
                  {this.state.error.message}
                </code>
                <p style={{
                  margin: '12px 0 0',
                  fontSize: '12px',
                  color: '#6e7681',
                }}>
                  💡 重试如果再次失败，请使用「刷新页面」
                </p>
              </>
            )}
          </p>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={this.handleReset}
              style={{
                padding: '8px 20px',
                background: '#238636',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '14px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 20px',
                background: '#21262d',
                color: '#c9d1d9',
                border: '1px solid #30363d',
                borderRadius: '6px',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * 🏠 WorkbenchView — 坐山客工作台（Schema v1.3）
 *
 * 独立页面：无 Topbar / Sidebar，Avatar 居中浮顶。
 * 卡片三区域：header→聊天 / body→产出类型自适应 / footer→产出入口。
 * 底部浮动对话栏驱动卡片增删改排序。
 *
 * 所有卡片数据从 scene.scene_config JSON 读取，不做文本解析。
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useStore } from '../stores/appStore';
import { Scene } from '../api/client';

export function WorkbenchView() {
  const { scenes, loadScenes, loadingScenes, setView, setCurrentScene, loadThinkingMap, loadSceneMessages,
    setCurrentChannel, channels, setAgentStatus, setAgentMessage, setAgentSpeaking } = useStore();

  const [clock, setClock] = useState('');
  const [greeting, setGreeting] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [inputVal, setInputVal] = useState('');
  const [barExpanded, setBarExpanded] = useState(true);
  const [avatarSpeech, setAvatarSpeech] = useState('');       // 🆕 Avatar 说话文字
  const [avatarSpeaking, setAvatarSpeaking] = useState(false); // 🆕 Avatar 是否在说话
  const processingRef = useRef(false);  // 🆕 防重复提交锁

  useEffect(() => { loadScenes(); }, []);

  const workbenchScenes = scenes
    .filter(s => s.show_on_workbench)
    .sort((a, b) => (a.workbench_position ?? 0) - (b.workbench_position ?? 0));

  // 🆕 打开工作台时自动刷新 stock 类场景的最新股价
  const [stockRefreshed, setStockRefreshed] = useState(false);
  useEffect(() => {
    if (!loadingScenes && workbenchScenes.length > 0 && !stockRefreshed) {
      const stockScenes = workbenchScenes.filter(s => s.category === 'stock');
      if (stockScenes.length > 0) {
        Promise.all(stockScenes.map(s =>
          fetch(`/api/scenes/${s.id}/refresh-stock`, { method: 'POST' }).catch(() => {})
        )).then(() => {
          loadScenes();
          setStockRefreshed(true);
        });
      } else {
        setStockRefreshed(true);
      }
    }
  }, [loadingScenes, workbenchScenes.length, stockRefreshed]);

  // ═══ 时钟 + 问候语 ═══
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      const h = now.getHours();
      if (h < 6)       setGreeting('夜深了 🌙');
      else if (h < 9)  setGreeting('早上好 🌅');
      else if (h < 12) setGreeting('上午好 ☀️');
      else if (h < 14) setGreeting('中午好 ☀️');
      else if (h < 18) setGreeting('下午好 🌤️');
      else             setGreeting('晚上好 🌆');
      setSubtitle(`${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 星期${['日','一','二','三','四','五','六'][now.getDay()]}`);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  // ═══ 进入场景 ═══
  const handleEnterScene = useCallback(async (scene: Scene) => {
    setCurrentScene(scene);
    setCurrentChannel(channels[0] || null);
    setView('chat');
    await loadThinkingMap(scene.id);
    await loadSceneMessages(scene.id);
    setAgentStatus('greeting');
    setAgentMessage(`${scene.icon || '📦'} ${scene.name}，来了！`);
    setTimeout(() => { setAgentStatus('idle'); setAgentMessage('在线待命'); }, 3000);
  }, [setCurrentScene, setCurrentChannel, setView, loadThinkingMap, loadSceneMessages, channels, setAgentStatus, setAgentMessage]);

  // ═══ 发送工作台聊天（SSE 流） ═══
  const sendWorkbenchChat = useCallback(async (text: string) => {
    if (!text.trim()) return;

    // 🆕 忙锁：前一个请求未完成时拒绝
    if (processingRef.current) {
      setAvatarSpeech('⏳ 上一个任务还在处理，请稍候...');
      setTimeout(() => { if (!processingRef.current) setAvatarSpeech(''); }, 3000);
      return;
    }
    processingRef.current = true;

    setInputVal('');
    setAvatarSpeaking(true);
    setAvatarSpeech('');
    setAgentSpeaking(true);

    try {
      const resp = await fetch('/api/workbench/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: text,
          scene_ids: workbenchScenes.map(s => s.id),
        }),
      });

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'speech:token' || event.type === 'speech:done') {
                setAvatarSpeech(event.text);
                setAgentMessage(event.text);
              } else if (event.type === 'done') {
                setAvatarSpeaking(false);
                setAgentSpeaking(false);
                setAgentStatus('idle');
                processingRef.current = false;
                // 3秒后自动隐藏字幕
                setTimeout(() => { setAvatarSpeech(''); setAgentMessage('在线待命'); }, 3000);
              } else if (event.type?.startsWith('action:')) {
                // Phase 2: 收到操作事件 → 刷新卡片
                if (event.type === 'action:reload') loadScenes();
              }
            } catch { /* skip malformed SSE */ }
          }
        }
      }
    } catch (e) {
      console.error('[workbench] SSE error:', e);
      setAvatarSpeaking(false);
      setAgentSpeaking(false);
      processingRef.current = false;
    }
  }, [workbenchScenes, setAgentSpeaking, setAgentMessage, setAgentStatus]);

  // ═══ 渲染卡片 body — 按 category 分派 ═══
  const renderCardBody = (scene: Scene) => {
    const sc = scene.scene_config || {};
    const cat = scene.category || 'other';

    // ① 天气 / life
    if (cat === 'life') {
      const w = sc.weather;
      if (w && w.temp !== undefined) {
        return (
          <div className="wb-card-body">
            <div className="wb-data-main">
              <div className="wb-data-icon">{scene.icon || '🌤️'}</div>
              <div className="wb-data-info">
                <div className="wb-data-value">{w.temp}°<span className="wb-temp-unit">C</span></div>
                <div className="wb-data-desc">{w.desc} · 体感 {w.feels_like}°</div>
                <div className="wb-data-location">📍 {w.city}</div>
              </div>
            </div>
            <div className="wb-data-details">
              <div className="wb-data-detail"><span className="wb-data-label">💧 湿度</span><span className="wb-data-val">{w.humidity}%</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">🌬 风力</span><span className="wb-data-val">{w.wind}</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">🌡 最高</span><span className="wb-data-val">{w.high}°</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">🌡 最低</span><span className="wb-data-val">{w.low}°</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">🌅 日出</span><span className="wb-data-val">{w.sunrise}</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">🌇 日落</span><span className="wb-data-val">{w.sunset}</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">👁 能见度</span><span className="wb-data-val">{w.visibility}</span></div>
              <div className="wb-data-detail"><span className="wb-data-label">☂ 降水</span><span className="wb-data-val">{w.precipitation}</span></div>
            </div>
          </div>
        );
      }
      return (
        <div className="wb-card-body">
          <div className="wb-data-main">
            <div className="wb-data-icon">{scene.icon || '🌤️'}</div>
            <div className="wb-data-info">
              <div className="wb-data-value">--°<span className="wb-temp-unit">C</span></div>
              <div className="wb-data-desc">等待数据更新</div>
              <div className="wb-data-location">📍 --</div>
            </div>
          </div>
        </div>
      );
    }

    // ② 待办 / todo
    if (cat === 'todo') {
      const items: any[] = sc.todo || [];
      const done = items.filter(i => i.done).length;
      const total = items.length;
      return (
        <div className="wb-card-body">
          <div className="todo-list">
            {items.slice(0, 5).map(i => (
              <div key={i.id} className={`todo-item${i.done ? ' done' : ''}`}>
                <span className="todo-check">{i.done ? '✓' : '○'}</span>
                <span className="todo-text">{i.text}</span>
                {i.priority && <span className={`todo-priority ${i.priority}`}>{i.priority === 'high' ? '高优' : '中优'}</span>}
              </div>
            ))}
          </div>
          <div className="todo-stats">
            <span>完成 <strong>{done}</strong> / {total}</span>
          </div>
        </div>
      );
    }

    // ③ 今日咨询 / news
    if (cat === 'news') {
      const items: any[] = sc.news || [];
      return (
        <div className="wb-card-body">
          <div className="news-list">
            {items.map(i => (
              <div key={i.rank} className="news-item">
                <span className="news-rank">{i.rank}</span>
                <div className="news-content">
                  <div className="news-title">{i.title}</div>
                  <div className="news-meta">{i.source} · {i.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // ④ Web 游戏 / game
    if (cat === 'game') {
      const g = sc.game || {};
      return (
        <div className="wb-card-body">
          <div className="webapp-preview">
            <div className="webapp-thumb" onClick={() => g.url && window.open(g.url, '_blank')}>
              🎮
              <span className="play-overlay">▶ 打开游戏</span>
            </div>
            <div className="webapp-info">
              <span>{g.title}</span>
              <button className="webapp-launch" onClick={() => g.url && window.open(g.url, '_blank')}>开始游戏</button>
            </div>
          </div>
        </div>
      );
    }

    // ⑤ 数据分析 / analysis
    if (cat === 'analysis') {
      const a = sc.analysis || {};
      const charts: any[] = a.charts || [];
      const maxVal = charts.length > 0 ? Math.max(...(charts[0]?.data || [0])) : 1;
      return (
        <div className="wb-card-body">
          <div className="analysis-metrics">
            <div className="analysis-metric"><div className="val">{a.daily_spend}</div><div className="label">今日消费</div></div>
            <div className="analysis-metric"><div className="val">{a.monthly_spend}</div><div className="label">本月消费</div></div>
            <div className="analysis-metric"><div className="val">{a.daily_tokens}</div><div className="label">今日 Token</div></div>
          </div>
          {charts.slice(0, 1).map((c, ci) => (
            <div key={ci} className="chart-bar-row" style={{marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #30363d'}}>
              <div className="chart-label" style={{fontSize: '11px', color: '#8b949e', marginBottom: '4px'}}>{c.label}</div>
              <div className="chart-bars" style={{display: 'flex', gap: '3px', alignItems: 'flex-end', height: '40px'}}>
                {(c.data as number[]).slice(-14).map((v: number, i: number) => (
                  <div key={i} style={{
                    flex: 1, background: c.color || '#58a6ff', borderRadius: '2px',
                    height: `${(v / maxVal) * 100}%`, minHeight: '4px', opacity: 0.7 + (i / 28) * 0.3
                  }} title={`${v.toFixed(1)}`} />
                ))}
              </div>
            </div>
          ))}
        </div>
      );
    }

    // ⑥ Git 提交 / git
    if (cat === 'git') {
      const g = sc.git || {};
      const y = g.yesterday || {};
      const t = g.today || {};
      return (
        <div className="wb-card-body">
          <div className="git-summary" style={{display: 'flex', gap: '16px', marginBottom: '12px'}}>
            <div className="git-day" style={{flex: 1, textAlign: 'center', padding: '8px', background: '#0d1117', borderRadius: '6px'}}>
              <div style={{fontSize: '24px', fontWeight: 600, color: '#58a6ff'}}>{y.count || 0}</div>
              <div style={{fontSize: '11px', color: '#8b949e'}}>昨日提交</div>
            </div>
            <div className="git-day" style={{flex: 1, textAlign: 'center', padding: '8px', background: '#0d1117', borderRadius: '6px'}}>
              <div style={{fontSize: '24px', fontWeight: 600, color: t.commits === 0 ? '#484f58' : '#3fb950'}}>{t.commits || 0}</div>
              <div style={{fontSize: '11px', color: '#8b949e'}}>今日提交</div>
            </div>
          </div>
          {(y.details || []).slice(0, 5).map((d: string, i: number) => (
            <div key={i} style={{fontSize: '11px', color: '#8b949e', padding: '2px 0', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
              {d}
            </div>
          ))}
        </div>
      );
    }

// 7語解布 / stock —平K目要洗图
    if (cat === 'stock') {
      const s = sc.stock || {};
      const isUp = (s.change ?? 0) >= 0;
      const kline = s.kline || [];
      // 浸渓最近日K庛消城图片（纯SVG，无夗外号
      let chartSvg = null;
      if (kline.length >= 2) {
        const w = 260, h = 80, pad = 4;
        const prices = kline.map(d => parseFloat(d.close));
        const minP = Math.min(...prices);
        const maxP = Math.max(...prices);
        const range = maxP - minP || 1;
        const xStep = (w - pad * 2) / (prices.length - 1);
        const toY = (v: number) => h - pad - ((v - minP) / range) * (h - pad * 2);
        const pts = prices.map((v, i) => `${pad + i * xStep},${toY(v)}`).join(' ');
        const lastP = prices[prices.length - 1];
        const firstP = prices[0];
        const trendUp = lastP >= firstP;
        const strokeColor = trendUp ? '#3fb950' : '#f85149';
        const fillColor = trendUp ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)';
        const fillPts = prices.map((v, i) => `${pad + i * xStep},${toY(v)}`).join(' ');
        const fillPath = `M${pad},${h - pad} L${fillPts} L${pad + (prices.length - 1) * xStep},${h - pad} Z`;
        chartSvg = (
          <svg width={w} height={h} style={{display:'block',margin:'8px auto 4px'}}>
            <path d={fillPath} fill={fillColor} />
            <polyline points={pts} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <text x={pad + (prices.length - 1) * xStep - 4} y={toY(lastP) - 6} textAnchor="end" fill={strokeColor} fontSize="11" fontWeight="600">
              {lastP.toFixed(2)}
            </text>
            {kline.length >= 3 && (
              <>
                <text x={pad} y={h - 2} fill="#484f58" fontSize="9">{kline[0].date.slice(5)}</text>
                <text x={w - pad} y={h - 2} textAnchor="end" fill="#484f58" fontSize="9">{kline[kline.length-1].date.slice(5)}</text>
              </>
            )}
          </svg>
        );
      }
      return (
        <div className="wb-card-body">
          <div className="wb-data-main" style={{marginBottom: '8px'}}>
            <div className="wb-data-icon" style={{fontSize: '32px'}}>{scene.icon || '🎈'}</div>
            <div className="wb-data-info">
              <div className="wb-data-value" style={{fontSize: '30px'}}>{s.price}<span className="wb-temp-unit" style={{fontSize: '16px'}}>{s.currency || ''}</span></div>
              <div className="wb-data-desc" style={{color: isUp ? '#3fb950' : '#f85149'}}>
                {isUp ? '▲' : '▔'} {s.change} ({s.change_pct})
              </div>
              <div className="wb-data-location">{s.name} . {s.code}</div>
            </div>
          </div>
          {chartSvg}
          <div className="wb-data-details">
            <div className="wb-data-detail"><span className="wb-data-label">最高</span><span className="wb-data-val">{s.high}</span></div>
            <div className="wb-data-detail"><span className="wb-data-label">最低</span><span className="wb-data-val">{s.low}</span></div>
            <div className="wb-data-detail"><span className="wb-data-label">成交量</span><span className="wb-data-val">{s.volume}</span></div>
            <div className="wb-data-detail"><span className="wb-data-label">市数</span><span className="wb-data-val">{s.market_cap}</span></div>
          </div>
        </div>
      );
    }

    // ⑧ 618热销 / shopping
    if (cat === 'shopping') {
      const items: any[] = sc.shopping || [];
      return (
        <div className="wb-card-body">
          {items.map(i => (
            <div key={i.rank} className="deal-item" style={{display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 0', borderBottom: '1px solid #21262d'}}>
              <span style={{fontSize: '12px', color: '#484f58', minWidth: '16px'}}>{i.rank}</span>
              <div style={{flex: 1, minWidth: 0}}>
                <div style={{fontSize: '13px', color: '#c9d1d9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{i.name}</div>
                <div style={{fontSize: '11px', color: '#8b949e'}}>{i.store}</div>
              </div>
              <div style={{textAlign: 'right'}}>
                <div style={{fontSize: '15px', fontWeight: 600, color: '#f85149'}}>{i.price}</div>
                <div style={{fontSize: '11px', color: '#484f58'}}><s>{i.original}</s> {i.discount}</div>
              </div>
            </div>
          ))}
        </div>
      );
    }

    // fallback → 占位卡片
    return (
      <div className="wb-card-body">
        <div className="wb-card-placeholder">
          <div className="wb-placeholder-icon">{scene.icon || '📦'}</div>
          <div className="wb-placeholder-title">坐山客正在准备中…</div>
          <div className="wb-placeholder-hint">跟我说你想要什么</div>
        </div>
      </div>
    );
  };

  // ═══ 渲染卡片 footer ═══
  const renderCardFooter = (scene: Scene) => {
    const cat = scene.category || 'other';
    if (cat === 'life') {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          📡 完整预报 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    if (cat === 'game') {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          🎮 进入游戏 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    if (cat === 'news') {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          📰 查看全部资讯 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    if (cat === 'analysis') {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          📊 详细报表 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    if (cat === 'todo') {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          ✅ 管理待办 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    if (scene.description) {
      return (
        <div className="wb-card-footer" onClick={() => handleEnterScene(scene)}>
          进入场景 <span className="wb-footer-arrow">→</span>
        </div>
      );
    }
    return (
      <div className="wb-card-footer wb-card-footer-empty">
        暂无产出
      </div>
    );
  };

  // ═══ 卡片友好标题 ═══
  const getCardTitle = (scene: Scene): string => {
    if (scene.category === 'life') return '今日天气';
    return scene.name;
  };

  return (
    <div className="workbench-view">
      {/* ═══ Greeting ═══ */}
      <div className="wb-greeting">
        <div className="wb-greeting-left">
          <h1>{greeting}</h1>
          <div className="wb-greeting-sub">{subtitle}</div>
        </div>
        <div className="wb-greeting-right">
          <span className="wb-clock">{clock}</span>
          <button className="wb-quick-btn">➕ 新建场景</button>
          <button className="wb-quick-btn wb-primary" onClick={() => setView('chat')}>进入坐山客空间 →</button>
        </div>
      </div>

      {/* ═══ Avatar 对话字幕（浮动覆盖层，不挤压卡片） ═══ */}
      <div className="wb-subtitle-wrapper">
        <div className={`wb-subtitle-bar${avatarSpeaking || avatarSpeech ? '' : ' wb-subtitle-hidden'}`}>
          <div className="wb-subtitle-text">{avatarSpeech || '\u00A0'}</div>
          <div className="wb-subtitle-name">— 坐山客 —</div>
        </div>
      </div>

      {/* ═══ Card Grid ═══ */}
      <div className="wb-card-grid">
        {loadingScenes ? (
          <div className="wb-empty"><div className="wb-empty-text">加载中...</div></div>
        ) : workbenchScenes.length === 0 ? (
          <div className="wb-empty">
            <div className="wb-empty-icon">🏠</div>
            <div className="wb-empty-text">工作台还是空的</div>
            <div className="wb-empty-desc">去场景广场逛逛，把喜欢的场景 ⭐ 钉到工作台</div>
          </div>
        ) : workbenchScenes.map(s => {
          const sc = s.scene_config || {};
          const weather = sc.weather;
          const stock = sc.stock;
          const cat = s.category || 'other';
          return (
          <div key={s.id} className="wb-card">
            {/* header */}
            <div className="wb-card-header" onClick={() => handleEnterScene(s)}>
              <span className="wb-card-icon">{s.icon || '📦'}</span>
              <span className="wb-card-name">{getCardTitle(s)}</span>
              <div className="wb-card-actions">
                {weather ? (
                  <>
                    <button className="wb-header-btn" title="切换城市">📍 {weather.city}</button>
                    <button className="wb-header-btn" title="刷新" onClick={e => { e.stopPropagation(); loadScenes(); }}>🔄</button>
                  </>
                ) : null}
                {cat === 'stock' && stock ? (
                  <button className="wb-header-btn" title="刷新股价" onClick={async e => {
                    e.stopPropagation();
                    try {
                      await fetch(`/api/scenes/${s.id}/refresh-stock`, { method: 'POST' });
                      loadScenes();
                    } catch {}
                  }}>🔄</button>
                ) : null}
              </div>
            </div>
            {/* body */}
            {renderCardBody(s)}
            {/* footer */}
            {renderCardFooter(s)}
          </div>
          );
        })}
      </div>

      {/* ═══ Floating Chat Bar ═══ */}
      <div className={`wb-float-bar${barExpanded ? '' : ' collapsed'}`}>
        <div className="wb-float-bar-toggle" onClick={() => setBarExpanded(!barExpanded)}>
          {barExpanded ? '▲' : '▼'}
        </div>
        <input className="wb-float-bar-input" type="text"
          placeholder="💬 跟坐山客说你想看什么..."
          value={inputVal} onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && inputVal.trim()) sendWorkbenchChat(inputVal); }} />
        <button className="wb-float-bar-send" onClick={() => { if (inputVal.trim()) sendWorkbenchChat(inputVal); }}>发送</button>
        <span className="wb-float-bar-hint">⌘K 唤起</span>
      </div>
    </div>
  );
}

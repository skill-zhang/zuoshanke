import { useState, useEffect, useRef, useCallback } from 'react';
import Plot from 'react-plotly.js';

// ═══ Types ═══

interface Dataset {
  id: string;
  filename: string;
  columns: string[];
  row_count: number;
  uploaded_at: string;
}

interface ForecastResult {
  dates: string[];
  historical: number[];
  predicted: number[];
  upper_bound: number[];
  lower_bound: number[];
  metrics: {
    mae: number;
    rmse: number;
    mape: number;
  };
}

interface AnomalyResult {
  dates: string[];
  values: number[];
  anomaly_indices: number[];
  anomaly_scores?: number[];
}

// ═══ API helpers ═══

const api = {
  async listDatasets(): Promise<Dataset[]> {
    const res = await fetch('/api/ml/datasets');
    if (!res.ok) throw new Error('获取数据集列表失败');
    return res.json();
  },

  async uploadDataset(file: File): Promise<Dataset> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/ml/datasets/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error('上传失败');
    return res.json();
  },

  async getDatasetPreview(id: string, limit = 50): Promise<Record<string, any>[]> {
    const res = await fetch(`/api/ml/datasets/${id}/preview?limit=${limit}`);
    if (!res.ok) throw new Error('获取预览失败');
    return res.json();
  },

  async runForecast(params: {
    dataset_id: string;
    date_column: string;
    value_column: string;
    algorithm: string;
    steps: number;
  }): Promise<ForecastResult> {
    const res = await fetch('/api/ml/forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('预测失败');
    return res.json();
  },

  async runAnomalyDetection(params: {
    dataset_id: string;
    value_column: string;
    algorithm: string;
    contamination: number;
  }): Promise<AnomalyResult> {
    const res = await fetch('/api/ml/anomaly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error('异常检测失败');
    return res.json();
  },
};

// ═══ Components ═══

/** 数据集管理面板 */
function DatasetManager({
  datasets,
  selectedId,
  onSelect,
  onUpload,
  onRefresh,
  previewData,
  previewLoading,
}: {
  datasets: Dataset[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUpload: (file: File) => void;
  onRefresh: () => void;
  previewData: Record<string, any>[] | null;
  previewLoading: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selected = datasets.find(d => d.id === selectedId) || null;

  return (
    <div className="ml-section">
      <div className="ml-section-header">
        <span className="ml-section-icon">📊</span>
        <span>数据集管理</span>
        <div className="ml-section-actions">
          <button className="btn btn-sm" onClick={onRefresh}>🔄 刷新</button>
          <button className="btn btn-sm btn-primary" onClick={() => fileInputRef.current?.click()}>
            📤 上传 Excel
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = '';
            }}
          />
        </div>
      </div>

      {/* 数据集列表 */}
      <div className="ml-dataset-list">
        {datasets.length === 0 ? (
          <div className="ml-empty">暂无数据集，请上传 Excel 文件</div>
        ) : (
          datasets.map(ds => (
            <div
              key={ds.id}
              className={`ml-dataset-item${selectedId === ds.id ? ' active' : ''}`}
              onClick={() => onSelect(ds.id)}
            >
              <div className="ml-dataset-name">{ds.filename}</div>
              <div className="ml-dataset-meta">
                <span>{ds.columns.length} 列</span>
                <span>·</span>
                <span>{ds.row_count} 行</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 预览表格 */}
      {selected && (
        <div className="ml-preview">
          <div className="ml-preview-title">
            📋 预览：{selected.filename}
            <span className="ml-preview-meta">
              {selected.columns.length} 列 · {selected.row_count} 行
            </span>
          </div>
          {previewLoading ? (
            <div className="ml-loading">加载中...</div>
          ) : previewData && previewData.length > 0 ? (
            <div className="ml-table-wrapper">
              <table className="ml-table">
                <thead>
                  <tr>
                    {Object.keys(previewData[0]).map(col => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewData.map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((val: any, j) => (
                        <td key={j}>{val !== null && val !== undefined ? String(val) : ''}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="ml-empty">暂无预览数据</div>
          )}
        </div>
      )}
    </div>
  );
}

/** 时序预测面板 */
function ForecastPanel({
  datasets,
  selectedDatasetId,
}: {
  datasets: Dataset[];
  selectedDatasetId: string | null;
}) {
  const selectedDataset = datasets.find(d => d.id === selectedDatasetId);
  const columns = selectedDataset?.columns || [];

  const [dateColumn, setDateColumn] = useState('');
  const [valueColumn, setValueColumn] = useState('');
  const [algorithm, setAlgorithm] = useState('Prophet');
  const [steps, setSteps] = useState(30);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [error, setError] = useState('');

  // Reset columns when dataset changes
  useEffect(() => {
    if (columns.length > 0) {
      setDateColumn(columns[0]);
      setValueColumn(columns[columns.length > 1 ? 1 : 0]);
    } else {
      setDateColumn('');
      setValueColumn('');
    }
    setResult(null);
    setError('');
  }, [selectedDatasetId]);

  const handleRun = async () => {
    if (!selectedDatasetId || !dateColumn || !valueColumn) return;
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const res = await api.runForecast({
        dataset_id: selectedDatasetId,
        date_column: dateColumn,
        value_column: valueColumn,
        algorithm,
        steps,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || '运行失败');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="ml-section">
      <div className="ml-section-header">
        <span className="ml-section-icon">📈</span>
        <span>时序预测</span>
      </div>

      <div className="ml-form-grid">
        <div className="ml-form-group">
          <label className="ml-label">日期列</label>
          <select className="ml-select" value={dateColumn} onChange={e => setDateColumn(e.target.value)} disabled={!selectedDatasetId}>
            {columns.map(col => <option key={col} value={col}>{col}</option>)}
            {columns.length === 0 && <option value="">请先选择数据集</option>}
          </select>
        </div>
        <div className="ml-form-group">
          <label className="ml-label">值列</label>
          <select className="ml-select" value={valueColumn} onChange={e => setValueColumn(e.target.value)} disabled={!selectedDatasetId}>
            {columns.map(col => <option key={col} value={col}>{col}</option>)}
            {columns.length === 0 && <option value="">请先选择数据集</option>}
          </select>
        </div>
        <div className="ml-form-group">
          <label className="ml-label">算法</label>
          <select className="ml-select" value={algorithm} onChange={e => setAlgorithm(e.target.value)}>
            <option value="Prophet">Prophet</option>
            <option value="ARIMA">ARIMA</option>
            <option value="LSTM">LSTM</option>
          </select>
        </div>
        <div className="ml-form-group">
          <label className="ml-label">预测步数</label>
          <input className="ml-input" type="number" min={1} max={365} value={steps} onChange={e => setSteps(Number(e.target.value))} />
        </div>
      </div>

      <div className="ml-form-actions">
        <button
          className="btn btn-primary"
          onClick={handleRun}
          disabled={running || !selectedDatasetId || !dateColumn || !valueColumn}
        >
          {running ? '⏳ 运行中...' : '▶ 运行预测'}
        </button>
      </div>

      {error && <div className="ml-error">{error}</div>}

      {result && (
        <div className="ml-result">
          {/* 评估指标 */}
          <div className="ml-metrics">
            <div className="ml-metric-card">
              <span className="ml-metric-label">MAE</span>
              <span className="ml-metric-value">{result.metrics.mae.toFixed(4)}</span>
            </div>
            <div className="ml-metric-card">
              <span className="ml-metric-label">RMSE</span>
              <span className="ml-metric-value">{result.metrics.rmse.toFixed(4)}</span>
            </div>
            <div className="ml-metric-card">
              <span className="ml-metric-label">MAPE</span>
              <span className="ml-metric-value">{result.metrics.mape.toFixed(2)}%</span>
            </div>
          </div>

          {/* 预测图表 */}
          <div className="ml-chart">
            <Plot
              data={[
                {
                  x: result.dates.slice(0, result.historical.length),
                  y: result.historical,
                  type: 'scatter',
                  mode: 'lines',
                  name: '历史数据',
                  line: { color: '#58a6ff', width: 2 },
                },
                {
                  x: result.dates.slice(result.historical.length),
                  y: result.predicted,
                  type: 'scatter',
                  mode: 'lines',
                  name: '预测值',
                  line: { color: '#f0883e', width: 2 },
                },
                {
                  x: [...result.dates.slice(result.historical.length), ...result.dates.slice(result.historical.length).reverse()],
                  y: [...result.upper_bound, ...result.lower_bound.slice().reverse()],
                  fill: 'toself',
                  type: 'scatter',
                  mode: 'none',
                  name: '置信区间',
                  fillcolor: 'rgba(240, 136, 62, 0.15)',
                  line: { color: 'rgba(240, 136, 62, 0)' },
                  showlegend: true,
                },
              ]}
              layout={{
                title: { text: '时序预测结果', font: { color: '#c9d1d9' } },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#8b949e', size: 12 },
                xaxis: {
                  gridcolor: '#30363d',
                  zerolinecolor: '#30363d',
                  title: { text: '日期', font: { color: '#8b949e' } },
                },
                yaxis: {
                  gridcolor: '#30363d',
                  zerolinecolor: '#30363d',
                  title: { text: '值', font: { color: '#8b949e' } },
                },
                legend: {
                  font: { color: '#c9d1d9' },
                  bgcolor: 'rgba(22,27,34,0.8)',
                  bordercolor: '#30363d',
                },
                margin: { t: 40, r: 20, b: 50, l: 60 },
                autosize: true,
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%', height: 400 }}
              useResizeHandler
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** 异常检测面板 */
function AnomalyPanel({
  datasets,
  selectedDatasetId,
}: {
  datasets: Dataset[];
  selectedDatasetId: string | null;
}) {
  const selectedDataset = datasets.find(d => d.id === selectedDatasetId);
  const columns = selectedDataset?.columns || [];

  const [valueColumn, setValueColumn] = useState('');
  const [algorithm, setAlgorithm] = useState('Isolation Forest');
  const [contamination, setContamination] = useState(0.1);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AnomalyResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (columns.length > 0) {
      setValueColumn(columns[0]);
    } else {
      setValueColumn('');
    }
    setResult(null);
    setError('');
  }, [selectedDatasetId]);

  const handleRun = async () => {
    if (!selectedDatasetId || !valueColumn) return;
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const res = await api.runAnomalyDetection({
        dataset_id: selectedDatasetId,
        value_column: valueColumn,
        algorithm,
        contamination,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || '运行失败');
    } finally {
      setRunning(false);
    }
  };

  const anomalySet = new Set(result?.anomaly_indices || []);
  const normalIndices: number[] = [];
  const anomalyIndices: number[] = [];
  (result?.dates || []).forEach((_, i) => {
    if (anomalySet.has(i)) anomalyIndices.push(i);
    else normalIndices.push(i);
  });

  return (
    <div className="ml-section">
      <div className="ml-section-header">
        <span className="ml-section-icon">🔍</span>
        <span>异常检测</span>
      </div>

      <div className="ml-form-grid">
        <div className="ml-form-group">
          <label className="ml-label">值列</label>
          <select className="ml-select" value={valueColumn} onChange={e => setValueColumn(e.target.value)} disabled={!selectedDatasetId}>
            {columns.map(col => <option key={col} value={col}>{col}</option>)}
            {columns.length === 0 && <option value="">请先选择数据集</option>}
          </select>
        </div>
        <div className="ml-form-group">
          <label className="ml-label">算法</label>
          <select className="ml-select" value={algorithm} onChange={e => setAlgorithm(e.target.value)}>
            <option value="Isolation Forest">Isolation Forest</option>
            <option value="LOF">LOF</option>
            <option value="3-Sigma">3-Sigma</option>
          </select>
        </div>
        <div className="ml-form-group">
          <label className="ml-label">异常比例</label>
          <div className="ml-range-group">
            <input
              className="ml-range"
              type="range"
              min={0.01}
              max={0.5}
              step={0.01}
              value={contamination}
              onChange={e => setContamination(Number(e.target.value))}
            />
            <span className="ml-range-value">{(contamination * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>

      <div className="ml-form-actions">
        <button
          className="btn btn-primary"
          onClick={handleRun}
          disabled={running || !selectedDatasetId || !valueColumn}
        >
          {running ? '⏳ 运行中...' : '▶ 运行检测'}
        </button>
      </div>

      {error && <div className="ml-error">{error}</div>}

      {result && (
        <div className="ml-result">
          <div className="ml-metrics">
            <div className="ml-metric-card">
              <span className="ml-metric-label">检测异常点</span>
              <span className="ml-metric-value">{result.anomaly_indices.length} / {result.dates.length}</span>
            </div>
          </div>

          <div className="ml-chart">
            <Plot
              data={[
                {
                  x: normalIndices.map(i => result.dates[i]),
                  y: normalIndices.map(i => result.values[i]),
                  type: 'scatter',
                  mode: 'markers',
                  name: '正常值',
                  marker: { color: '#58a6ff', size: 6, opacity: 0.7 },
                },
                {
                  x: anomalyIndices.map(i => result.dates[i]),
                  y: anomalyIndices.map(i => result.values[i]),
                  type: 'scatter',
                  mode: 'markers',
                  name: '异常点',
                  marker: { color: '#f85149', size: 10, symbol: 'x', line: { color: '#f85149', width: 2 } },
                },
              ]}
              layout={{
                title: { text: '异常检测结果', font: { color: '#c9d1d9' } },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#8b949e', size: 12 },
                xaxis: {
                  gridcolor: '#30363d',
                  zerolinecolor: '#30363d',
                  title: { text: '索引 / 日期', font: { color: '#8b949e' } },
                },
                yaxis: {
                  gridcolor: '#30363d',
                  zerolinecolor: '#30363d',
                  title: { text: '值', font: { color: '#8b949e' } },
                },
                legend: {
                  font: { color: '#c9d1d9' },
                  bgcolor: 'rgba(22,27,34,0.8)',
                  bordercolor: '#30363d',
                },
                margin: { t: 40, r: 20, b: 50, l: 60 },
                autosize: true,
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%', height: 400 }}
              useResizeHandler
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ═══ Main View ═══

export function MLExperimentView() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<Record<string, any>[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDatasets = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listDatasets();
      setDatasets(data);
      setError('');
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  // Load preview when dataset selected
  useEffect(() => {
    if (!selectedDatasetId) {
      setPreviewData(null);
      return;
    }
    setPreviewLoading(true);
    api.getDatasetPreview(selectedDatasetId)
      .then(data => setPreviewData(data))
      .catch(() => setPreviewData(null))
      .finally(() => setPreviewLoading(false));
  }, [selectedDatasetId]);

  const handleUpload = async (file: File) => {
    try {
      await api.uploadDataset(file);
      await loadDatasets();
    } catch (e: any) {
      setError(e.message || '上传失败');
    }
  };

  return (
    <div className="ml-view">
      <div className="ml-view-header">
        <span className="ml-view-icon">🧪</span>
        <span className="ml-view-title">ML 算法实验</span>
        <span className="ml-view-badge">实验性</span>
      </div>

      {error && <div className="ml-error ml-error-banner">{error}</div>}

      {loading ? (
        <div className="ml-loading">加载中...</div>
      ) : (
        <div className="ml-grid">
          <DatasetManager
            datasets={datasets}
            selectedId={selectedDatasetId}
            onSelect={setSelectedDatasetId}
            onUpload={handleUpload}
            onRefresh={loadDatasets}
            previewData={previewData}
            previewLoading={previewLoading}
          />
          <ForecastPanel
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
          />
          <AnomalyPanel
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
          />
        </div>
      )}
    </div>
  );
}

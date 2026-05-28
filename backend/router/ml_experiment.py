"""ML 算法引擎 API — 数据集管理、时序预测、异常检测"""

import io
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

# ── 上传目录 ──────────────────────────────────────────────
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── 内存数据存储 ──────────────────────────────────────────
_datasets: dict[str, dict] = {}  # dataset_id -> {info}

router = APIRouter(tags=["ML 算法引擎"])


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def _parse_excel(file_path: str) -> pd.DataFrame:
    """解析 Excel 文件为 DataFrame"""
    ext = Path(file_path).suffix.lower()
    if ext == ".xlsx":
        df = pd.read_excel(file_path, engine="openpyxl")
    elif ext == ".xls":
        df = pd.read_excel(file_path, engine="xlrd")
    else:
        raise HTTPException(400, f"不支持的文件格式: {ext}，仅支持 .xlsx 和 .xls")
    return df


def _serialize_df(df: pd.DataFrame) -> dict:
    """将 DataFrame 序列化为可 JSON 序列化的字典"""
    # 处理 NaN / NaT / 非 JSON 原生类型
    preview = df.head(5).copy()
    # 将 Timestamp 转为字符串
    for col in preview.select_dtypes(include=["datetime64[ns]", "datetime64"]).columns:
        preview[col] = preview[col].astype(str)
    # 将 NaN 转为 None
    preview = preview.where(pd.notna(preview), None)
    return {
        "columns": list(df.columns),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "row_count": len(df),
        "preview": json.loads(preview.to_json(orient="records", force_ascii=False)),
    }


def _ensure_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """确保列是数值类型，否则尝试转换"""
    if column not in df.columns:
        raise HTTPException(400, f"列 '{column}' 不存在于数据集中")
    col = df[column]
    if not pd.api.types.is_numeric_dtype(col):
        try:
            col = pd.to_numeric(col, errors="coerce")
        except Exception:
            raise HTTPException(400, f"列 '{column}' 无法转换为数值类型")
    if col.isna().all():
        raise HTTPException(400, f"列 '{column}' 全部为空值")
    return col


# ═══════════════════════════════════════════════════════════
# 1. POST /api/ml/upload — 上传 Excel 数据集
# ═══════════════════════════════════════════════════════════

@router.post("/api/ml/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """上传 Excel 文件作为数据集

    支持 .xlsx / .xls，解析后返回列名、行数、前 5 行预览。
    """
    if not file.filename:
        raise HTTPException(400, "文件名为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(400, f"不支持的文件格式: {ext}，仅支持 .xlsx 和 .xls")

    # 保存文件
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / unique_name
    try:
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "文件过大，最大支持 50MB")
        save_path.write_bytes(content)
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[ml/upload] 保存文件失败: {e}")
        raise HTTPException(500, f"文件保存失败: {e}")

    # 解析 Excel
    try:
        df = _parse_excel(str(save_path))
    except HTTPException:
        raise
    except Exception as e:
        # 删除已保存的文件
        save_path.unlink(missing_ok=True)
        _log.error(f"[ml/upload] 解析 Excel 失败: {e}")
        raise HTTPException(400, f"Excel 解析失败: {e}")

    # 存入内存
    dataset_id = uuid.uuid4().hex
    _datasets[dataset_id] = {
        "id": dataset_id,
        "filename": file.filename,
        "file_path": str(save_path),
        "uploaded_at": datetime.now().isoformat(),
        "df": df,
        "info": _serialize_df(df),
    }

    return JSONResponse({
        "dataset_id": dataset_id,
        "filename": file.filename,
        "info": _datasets[dataset_id]["info"],
    })


# ═══════════════════════════════════════════════════════════
# 2. POST /api/ml/datasets — 列出已上传的数据集
# ═══════════════════════════════════════════════════════════

@router.post("/api/ml/datasets")
async def list_datasets():
    """列出所有已上传的数据集"""
    result = []
    for ds_id, ds in _datasets.items():
        result.append({
            "dataset_id": ds_id,
            "filename": ds["filename"],
            "uploaded_at": ds["uploaded_at"],
            "row_count": ds["info"]["row_count"],
            "columns": ds["info"]["columns"],
        })
    return JSONResponse({"datasets": result, "total": len(result)})


# ═══════════════════════════════════════════════════════════
# 3. POST /api/ml/predict — 时序预测
# ═══════════════════════════════════════════════════════════

@router.post("/api/ml/predict")
async def time_series_predict(
    dataset_id: str = Form(...),
    date_column: str = Form(...),
    value_column: str = Form(...),
    algorithm: str = Form("prophet"),
    forecast_periods: int = Form(30),
):
    """时序预测

    使用 Prophet 算法对指定列进行时序预测，返回预测结果和评估指标。
    """
    if dataset_id not in _datasets:
        raise HTTPException(404, f"数据集 '{dataset_id}' 不存在")

    ds = _datasets[dataset_id]
    df = ds["df"].copy()

    # 校验列
    if date_column not in df.columns:
        raise HTTPException(400, f"日期列 '{date_column}' 不存在")
    if value_column not in df.columns:
        raise HTTPException(400, f"值列 '{value_column}' 不存在")

    # 解析日期列
    try:
        df[date_column] = pd.to_datetime(df[date_column])
    except Exception as e:
        raise HTTPException(400, f"日期列 '{date_column}' 解析失败: {e}")

    # 确保值列为数值
    df[value_column] = _ensure_numeric(df, value_column)

    # 按日期排序
    df = df.sort_values(date_column).dropna(subset=[value_column])
    if len(df) < 2:
        raise HTTPException(400, "数据点不足，至少需要 2 个有效数据点")

    # 只支持 prophet 算法（其他算法占位）
    if algorithm.lower() not in ("prophet",):
        raise HTTPException(400, f"不支持的算法: {algorithm}，当前仅支持 prophet")

    from prophet import Prophet

    # 准备 Prophet 数据格式
    prophet_df = df[[date_column, value_column]].rename(
        columns={date_column: "ds", value_column: "y"}
    )

    # 训练 Prophet 模型
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.80,
    )
    model.fit(prophet_df)

    # 预测
    future = model.make_future_dataframe(periods=forecast_periods)
    forecast = model.predict(future)

    # 提取预测结果
    forecast_result = forecast.tail(forecast_periods)
    predictions = []
    for _, row in forecast_result.iterrows():
        predictions.append({
            "date": row["ds"].strftime("%Y-%m-%d"),
            "yhat": round(float(row["yhat"]), 4),
            "yhat_lower": round(float(row["yhat_lower"]), 4),
            "yhat_upper": round(float(row["yhat_upper"]), 4),
        })

    # 评估指标（在历史数据上计算）
    fitted = forecast.iloc[:len(prophet_df)]
    y_true = prophet_df["y"].values
    y_pred = fitted["yhat"].values

    # 过滤 NaN
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true_f = y_true[mask]
    y_pred_f = y_pred[mask]

    if len(y_true_f) == 0:
        raise HTTPException(400, "无法计算评估指标：所有预测值均为空")

    mae = float(np.mean(np.abs(y_true_f - y_pred_f)))
    rmse = float(np.sqrt(np.mean((y_true_f - y_pred_f) ** 2)))
    # MAPE：避免除零
    nonzero_mask = y_true_f != 0
    if nonzero_mask.sum() > 0:
        mape = float(np.mean(np.abs((y_true_f[nonzero_mask] - y_pred_f[nonzero_mask]) / y_true_f[nonzero_mask])) * 100)
    else:
        mape = None

    # 图表数据（全部历史 + 预测）
    chart_data = []
    for _, row in forecast.iterrows():
        chart_data.append({
            "date": row["ds"].strftime("%Y-%m-%d"),
            "actual": round(float(row.get("y", np.nan)), 4) if "y" in row and pd.notna(row.get("y")) else None,
            "predicted": round(float(row["yhat"]), 4),
            "yhat_lower": round(float(row["yhat_lower"]), 4),
            "yhat_upper": round(float(row["yhat_upper"]), 4),
        })

    return JSONResponse({
        "algorithm": algorithm,
        "forecast_periods": forecast_periods,
        "predictions": predictions,
        "metrics": {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 4) if mape is not None else None,
        },
        "chart_data": chart_data,
    })


# ═══════════════════════════════════════════════════════════
# 4. POST /api/ml/detect — 异常检测
# ═══════════════════════════════════════════════════════════

@router.post("/api/ml/detect")
async def anomaly_detect(
    dataset_id: str = Form(...),
    value_column: str = Form(...),
    algorithm: str = Form("isolation_forest"),
    contamination: float = Form(0.1),
):
    """异常检测

    支持算法：isolation_forest / lof / 3sigma
    """
    if dataset_id not in _datasets:
        raise HTTPException(404, f"数据集 '{dataset_id}' 不存在")

    ds = _datasets[dataset_id]
    df = ds["df"].copy()

    if value_column not in df.columns:
        raise HTTPException(400, f"值列 '{value_column}' 不存在")

    values = _ensure_numeric(df, value_column)

    # 去除 NaN
    valid_mask = values.notna()
    valid_values = values[valid_mask].values.reshape(-1, 1)
    original_indices = np.where(valid_mask)[0]

    if len(valid_values) < 3:
        raise HTTPException(400, "有效数据点不足，至少需要 3 个")

    algorithm = algorithm.lower()

    if algorithm == "isolation_forest":
        from sklearn.ensemble import IsolationForest
        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
        )
        preds = model.fit_predict(valid_values)
        # IsolationForest: 1=正常, -1=异常
        anomaly_flags = preds == -1

    elif algorithm == "lof":
        from sklearn.neighbors import LocalOutlierFactor
        model = LocalOutlierFactor(
            contamination=contamination,
            n_neighbors=min(20, max(2, len(valid_values) // 2)),
        )
        preds = model.fit_predict(valid_values)
        # LOF: 1=正常, -1=异常
        anomaly_flags = preds == -1

    elif algorithm == "3sigma":
        mean = np.mean(valid_values)
        std = np.std(valid_values)
        if std == 0:
            raise HTTPException(400, "数据标准差为 0，无法使用 3-sigma 检测")
        threshold = 3 * std
        anomaly_flags = np.abs(valid_values.flatten() - mean) > threshold

    else:
        raise HTTPException(400, f"不支持的算法: {algorithm}，支持: isolation_forest / lof / 3sigma")

    # 构建结果
    anomaly_points = []
    normal_points = []
    for i, idx in enumerate(original_indices):
        val = float(valid_values[i][0])
        point = {
            "index": int(idx),
            "value": round(val, 4),
        }
        # 如果有日期列，尝试加入日期信息
        for col in df.columns:
            if "date" in col.lower() or "time" in col.lower():
                try:
                    dt_val = pd.to_datetime(df.iloc[idx][col])
                    point["date"] = dt_val.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    point["date"] = str(df.iloc[idx][col])
                break

        if anomaly_flags[i]:
            anomaly_points.append(point)
        else:
            normal_points.append(point)

    anomaly_ratio = round(len(anomaly_points) / len(valid_values), 4)

    return JSONResponse({
        "algorithm": algorithm,
        "contamination": contamination,
        "anomaly_count": len(anomaly_points),
        "normal_count": len(normal_points),
        "anomaly_ratio": anomaly_ratio,
        "anomaly_points": anomaly_points,
        "normal_points": normal_points[:100],  # 限制返回数量
    })


# ═══════════════════════════════════════════════════════════
# 5. GET /api/ml/datasets/{id}/data — 获取数据集详情
# ═══════════════════════════════════════════════════════════

@router.get("/api/ml/datasets/{dataset_id}/data")
async def get_dataset_data(dataset_id: str):
    """获取数据集详情，包括完整数据"""
    if dataset_id not in _datasets:
        raise HTTPException(404, f"数据集 '{dataset_id}' 不存在")

    ds = _datasets[dataset_id]
    df = ds["df"].copy()

    # 序列化所有数据
    data_records = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                record[col] = val.isoformat()
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = float(val)
            elif isinstance(val, np.bool_):
                record[col] = bool(val)
            else:
                record[col] = val
        data_records.append(record)

    return JSONResponse({
        "dataset_id": dataset_id,
        "filename": ds["filename"],
        "uploaded_at": ds["uploaded_at"],
        "row_count": len(data_records),
        "columns": list(df.columns),
        "data": data_records,
    })

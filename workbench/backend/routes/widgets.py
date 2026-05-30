"""Widget 配置 CRUD"""
import json
import urllib.request
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import WidgetConfig

router = APIRouter(prefix="/api/widgets", tags=["widgets"])

# 内建 widget 类型列表（与前端 widgetRegistry 对齐）
BUILTIN_WIDGET_TYPES = [
    {"type": "hello", "name": "你好世界", "icon": "👋"},
    {"type": "clock", "name": "数字时钟", "icon": "🕐"},
    {"type": "weather", "name": "天气预报", "icon": "🌤️"},
    {"type": "todo", "name": "待办事项", "icon": "✅"},
    {"type": "news", "name": "资讯快报", "icon": "📰"},
    {"type": "game", "name": "游戏", "icon": "🎮"},
    {"type": "analysis", "name": "数据分析", "icon": "📊"},
    {"type": "git", "name": "代码提交", "icon": "🔨"},
    {"type": "stock", "name": "股票行情", "icon": "📈"},
    {"type": "shopping", "name": "购物清单", "icon": "🛒"},
]


@router.get("/types")
def list_widget_types():
    """列出可用的 widget 类型（从注册表读取）"""
    return {"types": BUILTIN_WIDGET_TYPES}


def _fetch_stock_from_main():
    """从主系统拉取最新小米股价+K线数据"""
    try:
        url = "https://qt.gtimg.cn/q=hk01810"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("gbk")
        m = re.search(r'"([^"]+)"', raw)
        if not m:
            return None
        fields = m.group(1).split("~")
        name = fields[1] if len(fields) > 1 else "小米集团-W"
        price = fields[3] if len(fields) > 3 else "0"
        change = fields[31] if len(fields) > 31 else "0"
        change_pct = fields[32] if len(fields) > 32 else "0%"
        high = fields[33] if len(fields) > 33 else "0"
        low = fields[34] if len(fields) > 34 else "0"
        volume_raw = fields[36] if len(fields) > 36 else "0"
        amount_raw = fields[37] if len(fields) > 37 else "0"
        time_str = fields[30] if len(fields) > 30 else ""

        try:
            vol = int(float(volume_raw))
            if vol > 100000000:
                volume = f"{vol/100000000:.2f}亿"
            elif vol > 10000:
                volume = f"{vol/10000:.2f}万"
            else:
                volume = str(vol)
        except:
            volume = volume_raw

        try:
            amt = float(amount_raw)
            if amt > 100000000:
                market_cap = f"{amt/100000000:.0f}亿HKD"
            else:
                market_cap = f"{amt/10000:.0f}万HKD"
        except:
            market_cap = amount_raw

        change_str = f"{float(change):+.2f}" if change else "0.00"
        change_pct_str = f"{float(change_pct):+.2f}%" if change_pct else "0.00%"

        stock_data = {
            "name": name,
            "code": "01810.HK",
            "price": float(price),
            "change": float(change),
            "change_pct": float(change_pct),
            "high": float(high),
            "low": float(low),
            "volume": volume,
            "market_cap": market_cap,
            "currency": "HKD",
            "time": time_str,
        }

        # 拉取30日K线
        try:
            kline_url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk01810,day,,,30,qfq"
            kreq = urllib.request.Request(kline_url, headers={"User-Agent": "Mozilla/5.0"})
            kresp = urllib.request.urlopen(kreq, timeout=10)
            kdata = json.loads(kresp.read().decode("utf-8"))
            kdays = kdata.get("data", {}).get("hk01810", {}).get("day", [])
            kline = []
            for d in kdays:
                kline.append({
                    "date": d[0],
                    "open": float(d[1]),
                    "close": float(d[2]),
                    "high": float(d[3]),
                    "low": float(d[4]),
                    "volume": float(d[5]),
                })
            stock_data["kline"] = kline
        except Exception:
            pass

        return stock_data
    except Exception as e:
        print(f"[widgets] refresh-stock error: {e}")
        return None


@router.get("")
def list_widgets(db: Session = Depends(get_db)):
    widgets = db.query(WidgetConfig).order_by(WidgetConfig.position).all()
    result = []
    for w in widgets:
        d = w.to_dict()
        # stock 类型实时拉取最新数据
        if w.widget_type == "stock" and w.enabled:
            fresh = _fetch_stock_from_main()
            if fresh:
                d["config"] = json.dumps(fresh, ensure_ascii=False)
                # 同时更新 DB 供后续使用
                w.config = json.dumps(fresh, ensure_ascii=False)
                db.commit()
        result.append(d)
    return {"widgets": result}


@router.post("")
def create_widget(data: dict, db: Session = Depends(get_db)):
    max_pos = db.query(WidgetConfig).count()
    w = WidgetConfig(
        widget_type=data.get("widget_type", "hello"),
        title=data.get("title", ""),
        config=json.dumps(data.get("config", {})),
        position=data.get("position", max_pos),
        width=data.get("width", 1),
        height=data.get("height", 1),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"widget": w.to_dict()}


@router.put("/{widget_id}")
def update_widget(widget_id: str, data: dict, db: Session = Depends(get_db)):
    w = db.query(WidgetConfig).filter(WidgetConfig.id == widget_id).first()
    if not w:
        raise HTTPException(404, "Widget not found")
    if "title" in data:
        w.title = data["title"]
    if "config" in data:
        w.config = json.dumps(data["config"])
    if "width" in data:
        w.width = data["width"]
    if "height" in data:
        w.height = data["height"]
    if "enabled" in data:
        w.enabled = data["enabled"]
    db.commit()
    db.refresh(w)
    return {"widget": w.to_dict()}


@router.delete("/{widget_id}")
def delete_widget(widget_id: str, db: Session = Depends(get_db)):
    w = db.query(WidgetConfig).filter(WidgetConfig.id == widget_id).first()
    if not w:
        raise HTTPException(404, "Widget not found")
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.put("/reorder")
def reorder_widgets(data: dict, db: Session = Depends(get_db)):
    order = data.get("order", [])
    for i, wid in enumerate(order):
        w = db.query(WidgetConfig).filter(WidgetConfig.id == wid).first()
        if w:
            w.position = i
    db.commit()
    return {"ok": True}

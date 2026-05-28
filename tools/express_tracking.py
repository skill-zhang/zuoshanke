"""📦 快递查询 — 实时物流跟踪（基于快递100 API）

查询主流快递公司的物流状态，返回完整的物流轨迹。
支持圆通/申通/顺丰/中通/韵达/京东/EMS 等 50+ 快递公司。

## 用法
    from tools.express_tracking import express_tracking
    r = json.loads(express_tracking("YT123456789", company="yuantong"))
    r = json.loads(express_tracking("SF1234567890"))  # 自动识别顺丰
"""

import json
import traceback
import urllib.request
import urllib.parse
import urllib.error

# ── 快递公司编码映射（中文名→编码） ──
COMPANY_MAP = {
    "顺丰": "shunfeng", "顺丰速运": "shunfeng",
    "圆通": "yuantong", "圆通速递": "yuantong",
    "申通": "shentong", "申通快递": "shentong",
    "中通": "zhongtong", "中通快递": "zhongtong",
    "韵达": "yunda", "韵达快递": "yunda",
    "京东": "jd", "京东物流": "jd",
    "EMS": "ems", "邮政": "ems", "中国邮政": "ems",
    "德邦": "debang", "德邦快递": "debang",
    "百世": "huitong", "百世快递": "huitong", "汇通": "huitong",
    "天天": "tiantian", "天天快递": "tiantian",
    "极兔": "jtexpress", "J&T": "jtexpress",
    "丹鸟": "danniao", "菜鸟": "danniao",
    "跨越": "kuayue", "跨越速运": "kuayue",
    "苏宁": "suning", "苏宁物流": "suning",
    "壹米滴答": "yimidida",
    "速尔": "sure", "速尔快递": "sure",
    "优速": "yousu", "优速快递": "yousu",
    "安能": "anneng", "安能物流": "anneng",
    "中邮": "zhongyou", "中邮物流": "zhongyou",
}

# ── 编码→中文名 ──
COMPANY_NAMES = {
    "shunfeng": "顺丰速运", "yuantong": "圆通速递", "shentong": "申通快递",
    "zhongtong": "中通快递", "yunda": "韵达快递", "jd": "京东物流",
    "ems": "EMS", "debang": "德邦快递", "huitong": "百世快递",
    "tiantian": "天天快递", "jtexpress": "极兔速递", "danniao": "丹鸟物流",
    "kuayue": "跨越速运", "suning": "苏宁物流", "yimidida": "壹米滴答",
    "sure": "速尔快递", "yousu": "优速快递", "anneng": "安能物流",
    "zhongyou": "中邮物流",
}

# ── 常见运单号前缀 → 快递公司（自动识别） ──
AUTO_DETECT = {
    "SF": "shunfeng",      # 顺丰
    "YT": "yuantong",      # 圆通
    "JD": "jd",            # 京东
    "JT": "jtexpress",     # 极兔
    "VA": "ems", "VB": "ems", "VC": "ems", "VD": "ems",
    "VE": "ems", "VF": "ems", "VG": "ems", "VH": "ems",
    "EA": "ems", "EB": "ems", "EC": "ems", "ED": "ems",
    "EE": "ems", "EF": "ems", "EG": "ems", "EH": "ems",
    "EI": "ems", "EJ": "ems", "EK": "ems", "EL": "ems",
    "EM": "ems", "EN": "ems",
}

TIMEOUT = 15

# ── 物流状态码 ──
STATE_LABELS = {
    "0": "在途",
    "1": "已揽收",
    "2": "疑难",
    "3": "已签收",
    "4": "已退签",
    "5": "派送中",
    "6": "退回",
    "7": "转单",
}


def _auto_detect_company(tracking_no: str) -> str:
    """根据运单号前缀自动识别快递公司"""
    upper = tracking_no.upper().strip()
    for prefix, company in AUTO_DETECT.items():
        if upper.startswith(prefix):
            return company
    # 纯数字可能是 EMS/邮政
    if tracking_no.isdigit():
        if len(tracking_no) == 13:
            return "ems"
    return ""


def _resolve_company(company: str) -> str:
    """将用户输入解析为快递100的公司编码"""
    if not company:
        return ""
    c = company.strip()
    # 已经是编码
    if c in COMPANY_NAMES or c in ("shunfeng", "yuantong", "shentong", "zhongtong", "yunda"):
        return c
    # 中文名匹配
    if c in COMPANY_MAP:
        return COMPANY_MAP[c]
    # 部分匹配
    for name, code in COMPANY_MAP.items():
        if name in c or c in name:
            return code
    return company  # 直接传回


def express_tracking(tracking_no: str, company: str = "") -> str:
    """查询快递物流信息，返回 JSON 字符串

    Args:
        tracking_no: 快递单号（必填）
        company:     快递公司（可选）。可传中文名（'顺丰'）或编码（'shunfeng'）。
                     为空时自动识别（支持顺丰/圆通/京东/EMS前缀）

    Returns:
        JSON string:
        {
            "success": true/false,
            "tracking_no": "运单号",
            "company": "快递公司编码",
            "company_name": "快递公司中文名",
            "state": "在途/已签收/派送中...",
            "state_code": "0-7",
            "is_signed": false,       // 是否已签收
            "records": [              // 物流轨迹
                {
                    "time": "2026-05-28 11:18:47",
                    "location": "开封市",
                    "description": "车辆正在长途运输中..."
                },
                ...
            ],
            "error": "错误信息"
        }
    """
    try:
        if not tracking_no or not tracking_no.strip():
            return json.dumps({"success": False, "error": "快递单号不能为空"}, ensure_ascii=False)

        tracking_no = tracking_no.strip()

        # 解析公司
        resolved_company = _resolve_company(company) if company else ""
        if not resolved_company:
            resolved_company = _auto_detect_company(tracking_no)

        if not resolved_company:
            return json.dumps({
                "success": False,
                "error": f"无法自动识别快递公司，请手动指定 company 参数（如 company='顺丰' 或 company='shunfeng'）",
                "tracking_no": tracking_no,
                "hint": "支持：顺丰/圆通/申通/中通/韵达/京东/EMS/极兔/百世/德邦等",
            }, ensure_ascii=False)

        # 调用快递100 API
        params = urllib.parse.urlencode({
            "type": resolved_company,
            "postid": tracking_no,
        })
        url = f"https://www.kuaidi100.com/query?{params}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))

        if data.get("status") != "200":
            return json.dumps({
                "success": False,
                "error": data.get("message", "查询失败"),
                "tracking_no": tracking_no,
            }, ensure_ascii=False)

        state_code = str(data.get("state", "0"))
        state_label = STATE_LABELS.get(state_code, "未知")
        raw_records = data.get("data", [])

        # 构造物流轨迹
        records = []
        for r in raw_records:
            time_str = r.get("time", "")
            ftime_str = r.get("ftime", "")
            context = r.get("context", "")
            location = r.get("location", "")

            # 从 context 中尝试提取地点
            if not location and context:
                import re
                loc_match = re.search(r'[【【](.+?)[】]', context)
                if loc_match:
                    location = loc_match.group(1)

            records.append({
                "time": ftime_str or time_str,
                "location": location,
                "description": context,
            })

        company_name = COMPANY_NAMES.get(resolved_company, resolved_company)

        result = {
            "success": True,
            "tracking_no": tracking_no,
            "company": resolved_company,
            "company_name": company_name,
            "state": state_label,
            "state_code": state_code,
            "is_signed": state_code == "3",
            "record_count": len(records),
            "records": records,
        }

        # 如果 API 返回异常数据（查无结果）
        if len(records) == 1 and "查无" in records[0]["description"]:
            result["is_valid"] = False
            result["note"] = "该单号暂无物流信息，请确认单号和快递公司是否正确"

        return json.dumps(result, ensure_ascii=False)

    except urllib.error.HTTPError as e:
        return json.dumps({
            "success": False,
            "error": f"HTTP {e.code}: {e.reason}",
            "tracking_no": tracking_no,
        }, ensure_ascii=False)
    except urllib.error.URLError as e:
        return json.dumps({
            "success": False,
            "error": f"网络连接失败: {e.reason}。快递查询需要网络连接",
            "tracking_no": tracking_no,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"快递查询失败: {str(e)}",
            "detail": traceback.format_exc(),
            "tracking_no": tracking_no,
        }, ensure_ascii=False)

"""🧮 计算器 & 单位换算 — 精确转换/日期计算/数学运算

纯标准库实现，不需要外部 API。
核心价值：LLM 在单位换算和精确计算上容易翻车，这个工具给出精确结果。

## 用法
    from tools.calculator import calculator
    r = json.loads(calculator(mode="convert", value=100, from_unit="cm", to_unit="m"))
    r = json.loads(calculator(mode="date", operation="diff", date1="2026-01-01", date2="2026-12-31"))
"""

import json
import math
import datetime
import re
import hashlib

# ── 单位换算表 ──
# 所有单位统一转成 SI 基准值，再转目标单位

# 长度 (基准: 米)
LENGTH = {
    "mm": 0.001, "厘米": 0.01, "cm": 0.01,
    "米": 1.0, "m": 1.0,
    "千米": 1000.0, "km": 1000.0,
    "英寸": 0.0254, "in": 0.0254,
    "英尺": 0.3048, "ft": 0.3048,
    "码": 0.9144, "yd": 0.9144,
    "英里": 1609.344, "mi": 1609.344,
    "海里": 1852.0, "nmi": 1852.0,
    "里": 500.0, "华里": 500.0,
    "丈": 3.33333, "尺": 0.33333, "寸": 0.03333,
}

# 重量 (基准: 千克)
WEIGHT = {
    "毫克": 0.000001, "mg": 0.000001,
    "克": 0.001, "g": 0.001,
    "千克": 1.0, "kg": 1.0,
    "吨": 1000.0, "t": 1000.0,
    "斤": 0.5,
    "两": 0.05,
    "磅": 0.453592, "lb": 0.453592,
    "盎司": 0.0283495, "oz": 0.0283495,
}

# 温度 (特殊: 非等比)
TEMPERATURE = {"c": "摄氏度", "f": "华氏度", "k": "开尔文"}

# 体积/容积 (基准: 升)
VOLUME = {
    "毫升": 0.001, "ml": 0.001,
    "升": 1.0, "l": 1.0, "L": 1.0,
    "立方米": 1000.0, "m3": 1000.0,
    "加仑": 3.78541, "gal": 3.78541,
    "品脱": 0.473176, "pt": 0.473176,
    "杯": 0.236588,
    "汤匙": 0.0147868, " tbsp": 0.0147868,
    "茶匙": 0.00492892, " tsp": 0.00492892,
}

# 面积 (基准: 平方米)
AREA = {
    "平方毫米": 0.000001, "mm2": 0.000001,
    "平方厘米": 0.0001, "cm2": 0.0001,
    "平方米": 1.0, "m2": 1.0,
    "平方千米": 1000000.0, "km2": 1000000.0,
    "公顷": 10000.0, "ha": 10000.0,
    "亩": 666.667,
    "平方英尺": 0.092903, "ft2": 0.092903,
    "平方英寸": 0.00064516, "in2": 0.00064516,
    "英亩": 4046.86,
}

# 速度 (基准: 米/秒)
SPEED = {
    "m/s": 1.0, "米/秒": 1.0,
    "km/h": 0.277778, "千米/时": 0.277778,
    "mph": 0.44704, "英里/时": 0.44704,
    "节": 0.514444, "kn": 0.514444,
}

# 数据存储 (基准: 字节)
DATA = {
    "b": 1, "bit": 1, "比特": 1,
    "B": 8, "byte": 8, "字节": 8,
    "KB": 8 * 1024, "K": 8 * 1024,
    "MB": 8 * 1024 * 1024, "M": 8 * 1024 * 1024,
    "GB": 8 * 1024 * 1024 * 1024, "G": 8 * 1024 * 1024 * 1024,
    "TB": 8 * 1024 * 1024 * 1024 * 1024, "T": 8 * 1024 * 1024 * 1024 * 1024,
}

# 时间 (基准: 秒)
TIME = {
    "毫秒": 0.001, "ms": 0.001,
    "秒": 1.0, "s": 1.0,
    "分钟": 60.0, "min": 60.0,
    "小时": 3600.0, "h": 3600.0, "时": 3600.0,
    "天": 86400.0, "d": 86400.0,
    "周": 604800.0,
    "月": 2592000.0,  # 按30天近似
    "年": 31536000.0,  # 按365天
}

# 压力 (基准: 帕斯卡)
PRESSURE = {
    "Pa": 1.0, "帕": 1.0,
    "kPa": 1000.0, "千帕": 1000.0,
    "MPa": 1000000.0, "兆帕": 1000000.0,
    "bar": 100000.0,
    "atm": 101325.0, "标准大气压": 101325.0,
    "mmHg": 133.322, "毫米汞柱": 133.322,
    "psi": 6894.76,
}

# 能量 (基准: 焦耳)
ENERGY = {
    "J": 1.0, "焦耳": 1.0,
    "kJ": 1000.0, "千焦": 1000.0,
    "cal": 4.184, "卡": 4.184, "卡路里": 4.184,
    "kcal": 4184.0, "千卡": 4184.0, "大卡": 4184.0,
    "kWh": 3600000.0, "度": 3600000.0,
    "eV": 1.602e-19, "电子伏": 1.602e-19,
}

UNIT_CATEGORIES = {
    "length": {"name": "长度", "units": LENGTH, "aliases": ["长度", "距离", "height", "长"]},
    "weight": {"name": "重量", "units": WEIGHT, "aliases": ["重量", "质量", "体重", "重"]},
    "temperature": {"name": "温度", "units": TEMPERATURE, "aliases": ["温度", "气温", "体温"]},
    "volume": {"name": "体积/容积", "units": VOLUME, "aliases": ["体积", "容积", "容量", "液体"]},
    "area": {"name": "面积", "units": AREA, "aliases": ["面积", "土地", "地"]},
    "speed": {"name": "速度", "units": SPEED, "aliases": ["速度", "速率", "时速"]},
    "data": {"name": "数据存储", "units": DATA, "aliases": ["数据", "存储", "硬盘", "内存", "流量", "bit"]},
    "time": {"name": "时间", "units": TIME, "aliases": ["时间", "时长"]},
    "pressure": {"name": "压力", "units": PRESSURE, "aliases": ["压力", "气压", "血压"]},
    "energy": {"name": "能量", "units": ENERGY, "aliases": ["能量", "热量", "卡路里", "电能"]},
}


def _convert_unit(value: float, from_unit: str, to_unit: str) -> dict:
    """执行单位换算"""
    from_lower = from_unit.lower().strip()
    to_lower = to_unit.lower().strip()

    # 先匹配分类
    for cat_name, cat in UNIT_CATEGORIES.items():
        units = cat["units"]

        # 温度特殊处理
        if cat_name == "temperature":
            from_temp = None
            to_temp = None
            for code, name in units.items():
                if from_lower in (code.lower(), name.lower()):
                    from_temp = code
                if to_lower in (code.lower(), name.lower()):
                    to_temp = code

            if from_temp and to_temp:
                # 摄氏度
                if from_temp == "c":
                    c_val = value
                elif from_temp == "f":
                    c_val = (value - 32) * 5 / 9
                else:  # k
                    c_val = value - 273.15

                # 转目标
                if to_temp == "c":
                    result = c_val
                elif to_temp == "f":
                    result = c_val * 9 / 5 + 32
                else:  # k
                    result = c_val + 273.15

                return {"success": True, "value": round(result, 6), "from_unit": from_unit, "to_unit": to_unit, "category": "temperature"}

        # 普通单位
        if from_lower in units and to_lower in units:
            base = value * units[from_lower]
            result = base / units[to_lower]
            return {"success": True, "value": round(result, 10), "from_unit": from_unit, "to_unit": to_unit, "category": cat["name"]}

        # 别名匹配
        for unit_key, factor in units.items():
            if isinstance(unit_key, str) and from_lower == unit_key.lower():
                base = value * factor
                break
        else:
            continue

        for unit_key, factor in units.items():
            if isinstance(unit_key, str) and to_lower == unit_key.lower():
                result = base / factor
                return {"success": True, "value": round(result, 10), "from_unit": from_unit, "to_unit": to_unit, "category": cat["name"]}
        break

    return {"success": False, "error": f"无法换算：{from_unit} → {to_unit}，请确认单位属于同一类别且拼写正确"}


def _date_calc(operation: str, **kwargs) -> dict:
    """日期计算"""
    now = datetime.date.today()
    ops = {
        "today": lambda: {"date": now.isoformat(), "weekday": ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()], "day_of_year": now.timetuple().tm_yday},

        "diff": lambda: _date_diff(kwargs.get("date1", ""), kwargs.get("date2", ""), kwargs.get("unit", "天")),

        "add": lambda: _date_add(kwargs.get("date", now.isoformat()), kwargs.get("amount", 1), kwargs.get("unit", "天")),

        "age": lambda: _calculate_age(kwargs.get("birthday", "")),

        "week_of_year": lambda: {"week": now.isocalendar()[1], "year": now.isocalendar()[0]},

        "month_days": lambda: _month_days(kwargs.get("year", now.year), kwargs.get("month", now.month)),

        "countdown": lambda: _countdown(kwargs.get("target_date", "")),
    }

    fn = ops.get(operation)
    if not fn:
        return {"success": False, "error": f"不支持的日期操作: {operation}"}

    try:
        result = fn()
        result["success"] = True
        result["operation"] = operation
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def _date_diff(d1: str, d2: str, unit: str) -> dict:
    """计算两个日期之差"""
    a = datetime.date.fromisoformat(d1)
    b = datetime.date.fromisoformat(d2)
    delta = abs((b - a).days)
    result = {"date1": d1, "date2": d2, "days": delta}
    if unit == "周":
        result["weeks"] = round(delta / 7, 1)
    elif unit == "月":
        result["months"] = round(delta / 30.44, 1)
    elif unit == "年":
        result["years"] = round(delta / 365.25, 1)
    return result


def _date_add(date_str: str, amount: int, unit: str) -> dict:
    """日期加减"""
    d = datetime.date.fromisoformat(date_str)
    if unit in ("天", "day", "days"):
        result = d + datetime.timedelta(days=amount)
    elif unit in ("周", "week", "weeks"):
        result = d + datetime.timedelta(weeks=amount)
    elif unit in ("月", "month", "months"):
        m = d.month + amount
        y = d.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        import calendar
        max_day = calendar.monthrange(y, m)[1]
        day = min(d.day, max_day)
        result = datetime.date(y, m, day)
    elif unit in ("年", "year", "years"):
        m = d.month
        y = d.year + amount
        import calendar
        max_day = calendar.monthrange(y, m)[1]
        day = min(d.day, max_day)
        result = datetime.date(y, m, day)
    else:
        return {"error": f"不支持的单位: {unit}"}
    return {"date": date_str, "amount": amount, "unit": unit, "result": result.isoformat()}


def _calculate_age(birthday: str) -> dict:
    """计算年龄"""
    bd = datetime.date.fromisoformat(birthday)
    today = datetime.date.today()
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    next_birthday = datetime.date(today.year + (1 if (today.month, today.day) > (bd.month, bd.day) else 0), bd.month, bd.day)
    days_to_next = (next_birthday - today).days
    return {"birthday": birthday, "age": age, "next_birthday": next_birthday.isoformat(), "days_until_next": days_to_next}


def _month_days(year: int, month: int) -> dict:
    """获取某月的天数"""
    import calendar
    return {"year": year, "month": month, "days": calendar.monthrange(year, month)[1], "month_name": ["","一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"][month]}


def _countdown(target: str) -> dict:
    """倒计时"""
    t = datetime.date.fromisoformat(target)
    today = datetime.date.today()
    delta = (t - today).days
    return {"target": target, "days_remaining": delta, "is_past": delta < 0}


def calculator(mode: str = "convert", **kwargs) -> str:
    """计算器 & 单位换算，返回 JSON 字符串

    Args:
        mode: 模式
            "convert" — 单位换算（需 value, from_unit, to_unit）
            "calc" — 数学计算（需 expression）
            "date" — 日期计算（需 operation + 各种参数）
            "list" — 列出所有支持的换算类别

    mode="convert" 参数:
        value:     数值
        from_unit: 源单位
        to_unit:   目标单位

    mode="calc" 参数:
        expression: 数学表达式，如 "12 * 3 + 5"、"sqrt(144)"、"2^10"

    mode="date" 参数:
        operation: 操作类型
            "today" — 获取今天日期
            "diff" — 日期差（需 date1, date2）
            "add" — 日期加减（需 date, amount, unit）
            "age" — 计算年龄（需 birthday YYYY-MM-DD）
            "countdown" — 倒计时（需 target_date YYYY-MM-DD）

    mode="list" — 列出所有支持的换算类别和单位

    Returns:
        JSON string
    """
    try:
        if mode == "list":
            categories = []
            for cat_name, cat in UNIT_CATEGORIES.items():
                units = list(cat["units"].keys())[:10]
                categories.append({"category": cat["name"], "examples": units})
            return json.dumps({"success": True, "mode": "list", "categories": categories}, ensure_ascii=False)

        if mode == "convert":
            value = kwargs.get("value")
            from_unit = kwargs.get("from_unit", "")
            to_unit = kwargs.get("to_unit", "")

            if value is None:
                return json.dumps({"success": False, "error": "缺少 value 参数"}, ensure_ascii=False)
            if not from_unit:
                return json.dumps({"success": False, "error": "缺少 from_unit 参数"}, ensure_ascii=False)
            if not to_unit:
                return json.dumps({"success": False, "error": "缺少 to_unit 参数"}, ensure_ascii=False)

            result = _convert_unit(float(value), from_unit, to_unit)
            result["input_value"] = float(value)
            result["mode"] = "convert"
            return json.dumps(result, ensure_ascii=False)

        if mode == "calc":
            expr = kwargs.get("expression", "")
            if not expr:
                return json.dumps({"success": False, "error": "缺少 expression 参数"}, ensure_ascii=False)

            # 安全表达式求值
            safe_ops = {
                "abs": abs, "round": round, "int": int, "float": float,
                "sqrt": math.sqrt, "pow": pow, "sin": math.sin, "cos": math.cos,
                "tan": math.tan, "log": math.log, "log10": math.log10, "log2": math.log2,
                "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
                "pi": math.pi, "e": math.e, "max": max, "min": min,
                "sum": sum,
            }

            # 替换常见符号
            cleaned = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
            cleaned = cleaned.replace("x", "*", 1) if cleaned.startswith("x") else cleaned

            result = eval(cleaned, {"__builtins__": {}}, safe_ops)
            return json.dumps({
                "success": True,
                "mode": "calc",
                "expression": expr,
                "result": round(result, 10) if isinstance(result, float) else result,
            }, ensure_ascii=False)

        if mode == "date":
            operation = kwargs.pop("operation", "today")
            result = _date_calc(operation, **kwargs)
            result["mode"] = "date"
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"success": False, "error": f"不支持的模式: {mode}，可选: convert/calc/date/list"}, ensure_ascii=False)

    except ZeroDivisionError:
        return json.dumps({"success": False, "error": "除以零"}, ensure_ascii=False)
    except SyntaxError:
        return json.dumps({"success": False, "error": "表达式语法错误"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"计算失败: {str(e)}"}, ensure_ascii=False)

"""get_current_time — 获取当前日期和时间"""

import json
from datetime import datetime, timezone, timedelta


CST = timezone(timedelta(hours=8))  # 中国标准时间 UTC+8


def get_current_time() -> str:
    """获取当前日期和时间

    Returns:
        JSON 字符串 {datetime, date, time, weekday, timestamp, timezone}
    """
    now = datetime.now(CST)
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return json.dumps({
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekdays[now.weekday()],
        "timestamp": int(now.timestamp()),
        "timezone": "Asia/Shanghai (UTC+8)",
    }, ensure_ascii=False)

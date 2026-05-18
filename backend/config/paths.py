"""坐山客 — 全局路径配置

所有项目路径定义集中在此文件。其他模块统一 `from config.paths import xxx` 引用。
禁止在任何 .py 文件中写死路径字符串。
"""
import os
from pathlib import Path

# ── 项目根目录 ──
PROJECT_ROOT = Path.home() / "zuoshanke"

# ── 目录 ──
TOOLS_DIR = os.path.expanduser("~/zuoshanke/tools")
SKILLS_DIR = os.path.expanduser("~/zuoshanke/skills")
FRONTEND_PUBLIC_DIR = os.path.expanduser("~/zuoshanke/frontend/public")

# ── 数据目录 ──
ZUOSHANKE_HOME = Path.home() / ".zuoshanke"
LOG_DIR = Path.home() / ".zuoshanke"
GATEWAY_BUF_DIR = Path.home() / ".zuoshanke" / "gateway"

# ── Hermes 依赖路径 ──
HERMES_ENV = Path.home() / ".hermes" / ".env"
HERMES_BIN = os.path.expanduser("~/.local/bin/hermes")
HERMES_LOGS = os.path.expanduser("~/.hermes/logs")

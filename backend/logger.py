"""统一日志模块

用法:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("msg")
    log.error("msg", exc_info=True)

日志输出到:
    - 文件: ~/.zuoshanke/backend.log (自动轮转，最大10MB，保留5份)
    - stdout: 控制台输出（uvicorn 风格）
"""
import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_DIR = Path.home() / ".zuoshanke"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "backend.log"

# ── 格式 ──
_FILE_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_STDOUT_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── 已配置标记（避免重复配置） ──
_LOGGER_CONFIGURED = False


def configure_logger(level: int = logging.DEBUG) -> None:
    """配置根日志器（只执行一次）"""
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    # 文件 Handler（自动轮转，10MB，保留5份）
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))
    root.addHandler(file_handler)

    # stdout Handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter(_STDOUT_FORMAT, _DATE_FORMAT))
    root.addHandler(stdout_handler)

    _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器（自动配置）"""
    configure_logger()
    return logging.getLogger(name)

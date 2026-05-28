#!/usr/bin/env python3
"""
code_runner.py — 多语言代码执行工具

纯 Python 标准库实现，支持 Python、Shell、JavaScript 执行。
安全措施：命令黑名单、超时控制。

Usage:
    from code_runner import run_code, run_file

    result = run_code("print('hello')", language="python")
    result = run_file("/path/to/script.sh", language="auto")
"""

import os
import sys
import subprocess
import shlex
import tempfile
import uuid
import time
import signal
import re
import shutil

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


DEFAULT_TIMEOUT = 30  # seconds (used by run_code)
FILE_TIMEOUT = 60     # seconds (used by run_file)

# 危险命令黑名单 — 匹配子进程命令中的任意子串（大小写不敏感）
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf --no-preserve-root",
    "dd if=",
    "mkfs",
    "mkfs.ext",
    "mkfs.xfs",
    "mkfs.btrfs",
    ":(){ :|:& };:",    # fork bomb (bash)
    "chmod -R 777 /",
    "chmod 777 /",
    "> /dev/sda",
    "| /dev/sda",
    "flashrom",
    "pv",
    "wipefs",
    "hdparm",
    "fdisk",
    "parted",
    "mkswap",
    "swapoff",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
    "poweroff",
    "halt",
]

# JavaScript 解释器路径（默认用系统 PATH 中的 node）
_NODE_PATH = os.environ.get("NODE_PATH", shutil.which("node") or "node")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _is_dangerous(code: str) -> tuple[bool, str]:
    """检查代码是否包含危险命令。返回 (危险?, 匹配到的模式)。"""
    code_lower = code.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in code_lower:
            return True, pattern
    return False, ""


def _scan_python_subprocess(code: str) -> tuple[bool, str]:
    """检查 Python 代码中是否通过 subprocess/os.system 执行危险系统命令。

    即使 language="python"，代码也可能通过 subprocess.run("kill", shell=True)
    执行危险系统命令。此函数检查 Python 特定的危险子进程调用模式。
    """
    patterns = [
        # subprocess.run("kill ...", shell=True) 或 subprocess.Popen("kill ...", ...)
        (r'subprocess\.(?:run|Popen|call|check_call)\s*\(\s*["\']\s*kill\s', 'Python subprocess kill'),
        # os.system("kill ...")
        (r'os\.system\s*\(\s*["\']\s*kill\s', 'Python os.system kill'),
        # os.popen("kill ...")
        (r'os\.popen\s*\(\s*["\']\s*kill\s', 'Python os.popen kill'),
        # subprocess.run("fuser -k ...")
        (r'subprocess\.(?:run|Popen)\s*\(\s*["\']\s*fuser\s+-k\s', 'Python subprocess fuser kill'),
        # subprocess.run(["kill", ...]) — list args
        (r'subprocess\.(?:run|Popen|call)\s*\(\s*\[[^\]]*["\']kill["\']', 'Python subprocess kill (list args)'),
        # subprocess.run("systemctl stop ...")
        (r'subprocess\.(?:run|Popen)\s*\(\s*["\']\s*systemctl\s+(?:stop|kill|restart)', 'Python subprocess systemctl'),
        # subprocess.run("rm -rf /..." or "shutdown"/"reboot")
        (r'subprocess\.(?:run|Popen)\s*\(\s*["\']\s*(?:rm\s+-[rf]|shutdown|reboot|poweroff|halt)', 'Python subprocess destructive'),
    ]
    for pat, desc in patterns:
        if re.search(pat, code, re.IGNORECASE):
            return True, desc
    return False, ""


def _detect_language_from_path(path: str) -> str:
    """根据文件扩展名自动检测语言。"""
    ext = os.path.splitext(path)[1].lower()
    ext_map = {
        ".py": "python",
        ".sh": "shell",
        ".js": "javascript",
    }
    lang = ext_map.get(ext)
    if lang is None:
        raise ValueError(
            f"无法从文件扩展名 '{ext}' 自动检测语言。支持的扩展名: .py, .sh, .js"
        )
    return lang


def _build_cmd(code: str, language: str) -> list[str]:
    """构建子进程命令列表。"""
    lang = language.lower().strip()
    if lang == "python":
        return ["python3", "-c", code]
    elif lang in ("shell", "bash"):
        return ["bash", "-c", code]
    elif lang in ("javascript", "js", "node"):
        return [_NODE_PATH, "-e", code]
    else:
        raise ValueError(
            f"不支持的语言: '{language}'。支持的: python, shell/bash, javascript/js/node"
        )


def _run_cmd(
    cmd: list[str],
    timeout: int,
    cwd: str | None = None,
) -> dict:
    """
    底层子进程执行。
    返回 dict: {stdout, stderr, exit_code, success, error, timed_out}
    """
    result = {
        "stdout": "",
        "stderr": "",
        "exit_code": -1,
        "success": False,
        "error": None,
        "timed_out": False,
    }

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=cwd,
            preexec_fn=os.setsid,  # 放入独立进程组，方便杀死子进程树
        )
    except FileNotFoundError as e:
        result["error"] = f"可执行文件未找到: {e}"
        return result
    except PermissionError as e:
        result["error"] = f"权限错误: {e}"
        return result
    except OSError as e:
        result["error"] = f"系统错误: {e}"
        return result

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        result["timed_out"] = False
    except subprocess.TimeoutExpired:
        # 超时 — 杀死整个进程组
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        stdout_bytes, stderr_bytes = proc.communicate()
        result["timed_out"] = True
        result["error"] = f"执行超时（{timeout}秒）"

    result["stdout"] = stdout_bytes.decode("utf-8", errors="replace")
    result["stderr"] = stderr_bytes.decode("utf-8", errors="replace")
    result["exit_code"] = proc.returncode
    result["success"] = proc.returncode == 0

    return result


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def run_code(
    code: str = "",
    language: str = "python",
    timeout: int = DEFAULT_TIMEOUT,
    code_b64: str = "",
) -> dict:
    """
    执行一段代码并返回结果。
    对于大段代码，可使用 code_b64 参数(base64编码)替代 code 参数，
    避免 JSON 转义问题。

    参数:
        code:     要执行的代码字符串
        language: 语言标识 — 'python', 'shell'/'bash', 'javascript' (或 'js', 'node')
        timeout:  超时秒数（默认 30）
        code_b64: base64 编码的代码（替代 code，避免 JSON 转义问题）

    返回:
        dict: {stdout, stderr, exit_code, success, error, timed_out}
    """
    import base64
    # 优先使用 code_b64
    if code_b64:
        try:
            code = base64.b64decode(code_b64).decode('utf-8')
        except Exception as e:
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "success": False,
                "error": f"base64 解码失败: {e}",
                "timed_out": False,
            }
    # 安全检测
    dangerous, pattern = _is_dangerous(code)
    if dangerous:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"危险命令被禁止: 匹配到黑名单模式 '{pattern}'",
            "timed_out": False,
        }

    # 🆕 Python 子进程安全检查（language="python" 时也能拦 kill/systemctl 等）
    if language == "python":
        py_dangerous, py_pattern = _scan_python_subprocess(code)
        if py_dangerous:
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "success": False,
                "error": f"Python 子进程危险命令被禁止: {py_pattern}",
                "timed_out": False,
            }

    if not isinstance(code, str) or not code.strip():
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": "代码内容为空",
            "timed_out": False,
        }

    # 长代码必须走 code_b64（避免 JSON 转义问题）
    # 详见 code_runner.py 的 code_b64 参数说明
    if len(code) > 3000 and not code_b64:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"代码过长({len(code)}字符)，JSON转义可能出错。请使用 code_b64(base64编码)参数替代 code 参数。",
            "timed_out": False,
        }

    try:
        cmd = _build_cmd(code, language)
    except ValueError as e:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": str(e),
            "timed_out": False,
        }

    return _run_cmd(cmd, timeout=timeout)


def run_file(
    path: str,
    language: str = "auto",
    timeout: int = FILE_TIMEOUT,
) -> dict:
    """
    执行一个脚本文件并返回结果。

    参数:
        path:     脚本文件路径
        language: 语言标识或 'auto'（自动根据扩展名检测）
        timeout:  超时秒数（默认 60）

    返回:
        dict: {stdout, stderr, exit_code, success, error, timed_out}
    """
    expanded_path = os.path.expanduser(path)

    if not os.path.isfile(expanded_path):
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"文件不存在: {expanded_path}",
            "timed_out": False,
        }

    if language == "auto":
        try:
            language = _detect_language_from_path(expanded_path)
        except ValueError as e:
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "success": False,
                "error": str(e),
                "timed_out": False,
            }

    # 读取文件内容做安全检测
    try:
        with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"无法读取文件: {e}",
            "timed_out": False,
        }

    dangerous, pattern = _is_dangerous(content)
    if dangerous:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"危险命令被禁止: 匹配到黑名单模式 '{pattern}'",
            "timed_out": False,
        }

    # 构建命令并执行文件
    lang = language.lower().strip()
    if lang == "python":
        cmd = ["python3", expanded_path]
    elif lang == "shell":
        cmd = ["bash", expanded_path]
    elif lang in ("javascript", "js", "node"):
        cmd = [_NODE_PATH, expanded_path]
    else:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"不支持的语言: '{language}'",
            "timed_out": False,
        }

    return _run_cmd(cmd, timeout=timeout, cwd=os.path.dirname(expanded_path))


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    """简易命令行接口。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="code_runner.py — 多语言代码执行工具",
    )
    parser.add_argument(
        "code_or_file",
        nargs="?",
        help="要执行的代码字符串或文件路径（配合 -f 使用文件模式）",
    )
    parser.add_argument(
        "-l", "--language",
        default="python",
        help='语言: python, shell, javascript (默认: python)',
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"超时秒数 (默认: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "-f", "--file",
        action="store_true",
        help="以文件模式运行（code_or_file 会被解释为文件路径）",
    )

    args = parser.parse_args()

    if not args.code_or_file:
        # 从 stdin 读取
        code = sys.stdin.read().strip()
        if not code:
            parser.print_help()
            sys.exit(1)
        args.code_or_file = code

    if args.file:
        result = run_file(
            path=args.code_or_file,
            language=args.language,
            timeout=args.timeout,
        )
    else:
        result = run_code(
            code=args.code_or_file,
            language=args.language,
            timeout=args.timeout,
        )

    # 输出
    if result["stdout"]:
        sys.stdout.write(result["stdout"])
        if not result["stdout"].endswith("\n"):
            sys.stdout.write("\n")
    if result["stderr"]:
        sys.stderr.write(result["stderr"])
        if not result["stderr"].endswith("\n"):
            sys.stderr.write("\n")
    if result["error"]:
        print(f"[错误] {result['error']}", file=sys.stderr)

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()

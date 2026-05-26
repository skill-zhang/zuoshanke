"""容器管理工具 — 基于 docker CLI 的 subprocess 封装

## 功能
- container_list: 列出所有容器（支持 -a 参数显示所有容器）
- container_logs: 查看容器日志（支持 tail 行数）
- container_restart: 重启容器

## 用法
    from container_tools import container_list, container_logs, container_restart
    r = container_list(all=True)        # → JSON {containers: [...]}
    r = container_logs("nginx", tail=50) # → JSON {logs: "..."}
    r = container_restart("nginx")       # → JSON {success: true, message: "..."}
"""

import json
import subprocess
import shlex
from typing import Optional


def _run_docker(cmd: list[str]) -> dict:
    """执行 docker 命令，返回统一格式的响应"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or result.stdout.strip(),
            }
        return {
            "success": True,
            "output": result.stdout.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "命令执行超时 (30s)"}
    except FileNotFoundError:
        return {"success": False, "error": "未找到 docker 命令，请确认 Docker 已安装"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def container_list(all: bool = False) -> str:
    """列出 Docker 容器

    Args:
        all: 是否显示所有容器（包括已停止的），默认只显示运行中的

    Returns:
        JSON 字符串 {success, containers: [{id, name, image, status, ports, created}], error}
    """
    cmd = ["docker", "ps"]
    if all:
        cmd.append("-a")

    # 用 --format 输出结构化数据
    fmt = '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}","created":"{{.CreatedAt}}"}'
    cmd.extend(["--format", fmt])

    result = _run_docker(cmd)
    if not result["success"]:
        return json.dumps({"success": False, "containers": [], "error": result["error"]})

    containers = []
    for line in result["output"].splitlines():
        line = line.strip()
        if line:
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                containers.append({"raw": line})

    return json.dumps({"success": True, "containers": containers}, ensure_ascii=False)


def container_logs(container: str, tail: Optional[int] = None, follow: bool = False) -> str:
    """查看容器日志

    Args:
        container: 容器名或容器 ID
        tail: 仅显示最后 N 行（默认全部）
        follow: 是否跟随输出（默认 False，设为 True 时仅返回当前日志）

    Returns:
        JSON 字符串 {success, logs, error}
    """
    cmd = ["docker", "logs"]

    if tail is not None:
        cmd.extend(["--tail", str(tail)])
    if follow:
        cmd.append("--follow")

    cmd.append(container)

    result = _run_docker(cmd)
    if not result["success"]:
        return json.dumps({"success": False, "logs": "", "error": result["error"]})

    return json.dumps({"success": True, "logs": result["output"]}, ensure_ascii=False)


def container_restart(container: str, timeout: Optional[int] = None) -> str:
    """重启容器

    Args:
        container: 容器名或容器 ID
        timeout: 等待容器停止的超时秒数（可选）

    Returns:
        JSON 字符串 {success, message, error}
    """
    cmd = ["docker", "restart"]

    if timeout is not None:
        cmd.extend(["--time", str(timeout)])

    cmd.append(container)

    result = _run_docker(cmd)
    if not result["success"]:
        return json.dumps({"success": False, "message": "", "error": result["error"]})

    return json.dumps({
        "success": True,
        "message": f"容器 {container} 已重启",
    }, ensure_ascii=False)

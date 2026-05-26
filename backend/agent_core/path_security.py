"""文件路径安全 — 防止路径穿越和敏感文件写入

核心功能:
1. validate_within_dir(path, root) — 确保路径在允许的 root 目录内
2. check_sensitive_write(path) — 阻止写入敏感系统/凭据文件
3. get_allowed_roots() — 返回允许写入的根目录列表

设计参考: Hermes tools/path_security.py (43 LOC) + file_safety.py (111 LOC)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── 敏感路径前缀（不允许 LLM 工具写入）──
_SENSITIVE_WRITE_PATHS = [
    # 系统级
    "/etc/",
    "/boot/",
    "/dev/",
    "/proc/",
    "/sys/",
    "/usr/",
    "/var/",
    "/bin/",
    "/sbin/",
    "/lib/",

    # macOS 路径变体
    "/private/etc/",
    "/private/var/",

    # SSH
    "/root/.ssh/",
    "~/.ssh/",

    # 云服务商凭据目录
    "~/.aws/",
    "~/.azure/",

    # 容器/K8s 认证
    "/var/run/docker.sock",
    "/run/docker.sock",
    "~/.docker/",
    "~/.kube/",

    # 代码签名/包管理
    "~/.gnupg/",
    "~/.config/gh/",

    # 系统认证
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/sudoers.d/",
    "/etc/systemd/",
    "/etc/ssl/",
]

# ── 敏感凭据文件（如果 LLM 覆盖了这些文件，系统可能断连）──
_CREDENTIAL_FILES = [
    ".env",
    "auth.json",
    "credentials.json",
    "service-account.json",
    "client_secret.json",
    "oauth_token.json",
    "gateway.env",
    "gateway.env.old",
    "gateway.env.new",

    # 网络/云凭据
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",

    # Shell 配置文件（持久化攻击向量）
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".zprofile",
    ".profile",
]

# ── 坐山客项目内部关键文件（覆盖后系统可能崩溃）──
_PROJECT_CRITICAL_FILES = [
    "main.py",
    "models.py",
    "database.py",
    "schemas.py",
]

# ── 项目根目录检测 ──

def _find_project_root() -> Optional[str]:
    """向上查找项目中 zuoshanke 的根目录（包含 tools/ 或 backend/ 的目录）"""
    cwd = os.getcwd()
    # 先检查当前目录
    for parent in [cwd] + [os.path.dirname(cwd)]:
        if os.path.isdir(os.path.join(parent, "tools")) and os.path.isdir(os.path.join(parent, "backend")):
            return parent
    # 再递归查找
    p = Path(cwd)
    while p.parent != p:
        if (p / "tools").is_dir() and (p / "backend").is_dir():
            return str(p)
        p = p.parent
    return None


def get_allowed_roots() -> list[str]:
    """返回 LLM 工具允许写入的根目录列表。"""
    roots = []
    # 项目目录
    project_root = _find_project_root()
    if project_root:
        roots.append(project_root)
    # 家目录下的项目（用户通常允许写入自己的项目文件）
    home = os.path.expanduser("~")
    if project_root and project_root.startswith(home):
        roots.append(home)
    return roots


def _normalize_path(path: str) -> str:
    """展开 ~ 并转为规范绝对路径。"""
    return str(Path(path).expanduser().resolve())


def has_traversal_component(path_str: str) -> bool:
    """快速检查路径是否包含遍历组件（..）。"""
    return ".." in Path(path_str).parts


def validate_within_dir(path: str, root: str) -> Optional[str]:
    """验证 path 是否在 root 目录内。

    Args:
        path: 要检查的文件路径
        root: 允许的根目录

    Returns:
        None: 路径安全
        str: 错误描述
    """
    try:
        path_resolved = Path(path).expanduser().resolve()
        root_resolved = Path(root).expanduser().resolve()
        path_resolved.relative_to(root_resolved)
        return None
    except ValueError:
        return f"路径不在允许的目录内: {path}"
    except (OSError, RuntimeError) as e:
        return f"路径解析失败: {e}"


def check_sensitive_write(path: str) -> Optional[str]:
    """检查写入目标路径是否涉及敏感文件。

    返回值:
        None: 可以写入
        str: 阻断原因

    阻断条件:
    1. 路径穿越（包含 ..）
    2. 写入系统敏感路径
    3. 写入凭据/认证文件
    4. 写入项目关键文件
    """
    try:
        resolved = _normalize_path(path)
    except Exception as e:
        return f"路径解析失败: {e}"

    # 1. 路径穿越
    if has_traversal_component(path):
        return f"路径包含遍历组件（..），已阻断: {path}"

    # 2. 系统敏感路径
    for sensitive in _SENSITIVE_WRITE_PATHS:
        sensitive_expanded = os.path.expanduser(sensitive)
        if resolved.startswith(sensitive_expanded):
            return f"禁止写入系统敏感路径: {sensitive}"

    # 3. 凭据文件
    filename = os.path.basename(resolved)
    if filename in _CREDENTIAL_FILES:
        return f"禁止写入凭据文件: {filename}"

    # 4. 项目关键文件（仅在项目根目录下检测）
    project_root = _find_project_root()
    if project_root:
        project_resolved = str(Path(project_root).resolve())
        if resolved.startswith(project_resolved):
            # 在项目目录内，检查关键文件
            rel = os.path.relpath(resolved, project_resolved)
            if rel in _PROJECT_CRITICAL_FILES:
                return f"禁止写入项目关键文件: {rel}"

    # 5. 路径在项目根之外不做硬阻断（仅作为额外安全提示）
    # 不在允许目录内的路径仍允许写入——硬阻断由上面的模式匹配负责
    return None  # 安全


def assert_safe_write(path: str) -> None:
    """检查写入路径，安全则静默通过，不安全则抛 ValueError。

    Args:
        path: 要写入的文件路径

    Raises:
        ValueError: 路径不安全时的详细描述
    """
    reason = check_sensitive_write(path)
    if reason:
        raise ValueError(f"Write denied: {reason}")


def resolve_safe_path(path: str, allowed_root: str) -> tuple[Optional[str], Optional[str]]:
    """安全解析路径：展开 ~、检查遍历、验证在 allowed_root 内。

    Args:
        path: 用户提供的路径
        allowed_root: 允许的根目录

    Returns:
        (None, error): 路径不安全，error 是原因
        (resolved, None): 路径安全且已解析
    """
    try:
        resolved = _normalize_path(path)
    except Exception as e:
        return None, f"路径解析失败: {e}"

    if has_traversal_component(path):
        return None, f"路径包含遍历组件: {path}"

    err = validate_within_dir(resolved, allowed_root)
    if err:
        return None, err

    return resolved, None

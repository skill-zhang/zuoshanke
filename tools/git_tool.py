"""Git Tool — Agent Loop 的 Git 操作工具

提供 git add/commit/status/diff 四个接口，供 LLM 在自开发场景中提交代码。

使用场景：
- 开发完成后提交代码变更
- 查看当前工作区状态
- 查看未提交的 diff

NOTES:
- Git 仅在本地使用（无远端推送）
- repo_path 默认 ~/zuoshanke
"""

import json
import os
import subprocess
from pathlib import Path

# ── 默认仓库路径 ──
DEFAULT_REPO = os.path.expanduser("~/zuoshanke")

# ── OpenAI Function-Calling Schemas ──

GIT_STATUS_SCHEMA = {
    "name": "git_status",
    "description": (
        "查看 Git 工作区状态（未跟踪/已修改/待提交的文件列表）。"
        "适合在做任何改动前先看看当前状态，确认分支和未提交变更。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Git 仓库路径（默认 ~/zuoshanke）",
                "optional": True,
            },
        },
    },
}

GIT_COMMIT_SCHEMA = {
    "name": "git_commit",
    "description": (
        "提交代码变更到本地 Git 仓库。自动执行 git add 后 commit。"
        "提交前建议先调 git_status 确认变更内容。"
        "注意：提交是本地操作，不推送远端。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "提交信息，简洁描述做了什么",
            },
            "add_all": {
                "type": "boolean",
                "description": "是否 git add -A（自动暂存所有变更），默认 true",
                "optional": True,
            },
            "path": {
                "type": "string",
                "description": "Git 仓库路径（默认 ~/zuoshanke）",
                "optional": True,
            },
        },
        "required": ["message"],
    },
}

GIT_DIFF_SCHEMA = {
    "name": "git_diff",
    "description": (
        "查看工作区未暂存的 diff（有哪些具体改动）。比 git_status 更详细——"
        "可以查看改动了哪些代码行。适合提交前确认改动内容。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "是否查看已暂存（staged）的 diff，默认 false（显示未暂存）",
                "optional": True,
            },
            "path": {
                "type": "string",
                "description": "Git 仓库路径（默认 ~/zuoshanke）",
                "optional": True,
            },
        },
    },
}


def _run_git(args: list[str], repo_path: str) -> dict:
    """执行 git 命令，返回结构化结果"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        success = result.returncode == 0
        return {
            "success": success,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Git 命令超时 (30s)", "exit_code": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Git 未安装", "exit_code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def git_status(path: str = "") -> str:
    """查看 Git 工作区状态"""
    repo = path or DEFAULT_REPO
    if not os.path.isdir(os.path.join(repo, ".git")):
        return json.dumps({
            "error": f"不是 Git 仓库: {repo}",
            "success": False,
        }, ensure_ascii=False)

    result = _run_git(["status"], repo)
    if not result["success"]:
        return json.dumps(result, ensure_ascii=False)

    # 同时获取简短状态便于 AI 解析
    short = _run_git(["status", "--short"], repo)

    # 获取当前分支名
    branch = _run_git(["branch", "--show-current"], repo)
    branch_name = branch["stdout"] if branch["success"] else "unknown"

    return json.dumps({
        "success": True,
        "branch": branch_name,
        "status": result["stdout"],
        "short_status": short["stdout"] if short["success"] else "",
        "has_changes": bool(short["stdout"].strip()) if short["success"] else False,
        "repo": repo,
    }, ensure_ascii=False)


def git_commit(message: str, add_all: bool = True, path: str = "") -> str:
    """提交代码变更"""
    repo = path or DEFAULT_REPO
    if not message or not message.strip():
        return json.dumps({"error": "提交信息不能为空", "success": False}, ensure_ascii=False)

    if not os.path.isdir(os.path.join(repo, ".git")):
        return json.dumps({
            "error": f"不是 Git 仓库: {repo}",
            "success": False,
        }, ensure_ascii=False)

    try:
        if add_all:
            add_result = _run_git(["add", "-A"], repo)
            if not add_result["success"]:
                return json.dumps(add_result, ensure_ascii=False)

        # 检查是否有东西可提交
        status_result = _run_git(["status", "--short"], repo)
        if not status_result["success"]:
            return json.dumps(status_result, ensure_ascii=False)
        if not status_result["stdout"].strip():
            return json.dumps({
                "success": True,
                "message": "无变更需要提交",
                "committed": False,
            }, ensure_ascii=False)

        commit_result = _run_git(
            ["commit", "-m", message.strip()],
            repo,
        )
        if commit_result["success"]:
            return json.dumps({
                "success": True,
                "message": message.strip(),
                "committed": True,
                "output": commit_result["stdout"],
                "repo": repo,
            }, ensure_ascii=False)
        else:
            return json.dumps(commit_result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, ensure_ascii=False)


def git_diff(staged: bool = False, path: str = "") -> str:
    """查看 diff"""
    repo = path or DEFAULT_REPO
    if not os.path.isdir(os.path.join(repo, ".git")):
        return json.dumps({
            "error": f"不是 Git 仓库: {repo}",
            "success": False,
        }, ensure_ascii=False)

    args = ["diff"]
    if staged:
        args.append("--staged")

    result = _run_git(args, repo)
    if result["success"]:
        return json.dumps({
            "success": True,
            "diff": result["stdout"],
            "staged": staged,
            "has_diff": bool(result["stdout"].strip()),
        }, ensure_ascii=False)
    else:
        return json.dumps(result, ensure_ascii=False)

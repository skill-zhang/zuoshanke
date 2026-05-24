# 轻量安全扫描器 — 方案设计

> 只监视破坏行为的高危命令扫描器。不搞规则引擎，纯正则匹配，命中即阻断。

---

## 1. 动机

坐山客的 Agent Loop 中，LLM 通过 terminal 工具执行 shell 命令。虽然用户在场监督 + git 兜底构成了核心安全防线，但**高危命令一旦执行，后果不可接受**：

- `rm -rf /` → WSL 系统全灭
- `DROP TABLE` → 数据库表结构+数据消失
- `git reset --hard HEAD`（有未提交更改）→ 编码半天的成果全丢
- `rm -rf ~/.ssh/authorized_keys` → 远程服务器 SSH 锁定

**这些命令 99.9% 不会触发**——正常 LLM 推理不会产生它们。但如果 LLM 出现路径幻觉、上下文混淆等罕见但真实的故障，一条命令就能让几小时的工作成果付之东流。

**不搞 Tirith 那种企业级规则引擎**：Tirith 规则密集、误报多、弹窗频繁，导致用户肌肉反射式 `/approve session`，反而让真正的警告被淹没。我们要的是**极少数真正高危的模式**，每次弹窗用户都会停下来认真看一眼。

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **只防破坏，不防使用** | 只匹配 `rm -rf /` 级别，不拦截 `rm file`、`pip install` 等正常操作 |
| **命中即阻断** | 高危命令必须用户 approve 后才能执行，不等同警告 |
| **零误报** | 规则精挑细选，无歧义（纯字面正则，无模糊匹配） |
| **纯正则，不调 LLM** | LLM 分析 = 额外 token + 延迟 + 误判，不值得 |
| **智能降级** | 某些场景下高危命令其实安全（如工作区干净的 `git reset --hard`）→ 降级为警告不阻断 |
| **无人值守拒绝** | cron job / 后台任务命中高危 → 直接拒绝，不等用户 |

---

## 3. 架构

### 3.1 注入点

扫描器插入在 `execute_tool()` 的 `terminal` 工具执行前：

```
用户/LLM → agent_loop 发出 terminal 命令
  ↓
扫描器(command) → 匹配 HIGH_RISK_PATTERNS
  ├── 无匹配 → 直接执行（零开销）
  ├── 匹配 + 可降级 → 执行降级逻辑
  │   ├── 条件满足 → 警告日志 + 直接执行
  │   └── 条件不满足 → 阻断，等用户 approve
  └── 匹配 + 不可降级 → 阻断，等用户 approve
```

### 3.2 扫描器模块

```python
# agent_core/command_scanner.py

"""高危命令扫描器 — 纯正则匹配，命中即阻断"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══ 高危命令模式（同步自 zuoshanke-security-philosophy skill）════
# 完整清单与分类: 见 skill references/dangerous-commands-list.md

HIGH_RISK_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern, category, description)

    # ── 文件系统毁灭 ──
    (r'\brm\s+(?:-[rfFR]+\s+)?/\b', 'filesystem', '递归删除根目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?--no-preserve-root', 'filesystem', '跳过 --no-preserve-root 保护删除根目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?~(?:\s|$)', 'filesystem', '删除用户主目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/boot\b', 'filesystem', '删除 /boot → 系统无法启动'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/etc\b', 'filesystem', '删除 /etc → 系统配置全灭'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/var\b', 'filesystem', '删除 /var → 日志/数据库全灭'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/usr\b', 'filesystem', '删除 /usr → 用户程序全灭'),
    (r'\bchmod\s+-R\s+[0-7]{3}\s+/\b', 'filesystem', '递归 chmod 根目录 → 系统权限崩坏'),
    (r'\bchown\s+-R\s+\w+:\w+\s+/\b', 'filesystem', '递归 chown 根目录 → 系统权限崩坏'),

    # ── 磁盘毁灭 ──
    (r'\bdd\s+if=/dev/zero\s+of=/dev/sd', 'disk', 'dd 零覆写系统盘'),
    (r'\bdd\s+if=/dev/random\s+of=/dev/sd', 'disk', 'dd 随机覆写系统盘'),
    (r'\bmkfs\b.*/dev/sd', 'disk', '格式化系统盘分区'),
    (r'\bshred\s+/dev/sd', 'disk', '安全擦除系统盘'),
    (r'\bwipefs\b.*/dev/sd', 'disk', '清除文件系统签名'),

    # ── Git 毁灭 ──
    (r'\bgit\s+reset\s+--hard\b', 'git', 'git reset --hard（有未提交更改时数据丢失）'),
    (r'\bgit\s+clean\s+-f[d]?\b', 'git', '强制删除所有未跟踪文件'),
    (r'\bgit\s+branch\s+-D\s+main\b', 'git', '强制删除 main 分支引用'),
    (r'\bgit\s+push\s+\w+\s+:main\b', 'git', '删除远程 main 分支'),
    (r'\bgit\s+update-ref\s+-d\b', 'git', '删除当前分支指针'),
    (r'\bgit\s+filter-branch\b', 'git', '强制重写 Git 历史'),

    # ── 数据库毁灭 ──
    (r'\bDROP\s+DATABASE\b', 'database', '删除整个数据库'),
    (r'\bDROP\s+TABLE\b', 'database', '删除表（结构+数据全灭）'),
    (r'\bDROP\s+SCHEMA\b', 'database', '删除模式'),
    (r'\bTRUNCATE\b', 'database', '清空表数据（不可回滚）'),
    (r'\bDELETE\s+FROM\b(?!.*\bWHERE\b)', 'database', 'DELETE FROM 无 WHERE → 全表数据丢失'),
    (r'\bUPDATE\s+\w+\s+SET\b(?!.*\bWHERE\b)', 'database', 'UPDATE 无 WHERE → 全表数据被覆盖'),

    # ── 网络自锁 ──
    (r'\biptables\s+-F\b', 'network', '清空 iptables 规则（远程可能自锁）'),
    (r'\biptables\s+-P\s+INPUT\s+DROP\b', 'network', '默认拒绝入站（远程 SSH 自锁）'),
    (r'\bufw\s+disable\b', 'network', '关闭 ufw 防火墙（远程自锁）'),
    (r'\bsystemctl\s+stop\s+ssh[d]?\b', 'network', '停止 SSH 服务（远程自锁）'),
    (r'\bip\s+link\s+set\s+\w+\s+down\b', 'network', '关闭网络接口（远程断网）'),

    # ── Docker ──
    (r'\bdocker\s+system\s+prune\b.*--volumes', 'docker', '清理 Docker 所有数据（含卷）'),
    (r'\bdocker\s+rm\s+-f\s+\$\(docker\s+ps', 'docker', '强制删除所有容器'),
    (r'\bdocker\s+rmi\s+-f\s+\$\(docker\s+images', 'docker', '强制删除所有镜像'),
    (r'\bdocker\s+volume\s+rm\b.*\$\(docker\s+volume', 'docker', '删除所有数据卷'),
    (r'\bdocker\s+compose\s+down\s+-v\b', 'docker', 'compose down 删除数据卷'),

    # ── 包管理器毁灭 ──
    (r'\bapt\s+remove\s+(python3?|systemd|libc6|apt)\b', 'package', '删除系统关键包'),
    (r'\bdpkg\s+--purge\s+(python3?|systemd|libc)\b', 'package', '彻底移除系统关键包'),
    (r'\bpacman\s+-Rns?\s+(python|systemd|glibc)\b', 'package', 'Arch 移除关键包'),

    # ── 配置/认证毁灭 ──
    (r'\brm\s+(?:-[rf]+\s+)?~?/\.ssh/', 'config', '删除 SSH 密钥/配置 → 远程自锁'),
    (r'\brm\s+(?:-[rf]+\s+)?/etc/(?:passwd|shadow|sudoers|resolv\.conf|ssl)', 'config', '删除系统关键配置'),
    (r'\bpasswd\s+-l\s+root\b', 'config', '锁定 root 账号'),
    (r'\busermod\s+-s\s+/sbin/nologin\s+root\b', 'config', '禁止 root 登录'),
    (r'\bkill\s+-9\s+-1\b', 'config', '广播 SIGKILL 杀死所有进程'),
    (r'\bpkill\s+-9\s+-u\b', 'config', '杀死指定用户所有进程'),
    (r'\brm\s+(?:-[rf]+\s+)?/etc/(?:nginx|apache2|mysql)\b', 'config', '删除服务配置目录'),
]


def check_git_clean(cwd: str = None) -> bool | None:
    """检查 Git 工作区是否干净（无未提交更改）
    
    Returns:
        True: 工作区干净
        False: 有未提交更改
        None: 不在 git 仓库中
    """
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, timeout=5,
            cwd=cwd,
        )
        if result.returncode != 0:
            return None  # 不是 git 仓库
        return len(result.stdout.strip()) == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_is_remote_ssh() -> bool:
    """检查当前是否通过 SSH 远程连接
    
    Returns:
        True: 当前是远程 SSH 连接
        False: 本地连接
    """
    import os
    return bool(os.environ.get('SSH_CONNECTION') or 
                os.environ.get('SSH_CLIENT') or 
                os.environ.get('SSH_TTY'))


def scan_command(command: str, cwd: str = None) -> dict | None:
    """扫描命令，返回匹配的高危模式详情或 None
    
    Args:
        command: 要执行的 shell 命令
        cwd: 命令执行的工作目录（用于 git 状态检测降级）
    
    Returns:
        None: 安全，直接执行
        dict: {
            "block": True | False,  # True=必须阻断, False=仅警告
            "category": str,        # 高危类别
            "pattern": str,         # 匹配到的正则
            "description": str,     # 后果描述
            "reason": str,          # 给用户看的解释
        }
    """
    for pattern, category, desc in HIGH_RISK_PATTERNS:
        m = re.search(pattern, command, re.IGNORECASE)
        if not m:
            continue

        # ── git 类：有降级可能 ──
        if category == 'git' and cwd:
            clean = check_git_clean(cwd)
            if clean is True:
                logger.info(f"高危命令降级(git工作区干净): {command[:80]}")
                return {
                    "block": False,
                    "category": category,
                    "pattern": pattern,
                    "description": desc,
                    "reason": f"Git 工作区干净，{desc} 不会丢失未提交数据。已放行。",
                }

        # ── 网络自锁类：远程环境才阻断 ──
        if category == 'network':
            if not check_is_remote_ssh():
                logger.info(f"高危命令降级(本地环境): {command[:80]}")
                return {
                    "block": False,
                    "category": category,
                    "pattern": pattern,
                    "description": desc,
                    "reason": "当前为本地环境（非远程 SSH），网络操作不会自锁。已放行。",
                }

        # ── 不可降级 → 阻断 ──
        logger.warning(f"高危命令阻断: [{category}] {command[:120]}")
        return {
            "block": True,
            "category": category,
            "pattern": pattern,
            "description": desc,
            "reason": f"高危操作【{desc}】。请确认是否执行：",
        }

    return None
```

### 3.3 注入点修改

**`agent_core/tool_executor.py`** 的 `execute_tool()` 函数，在终端命令执行前插入扫描：

```python
def execute_tool(name: str, params: dict, ...) -> dict:
    # ... 现有逻辑 ...
    
    if name == "terminal":
        command = params.get("command", "")
        if command:
            from agent_core.command_scanner import scan_command
            result = scan_command(command, workdir)
            if result and result["block"]:
                # 阻断：返回错误给 LLM，或弹窗等用户确认
                return {
                    "success": False,
                    "result": None,
                    "error": result["reason"],
                    "high_risk": result
                }
    
    # ... 现有执行逻辑 ...
```

### 3.4 用户确认流程

```
LLM 调 terminal("rm -rf /")
  ↓
scan_command() → 命中 filesystem 类 → block=True
  ↓
execute_tool() 返回 {"success": False, "error": "...", "high_risk": {...}}
  ↓
agent_loop 收到响应
  ├── 场景聊天 → 在消息流中插入一个特殊事件
  │   {
  │     "event": "command_approval",
  │     "data": {
  │       "command": "rm -rf /",
  │       "risk": "高危操作【递归删除根目录】",
  │       "approved": false
  │     }
  │   }
  ├── 前端收到 → 显示确认对话框
  │   └── 用户点「批准」→ 重新发送 terminal 命令（绕过扫描器）
  │   └── 用户点「拒绝」→ 消息流提示命令被拒绝
  └── 非聊天场景（cron/后台）→ 直接拒绝
```

---

## 4. 降级逻辑详解

### 4.1 Git 类降级

```
git reset --hard HEAD   ← 命中
  ↓
check_git_clean(cwd)
  ├── True  → 工作区干净 → 降级为警告，放行
  ├── False → 有未提交改动 → 阻断
  └── None  → 不是 git 仓库 → 阻断（保守策略）
```

降级原理：git reflog 可以恢复 `git reset --hard` 丢失的 commit 引用，但无法恢复 **未提交的工作区改动**。如果工作区干净，reset --hard 最多丢掉几个 commit（可通过 `git reflog` + `git cherry-pick` 恢复），后果可控。

### 4.2 网络自锁降级

```
iptables -F   ← 命中
  ↓
check_is_remote_ssh()
  ├── True  → 有 SSH 连接 → 阻断（清空规则可能暴露服务或断开当前连接）
  └── False → 本地 → 降级（重启即可恢复）
```

### 4.3 包管理器降级（暂不实现，未来可加）

如果 `apt remove python3` 但 `--dry-run` 模式 → 降级放行。当前不实现，因为 `apt remove` 本身已经够少见了，先全阻断。

---

## 5. 拦截 vs 报告

| 运行模式 | 高危命中 | 行为 |
|---------|---------|------|
| 场景聊天 | 阻断 | 弹 approval dialog，等用户操作 |
| 频道/闲聊 | 阻断 | 同上（走 gateway 消息交互） |
| cron job | 拒绝 | 直接拒绝，记录日志，报告失败 |
| 后台任务 | 拒绝 | 直接拒绝 |

所有模式都会记录日志：`WARNING [command_scanner] 高危命令阻断: [category] command`

---

## 6. 规则维护

规则主来源：`tools/command_scanner.py` 中的 `HIGH_RISK_PATTERNS` 元组。

**参考文档**（授权引用）：`zuoshanke-security-philosophy` skill 的 `references/dangerous-commands-list.md` — 该文档维护了完整的分类描述清单，与代码规则保持同步。

**增加规则的流程**：

1. 在 `dangerous-commands-list.md` 中补充分类和描述
2. 在 `tools/command_scanner.py` 中加对应的正则模式
3. 编写单元测试覆盖新规则

**删除规则的流程**（罕见）：

1. 确认该命令即使误执行后果也有限
2. 从两边同步删除

---

## 7. 文件改动清单

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `backend/agent_core/command_scanner.py` | 🆕 新增 — 扫描器核心（模式 + 降级逻辑） | ~120 |
| `backend/agent_core/tool_executor.py` | 修改 `execute_tool()` — terminal 命令前插入扫描 | ~15 |
| `backend/router/scene_stream.py` | 修改 SSE 事件处理 — 添加 `command_approval` 事件 | ~10 |
| `frontend/src/api/client.ts` | 新增 CommandApproval 类型 | ~10 |
| `frontend/src/components/ChatView.tsx` | 新增 approval dialog 组件 | ~40 |
| `tests/test_command_scanner.py` | 🆕 新增 — ~50 条单元测试 | ~80 |

**总计新增约 275 行，修改 3 个现有文件，零重构。**

---

## 8. 测试

| 测试用例 | 期望 |
|---------|------|
| `rm -rf /` | 阻断 |
| `rm -rf /var/log` | 阻断 |
| `rm file.txt` | 放行 |
| `rm -rf node_modules` | 放行 |
| `git reset --hard HEAD` (工作区脏) | 阻断 |
| `git reset --hard HEAD` (工作区干净) | 降级放行 |
| `git commit -m "fix"` | 放行 |
| `DROP TABLE users;` | 阻断 |
| `SELECT * FROM users` | 放行 |
| `pip install requests` | 放行 |
| `dd if=/dev/zero of=/dev/sda` | 阻断 |
| `dd if=/dev/zero of=test.img bs=1M count=10` | 放行（目标不是 sd* 设备） |
| 空字符串 | 无匹配 |
| 普通命令 `ls -la` | 放行 |
| `sudo rm -rf /` | 阻断（sudo 前缀不影响） |

---

## 9. 边界情况

| 情况 | 处理 |
|------|------|
| 命令中包含注释 `rm -rf / # dangerous` | 先 strip 注释再扫描？→ 不 strip，整条匹配（注释里的 `/` 也会触发） |
| 变量替换 `rm -rf $TARGET` | 不解析变量，只匹配字面量。如果 `$TARGET` 被解析为 `/` 则无法预检 → 可接受（变量注入需要专门手段） |
| 管道 `echo y \| rm -rf /` | 整条匹配 → 命中 |
| 子 shell `$(rm -rf /)` | 整条匹配 → 命中 |
| SQL 在 Python 字符串中 `cursor.execute("DROP TABLE users")` | 不匹配（不是直接 terminal 命令） → 工具层安全不在本扫描范围 |
| WSL 路径 `/mnt/c/Windows` | `rm -rf /mnt/c/Windows` 不会匹配 `/` 模式 → ⚠️ 需要加 `/mnt/` 规则？用户决定不加（不影响 WSL 系统，只影响 Windows） |

---

## 10. 实施步骤

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | 新建 `backend/agent_core/command_scanner.py` | 无 |
| 2 | 修改 `backend/agent_core/tool_executor.py` — 注入扫描 | Step 1 |
| 3 | 修改 `backend/router/scene_stream.py` — approval 事件 | Step 2 |
| 4 | 前端 approval dialog 组件 | Step 3 |
| 5 | 测试文件 `tests/test_command_scanner.py` | Step 1 |
| 6 | 验收测试（BDT 拨测） | Step 4 |

---

## 11. 设计文档

- `docs/design/command-scanner.md` — 本文
- `zuoshanke-security-philosophy` skill → `references/dangerous-commands-list.md` — 完整清单（授权引用）
- `zuoshanke-security-philosophy` skill → `SKILL.md` — 安全哲学总纲

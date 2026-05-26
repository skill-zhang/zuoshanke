"""高危命令扫描器 — 纯正则匹配，命中即阻断

只监视破坏行为的高危命令，不搞规则引擎。
设计文档: docs/design/command-scanner.md
"""

import re
import logging
import subprocess
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ═══ 高危命令模式 ═══
# (pattern, category, description)
HIGH_RISK_PATTERNS: list[tuple[str, str, str]] = [
    # ── 文件系统毁灭 ──
    (r'\brm\s+(?:-[rfFR]+\s+)?/', 'filesystem', '递归删除根目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?--no-preserve-root', 'filesystem', '跳过 --no-preserve-root 保护删除根目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?~(?:\\s|$)', 'filesystem', '删除用户主目录'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/boot\b', 'filesystem', '删除 /boot → 系统无法启动'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/etc\b', 'filesystem', '删除 /etc → 系统配置全灭'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/var\b', 'filesystem', '删除 /var → 日志/数据库全灭'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/usr\b', 'filesystem', '删除 /usr → 用户程序全灭'),
    (r'\bchmod\s+-R\s+[0-7]{3}\s+/', 'filesystem', '递归 chmod 根目录 → 系统权限崩坏'),
    (r'\bchown\s+-R\s+\w+:\w+\s+/', 'filesystem', '递归 chown 根目录 → 系统权限崩坏'),
    (r'\brm\s+(?:-[rfFR]+\s+)?/etc/(?:nginx|apache2|mysql)\b', 'filesystem', '删除服务配置目录'),

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

    # ── 凭据外泄（exfiltration）──
    (r'curl\s+[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)[^}]*\}?', 'exfil', 'curl 外泄 API Key/Token 到外部服务器'),
    (r'wget\s+[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', 'exfil', 'wget 外泄 API Key/Token 到外部服务器'),
    (r'(?:cat|base64|head|tail)\s+(?:.*\|\s*)?(?:curl|wget|nc|ncat)', 'exfil', '通过管道将本地文件内容外泄到外部服务器'),
    (r'(?:\.env|credentials|auth\.json|\.netrc|\.pgpass)\s*\|(?!\s*grep)', 'exfil', '读取敏感文件并通过管道外泄'),
    (r'\b(?:nc|ncat)\s+(?:-e|--exec)\s', 'exfil', 'netcat 反向 shell 外泄'),
    (r'base64\s+.*(?:\.env|credentials|\.netrc)', 'exfil', 'base64 编码敏感文件 → 可用于外泄'),

    # ── SSRF curl（curl 到私有/元数据地址）──
    (r'curl\s+.*169\.254\.169\.254', 'ssrf', 'curl 到云元数据服务（169.254.169.254）'),
    (r'wget\s+.*169\.254\.169\.254', 'ssrf', 'wget 到云元数据服务（169.254.169.254）'),
    (r'curl\s+.*metadata\.google\.internal', 'ssrf', 'curl 到 GCP 元数据服务'),
    (r'curl\s+.*metadata\.goog', 'ssrf', 'curl 到 GCP 元数据服务'),
    (r'curl\s+.*100\.100\.100\.200', 'ssrf', 'curl 到阿里云元数据服务'),
    (r'curl\s+.*fd00:ec2::254', 'ssrf', 'curl 到 AWS IMDS IPv6 端点'),
    (r'wget\s+.*metadata\.google\.internal', 'ssrf', 'wget 到 GCP 元数据服务'),
    (r'wget\s+.*100\.100\.100\.200', 'ssrf', 'wget 到阿里云元数据服务'),
]


def check_git_clean(cwd: Optional[str] = None) -> Optional[bool]:
    """检查 Git 工作区是否干净（无未提交更改）

    Returns:
        True: 工作区干净
        False: 有未提交更改
        None: 不在 git 仓库中
    """
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
    return bool(os.environ.get('SSH_CONNECTION') or
                os.environ.get('SSH_CLIENT') or
                os.environ.get('SSH_TTY'))


def scan_command(command: str, cwd: Optional[str] = None) -> Optional[dict]:
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
            "reason": f"⚠️ 高危操作【{desc}】\n\n命令: `{command[:200]}`\n\n请确认是否执行：",
        }

    return None

# 分身自毁防护（Backend Self-Destruction Guard）

> 分身通过 `run_code(language="bash")` 执行操作系统命令时，可能杀死坐山客后端进程
> （如 `lsof -ti:8002 | xargs kill -9`），导致当前 SSE 断连、任务卡超时。

## 问题

分身执行 bash 命令杀死后端进程的链条：

```
分身 run_code("bash", code="lsof -ti:8002 | xargs kill -9 ...")
  ↓ command_scanner 扫描
  ↓ (缺规则时) 漏检 → 执行
  ↓ 后端进程被杀死
  ↓ SSE 连接断 → 分身卡住 → 超时
```

## 防护方案

在 `backend/agent_core/command_scanner.py` 的 `HIGH_RISK_PATTERNS` 中新增
`category='service'` 类规则，**不可降级**（始终阻断）：

| 规则 | 正则 | 目标 |
|------|------|------|
| lsof+xargs kill | `lsof\s+-ti\s*:?\s*8\d{3}\s*\|\s*xargs\s+kill` | 通过端口查找并用 xargs 杀死进程 |
| kill+端口 | `kill\s+.*\b8\d{3}\b` | 按端口号 kill（8000/8001/8002） |
| xargs kill -9 | `xargs\s+kill\s+-9` | 批量终止进程的通用模式 |
| systemctl 停服务 | `systemctl\s+(?:stop\|restart)\s+(?:zuoshanke\|agai-maas\|backend)` | 通过 systemd 停后端 |
| cd zuoshanke+重启 | `cd\s+~[/\w]*zuoshanke.*&&.*python3\s+backend/main\.py` | 手动重启坐山客 |
| cd agai-maas+重启 | `cd\s+~[/\w]*agai-maas.*&&.*python3\s+-m\s+backend\.main` | 手动重启 agai-maas |

## 为什么不直接用 SSE 自动重试

前端已有 Layer 3 SSE 自动重试（`appStore.ts` 的 `_retryStream`），但：
- 后端重启后 Agent Loop 的 Generator 状态丢失（在内存中）
- 分身需要重新发起完整请求，无法恢复上下文
- 父 agent 的 delegate_task 线程也会丢失

所以阻断比重试更可靠。

## 配套文档

- 现有自修改防护系统：`docs/design/self-modification-guard.md`
- 命令扫描器设计：`docs/design/command-scanner.md`
- 进程隔离规划：`docs/design/schema-v1.7.md`（Layer 6 沙箱）

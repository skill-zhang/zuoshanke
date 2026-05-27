"""cloudflare_tunnel_setup — Cloudflare Tunnel 公网访问配置生成器

功能：生成 cloudflared tunnel 完整配置，
     支持 quick tunnel（trycloudflare.com）和 named tunnel（自定义域名），
     Caddy 反向代理 + Basic Auth 配置，
     systemd 自启服务，
     本地 cloudflared 安装检测

使用场景：
  - 在本地开发环境（无公网 IP）通过 Cloudflare Tunnel 实现公网访问
  - 给坐山客工作台（或任何本地 Web 服务）开公网入口
  - 需要 HTTPS + 认证保护

作者: 坐山客工具系统
"""

import json
import shutil
import subprocess
import textwrap
from typing import Optional


def cloudflare_tunnel_setup(
    mode: str = "quick",
    domain: str = "",
    local_port: int = 5173,
    auth_enabled: bool = True,
    auth_user: str = "admin",
    auth_pass: str = "",
    service_type: str = "vite",
    api_port: int = 8000,
    api_path: str = "/api",
    check_cloudflared: bool = True,
) -> str:
    """生成 Cloudflare Tunnel 公网访问配置

    根据模式（quick/named）、本地端口、认证参数等，生成完整的公网暴露方案。
    包括：cloudflared 安装/运行命令、Caddyfile 配置、systemd 服务、
    前端 vite.config.ts 调整说明。

    Args:
        mode: "quick"（临时隧道，免费，无需域名）或 "named"（永久隧道，需自有域名）
        domain: 自定义域名（mode="named" 时必填）
        local_port: 本地服务端口（默认 5173，Vite 开发服务器）
        auth_enabled: 是否启用 Basic Auth 认证（默认开启）
        auth_user: Basic Auth 用户名（默认 admin）
        auth_pass: Basic Auth 密码（建议设置强密码）
        service_type: 本地服务类型（vite / nginx / other）
        api_port: API 后端端口（默认 8000，仅 vite 模式需要区分前后端）
        api_path: API 后端路径前缀（默认 /api）
        check_cloudflared: 是否检测本地 cloudflared 安装（默认开启）

    Returns:
        JSON 字符串，包含 sections: install_check, tunnel_config,
        caddy_config, systemd_service, vite_config, setup_guide
    """
    # ── 参数校验 ──
    if mode == "named" and not domain:
        return json.dumps({
            "success": False,
            "error": "named 模式必须提供 domain 参数（已在 Cloudflare 管理的域名）",
        }, ensure_ascii=False)

    result = {
        "success": True,
        "mode": mode,
        "domain": domain or f"*.trycloudflare.com",
        "local_port": local_port,
        "auth_enabled": auth_enabled,
        "auth_user": auth_user,
        "service_type": service_type,
        "sections": {},
    }

    # ── 本地 cloudflared 检测 ──
    install_check = {"installed": False}
    if check_cloudflared:
        cf_path = shutil.which("cloudflared")
        if cf_path:
            try:
                ver = subprocess.run(
                    [cf_path, "--version"],
                    capture_output=True, text=True, timeout=5
                )
                install_check = {
                    "installed": True,
                    "path": cf_path,
                    "version": ver.stdout.strip() if ver.returncode == 0 else "未知",
                }
            except Exception:
                install_check = {"installed": True, "path": cf_path, "version": "检测失败"}
        else:
            install_check = {
                "installed": False,
                "install_guide": "Linux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
            }
    result["sections"]["install_check"] = install_check

    # ── Tunnel 运行模式 ──
    tunnel_config = {
        "mode": mode,
        "type": "quick" if mode == "quick" else "named",
    }

    if mode == "quick":
        # Quick tunnel 不支持 Basic Auth，需要用 Caddy 前置
        tunnel_config["command"] = (
            f"cloudflared tunnel --url http://localhost:{local_port}"
        )
        tunnel_config["note"] = (
            "⚠️ Quick tunnel 不支持 --http-basic-auth 参数。"
            "如需认证，必须先启动 Caddy（见下方说明），"
            "再将 tunnel 指向 http://localhost:8080"
        )
        tunnel_config["caddy_required"] = auth_enabled
    else:
        # Named tunnel 步骤
        tunnel_config["steps"] = {
            "login": "cloudflared tunnel login",
            "create": f"cloudflared tunnel create zuoshanke-tunnel",
            "config": _named_tunnel_config(domain, local_port, auth_enabled),
            "dns": f"cloudflared tunnel route dns zuoshanke-tunnel {domain}",
            "run": "cloudflared tunnel run zuoshanke-tunnel",
        }
        tunnel_config["config_file_path"] = "~/.cloudflared/config.yml"
        tunnel_config["note"] = (
            "Named tunnel 的认证信息（cert.pem, tunnel credentials）"
            "存储在 ~/.cloudflared/ 目录下。运行前需先 login 授权。"
        )
    result["sections"]["tunnel_config"] = tunnel_config

    # ── Caddy 配置（Basic Auth + 反向代理） ──
    caddy_config = None
    if auth_enabled:
        caddyfile = _build_caddyfile(
            local_port=local_port,
            auth_user=auth_user,
            auth_pass=auth_pass or _suggest_password(),
            service_type=service_type,
            api_port=api_port,
            api_path=api_path,
        )
        caddy_config = {
            "path": "/tmp/Caddyfile",
            "content": caddyfile,
            "command_install": (
                "Linux: apt install -y caddy\n"
                "或 wget https://github.com/caddyserver/caddy/releases/latest -O /usr/bin/caddy"
            ),
            "command_run": "caddy run --config /tmp/Caddyfile --adapter caddyfile",
            "password_hash_command": f'caddy hash-password --plaintext {auth_pass or "your_password"}',
            "password_hashed_note": "将生成的哈希替换 Caddyfile 中的 password_hash 字段",
        }
    result["sections"]["caddy_config"] = caddy_config

    # ── 无 Caddy 时的直接访问配置 ──
    if not auth_enabled:
        result["sections"]["direct_access"] = {
            "quick_tunnel": f"cloudflared tunnel --url http://localhost:{local_port}",
            "note": "无认证，任何人拿到 tunnel URL 即可访问，建议仅用于临时测试",
        }

    # ── systemd 服务（持久化） ──
    systemd_service = _build_systemd(domain, local_port, auth_enabled, mode)
    result["sections"]["systemd_service"] = systemd_service

    # ── Vite 配置调整 ──
    vite_config = None
    if service_type == "vite":
        vite_config = {
            "file": "frontend/vite.config.ts",
            "required_setting": 'server: { allowedHosts: true }',
            "note": "Cloudflare Tunnel 的域名不是 localhost，Vite 默认 host 检查会拦截。添加 allowedHosts: true 放行任意域名。",
            "example_snippet": textwrap.dedent("""\
                export default defineConfig({
                  server: {
                    allowedHosts: true,      // 允许 Cloudflare Tunnel 等任意域名访问
                    port: 5173,
                    proxy: { "/api": "http://localhost:8000" },
                  },
                })
            """),
        }
    result["sections"]["vite_config"] = vite_config

    # ── 部署步骤总览 ──
    setup_guide = []
    step = 1

    setup_guide.append({
        "step": step, "action": "安装 cloudflared",
        "command": install_check.get("install_guide", "cloudflared 已安装"),
        "note": "如果已安装则跳过",
    })
    step += 1

    if auth_enabled:
        setup_guide.append({
            "step": step, "action": "安装 Caddy",
            "command": caddy_config["command_install"],
            "note": "Caddy 负责 Basic Auth + 反向代理",
        })
        step += 1

        setup_guide.append({
            "step": step, "action": "创建 Caddyfile",
            "command": f"将配置写入 {caddy_config['path']}",
            "note": f"用户: {auth_user}, 密码建议设强密码",
        })
        step += 1

        setup_guide.append({
            "step": step, "action": "启动 Caddy",
            "command": caddy_config["command_run"],
            "note": "Caddy 将在 :8080 监听，请求转发到 localhost:{local_port}",
        })
        step += 1

    if mode == "quick":
        tunnel_cmd = (
            f"cloudflared tunnel --url http://localhost:8080"
            if auth_enabled
            else f"cloudflared tunnel --url http://localhost:{local_port}"
        )
        setup_guide.append({
            "step": step, "action": "启动 quick tunnel",
            "command": tunnel_cmd,
            "note": "启动后终端会显示 trycloudflare.com URL",
        })
        step += 1
    else:
        setup_guide.append({
            "step": step, "action": "Cloudflare 登录授权",
            "command": tunnel_config["steps"]["login"],
            "note": "浏览器打开链接，授权你的 Cloudflare 账号",
        })
        step += 1
        setup_guide.append({
            "step": step, "action": "创建命名隧道",
            "command": tunnel_config["steps"]["create"],
        })
        step += 1
        setup_guide.append({
            "step": step, "action": "配置隧道",
            "command": f"编辑 {tunnel_config['config_file_path']}",
            "note": "参考上方 config.yml 示例",
        })
        step += 1
        setup_guide.append({
            "step": step, "action": "DNS 路由",
            "command": tunnel_config["steps"]["dns"],
        })
        step += 1
        setup_guide.append({
            "step": step, "action": "启动隧道",
            "command": tunnel_config["steps"]["run"],
            "note": "或将 systemd 服务启用后开机自启",
        })
        step += 1

    if service_type == "vite":
        setup_guide.append({
            "step": step, "action": "确认 Vite 配置",
            "command": "检查 vite.config.ts 中 allowedHosts 是否为 true",
            "note": "否则 Tunnel 域名访问会 403",
        })
        step += 1

    result["sections"]["setup_guide"] = setup_guide

    # ── 验证方法 ──
    result["sections"]["verification"] = {
        "basic_check": f"浏览器打开 Tunnel 域名，应看到页面内容",
        "auth_check": "如启用认证，未输入凭据时应弹出 HTTP 登录框（401）",
        "api_check": "打开开发者工具 → Network，确认 /api 请求返回 200 而非 HTML",
        "log_locations": {
            "cloudflared": "cloudflared 终端输出或 systemd journalctl -u cloudflared-tunnel",
            "caddy": "Caddy 终端输出或 journalctl -u caddy",
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def _check_cloudflared_local() -> dict:
    """检查本地是否已安装 cloudflared"""
    cf = shutil.which("cloudflared")
    if not cf:
        return {"installed": False}
    try:
        r = subprocess.run([cf, "--version"], capture_output=True, text=True, timeout=5)
        return {"installed": True, "path": cf, "version": r.stdout.strip()}
    except Exception:
        return {"installed": True, "path": cf, "version": "?"}


def _named_tunnel_config(domain: str, local_port: int, auth_enabled: bool) -> str:
    """生成 named tunnel 的 config.yml"""
    if auth_enabled:
        target = "localhost:8080"  # Caddy
    else:
        target = f"localhost:{local_port}"

    return textwrap.dedent(f"""\
    tunnel: zuoshanke-tunnel
    credentials-file: /root/.cloudflared/zuoshanke-tunnel.json

    ingress:
      - hostname: {domain}
        service: http://{target}
      - service: http_status:404
    """).rstrip()


def _build_caddyfile(
    local_port: int,
    auth_user: str,
    auth_pass: str,
    service_type: str,
    api_port: int,
    api_path: str,
) -> str:
    """生成 Caddyfile 配置"""
    lines = [
        ":8080 {",
        f"    # Basic Auth",
        f"    basicauth * {{",
        f"        {auth_user} $2a$14$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        f"    }}",
        f"",
        f"    # API 反向代理（必须在静态文件之前匹配）",
    ]

    if service_type == "vite":
        lines.extend([
            f"    handle_path {api_path}/* {{",
            f"        reverse_proxy localhost:{api_port}",
            f"    }}",
        ])
    else:
        lines.extend([
            f"    handle_path {api_path}/* {{",
            f"        reverse_proxy localhost:{api_port}",
            f"    }}",
        ])

    lines.extend([
        f"",
        f"    # 前端静态文件 + SPA fallback",
        f"    handle {{",
        f"        reverse_proxy localhost:{local_port}",
        f"    }}",
        f"}}",
    ])

    return "\n".join(lines)


def _build_systemd(domain: str, local_port: int, auth_enabled: bool, mode: str) -> dict:
    """生成 systemd 服务文件"""
    target = "localhost:8080" if auth_enabled else f"localhost:{local_port}"
    tunnel_cmd = f"cloudflared tunnel --url http://{target}"
    if mode == "named":
        tunnel_cmd = f"cloudflared tunnel run zuoshanke-tunnel"

    return {
        "file_path": "/etc/systemd/system/cloudflared-tunnel.service",
        "content": textwrap.dedent(f"""\
        [Unit]
        Description=Cloudflare Tunnel (zuoshanke)
        After=network.target

        [Service]
        Type=simple
        User=root
        ExecStart={tunnel_cmd}
        Restart=always
        RestartSec=5
        Environment=HOME=/root

        [Install]
        WantedBy=multi-user.target
        """),
        "enable_command": (
            "sudo systemctl daemon-reload\n"
            "sudo systemctl enable cloudflared-tunnel\n"
            "sudo systemctl start cloudflared-tunnel\n"
            "sudo systemctl status cloudflared-tunnel"
        ),
    }


def _suggest_password() -> str:
    """生成一个建议密码"""
    import string, random
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choice(chars) for _ in range(12))

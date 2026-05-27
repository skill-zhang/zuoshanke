"""frp_generate_setup — frp（Fast Reverse Proxy）内网穿透配置生成器

功能：生成 frp 服务端 (frps) 和客户端 (frpc) 的完整部署配置，
     支持 Docker 部署、systemd 自启、多代理协议（TCP/HTTP/HTTPS）、
     面板监控、认证配置

使用场景：
  - 有一台云 VPS（公网 IP），想穿透内网服务到公网
  - frp 是国内最主流的内网穿透方案，低延迟、稳定、可控

作者: 坐山客工具系统
"""

import json
import socket
import textwrap
from typing import Optional


def frp_generate_setup(
    server_ip: str = "",
    bind_port: int = 7000,
    dashboard_port: int = 7500,
    dashboard_user: str = "admin",
    dashboard_pwd: str = "",
    token: str = "",
    local_port: int = 5173,
    remote_port: int = 8080,
    proxy_type: str = "tcp",
    proxy_name: str = "zuoshanke-web",
    use_docker: bool = True,
    custom_domain: str = "",
    check_ports: bool = True,
) -> str:
    """生成 frp 内网穿透配置

    根据服务器 IP、端口、代理类型等参数，生成 frps（服务端）+ frpc（客户端）的
    完整配置方案。包括 Docker 部署命令、配置文件、systemd 服务、面板信息。

    Args:
        server_ip: 云服务器公网 IP（必填）
        bind_port: frps 绑定端口（默认 7000，frpc 连接用）
        dashboard_port: frps 管理面板端口（默认 7500）
        dashboard_user: 面板登录用户名（默认 admin）
        dashboard_pwd: 面板登录密码（建议设置）
        token: frps-frpc 认证令牌（建议设置）
        local_port: 本地服务端口（默认 5173，坐山客前端）
        remote_port: 公网映射端口（默认 8080）
        proxy_type: 代理协议 tcp/http/https（默认 tcp）
        proxy_name: 代理名称标识（默认 zuoshanke-web）
        use_docker: 是否使用 Docker 部署（默认 true）
        custom_domain: HTTP 代理时自定义域名（需 DNS 指向服务器）
        check_ports: 是否检测服务器端口连通性（默认开启）

    Returns:
        JSON 字符串，包含 sections: server_config, client_config,
        docker_commands, systemd_service, dashboard_info,
        port_check, setup_guide
    """
    if not server_ip:
        return json.dumps({
            "success": False,
            "error": "必须提供 server_ip 参数（云服务器公网 IP）",
        }, ensure_ascii=False)

    if not dashboard_pwd:
        dashboard_pwd = _suggest_password()
    if not token:
        token = _suggest_password()

    result = {
        "success": True,
        "server_ip": server_ip,
        "proxy_type": proxy_type,
        "proxy_name": proxy_name,
        "local_port": local_port,
        "remote_port": remote_port,
        "dashboard_port": dashboard_port,
        "dashboard_url": f"http://{server_ip}:{dashboard_port}",
        "sections": {},
    }

    # ── 端口检测 ──
    port_check = {}
    if check_ports:
        ports_to_check = [
            (bind_port, "frp 通信端口（必须开放）"),
            (dashboard_port, "管理面板端口（可选开放）"),
            (remote_port, f"服务映射端口（{proxy_type} 协议）"),
        ]
        for port, note in ports_to_check:
            status = _check_tcp_port(server_ip, port)
            port_check[str(port)] = {
                "protocol": "TCP",
                "note": note,
                "status": status,
                "hint": (
                    "✅ 已开放" if status == "open"
                    else "⛔ 未开放或防火墙拦截" if status == "timeout"
                    else "⚠️ 无法检测"
                ),
            }
    result["sections"]["port_check"] = port_check

    # ── frps（服务端）配置 ──
    frps_config = {
        "config_file": "/root/frp/frps.toml",
        "content": textwrap.dedent(f"""\
            bindPort = {bind_port}
            auth.token = "{token}"

            webServer.addr = "0.0.0.0"
            webServer.port = {dashboard_port}
            webServer.user = "{dashboard_user}"
            webServer.password = "{dashboard_pwd}"
            """),
        "note": "frp v2 使用 TOML 格式配置文件。如果需要 v1（INI 格式），路径改为 /root/frp/frps.ini",
    }
    result["sections"]["frps_config"] = frps_config

    # ── frpc（客户端）配置 ──
    proxy_block = _build_proxy_block(
        proxy_type, proxy_name, local_port, remote_port, custom_domain, server_ip
    )
    frpc_config = {
        "config_file": "/root/frp/frpc.toml",
        "content": textwrap.dedent(f"""\
            serverAddr = "{server_ip}"
            serverPort = {bind_port}
            auth.token = "{token}"

            {proxy_block}
            """),
        "note": (
            "将此文件放到有公网访问的内网机器（或同一台服务器的 Docker 中运行 frpc）。"
            "frpc 需要能连接 frps 的 {bind_port}端口。"
        ),
    }
    result["sections"]["frpc_config"] = frpc_config

    # ── Docker 部署 ──
    docker_commands = {}
    if use_docker:
        # frps
        docker_commands["frps"] = {
            "container_name": "frps",
            "command": textwrap.dedent(f"""\
            docker run -d --name frps --restart=always \\
              --network host \\
              -v /root/frp/frps.toml:/etc/frp/frps.toml \\
              snowdreamtech/frps
            """),
            "note": "使用 --network host 模式，frps 直接使用宿主机网络，自动暴露所有端口。",
        }
        # frpc
        docker_commands["frpc"] = {
            "container_name": "frpc",
            "command": textwrap.dedent(f"""\
            docker run -d --name frpc --restart=always \\
              --network host \\
              -v /root/frp/frpc.toml:/etc/frp/frpc.toml \\
              snowdreamtech/frpc
            """),
            "note": "frpc 可运行在任意能访问 frps 的机器上，不一定和 frps 在同一台。",
        }
        # 拉取镜像
        docker_commands["pull"] = "docker pull snowdreamtech/frps && docker pull snowdreamtech/frpc"
        docker_commands["image_source_note"] = (
            "国内建议用 DaoCloud 镜像：docker.m.daocloud.io/snowdreamtech/frps"
        )
    result["sections"]["docker_commands"] = docker_commands

    # ── systemd 服务（非 Docker 部署时用） ──
    systemd = _build_systemd_services(dashboard_port, bind_port, remote_port)
    result["sections"]["systemd_service"] = systemd

    # ── 面板信息 ──
    result["sections"]["dashboard_info"] = {
        "url": f"http://{server_ip}:{dashboard_port}",
        "username": dashboard_user,
        "password": dashboard_pwd,
        "note": "面板显示在线代理、流量统计、连接状态。建议在安全组限制面板访问来源 IP。",
    }

    # ── 验证方法 ──
    result["sections"]["verification"] = {
        "frps": f"curl http://{server_ip}:{dashboard_port}/api/serverinfo",
        "frpc": f"ssh root@{server_ip} 'docker logs frps --tail 20' | grep 'proxy added'",
        "service": f"浏览器打开 http://{server_ip}:{remote_port}（TCP 需客户端直连）",
    }

    # ── 部署步骤总览 ──
    setup_guide = [
        {"step": 1, "action": "登录云服务器",
         "command": f"ssh root@{server_ip}",
         "note": "在云控制台安全组开放 {bind_port}/{dashboard_port}/{remote_port} TCP"},
        {"step": 2, "action": "创建配置目录",
         "command": "mkdir -p /root/frp"},
        {"step": 3, "action": "写入 frps 配置",
         "command": f"将 frps.toml 写入 /root/frp/",
         },
        {"step": 4, "action": "启动 frps（Docker）",
         "command": docker_commands["frps"]["command"] if use_docker else systemd["frps"]["enable_command"],
         "note": "可用 docker ps 确认运行状态"},
        {"step": 5, "action": "验证服务端运行",
         "command": f"curl -u {dashboard_user}:{dashboard_pwd} http://{server_ip}:{dashboard_port}/api/serverinfo",
         "note": "应返回 JSON 格式的服务器状态"},
        {"step": 6, "action": "配置 frpc（内网机器）",
         "command": "将 frpc.toml 复制到内网机器 /root/frp/ 目录",
         "note": "frpc 需要在能访问 frps:bind_port 的内网机器上运行"},
        {"step": 7, "action": "启动 frpc",
         "command": docker_commands["frpc"]["command"] if use_docker else systemd["frpc"]["enable_command"],
         "note": "启动后去面板查看代理状态"},
        {"step": 8, "action": "验证穿透",
         "command": f"浏览器访问 http://{server_ip}:{remote_port}" if proxy_type in ("http", "https")
                   else f"telnet {server_ip} {remote_port} 或 nc -zv {server_ip} {remote_port}",
         "note": "TCP 代理需要客户端直连；HTTP 代理浏览器直接访问"},
    ]

    if proxy_type == "http" and custom_domain:
        setup_guide.append({
            "step": 9, "action": "配置自定义域名",
            "command": f"DNS 将 {custom_domain} 指向 {server_ip}",
            "note": "确保 frps.toml 中 vhostHTTPPort 已设置"
        })

    result["sections"]["setup_guide"] = setup_guide

    return json.dumps(result, ensure_ascii=False, indent=2)


def _build_proxy_block(
    proxy_type: str,
    proxy_name: str,
    local_port: int,
    remote_port: int,
    custom_domain: str,
    server_ip: str,
) -> str:
    """构建 frpc 代理配置块"""
    if proxy_type == "tcp":
        return textwrap.dedent(f"""\
            [[proxies]]
            name = "{proxy_name}"
            type = "tcp"
            localIP = "127.0.0.1"
            localPort = {local_port}
            remotePort = {remote_port}
            """)
    elif proxy_type == "http":
        domains = f'customDomains = ["{custom_domain}"]' if custom_domain else f'customDomains = ["{server_ip}"]'
        return textwrap.dedent(f"""\
            [[proxies]]
            name = "{proxy_name}"
            type = "http"
            localIP = "127.0.0.1"
            localPort = {local_port}
            {domains}
            """)
    elif proxy_type == "https":
        domains = f'customDomains = ["{custom_domain}"]' if custom_domain else f'customDomains = ["{server_ip}"]'
        return textwrap.dedent(f"""\
            [[proxies]]
            name = "{proxy_name}"
            type = "https"
            localIP = "127.0.0.1"
            localPort = {local_port}
            {domains}
            plugin.crtPath = "/etc/frp/ssl/server.crt"
            plugin.keyPath = "/etc/frp/ssl/server.key"
            """)
    return ""


def _build_systemd_services(dashboard_port: int, bind_port: int, remote_port: int) -> dict:
    """生成 frps/frpc systemd 服务文件"""
    return {
        "frps": {
            "file_path": "/etc/systemd/system/frps.service",
            "content": textwrap.dedent(f"""\
            [Unit]
            Description=frp server (frps)
            After=network.target

            [Service]
            Type=simple
            User=root
            ExecStart=/usr/local/bin/frps -c /root/frp/frps.toml
            Restart=always
            RestartSec=5
            LimitNOFILE=1048576

            [Install]
            WantedBy=multi-user.target
            """),
            "enable_command": (
                "systemctl daemon-reload\n"
                "systemctl enable frps\n"
                "systemctl start frps\n"
                "systemctl status frps"
            ),
        },
        "frpc": {
            "file_path": "/etc/systemd/system/frpc.service",
            "content": textwrap.dedent(f"""\
            [Unit]
            Description=frp client (frpc)
            After=network.target

            [Service]
            Type=simple
            User=root
            ExecStart=/usr/local/bin/frpc -c /root/frp/frpc.toml
            Restart=always
            RestartSec=5
            LimitNOFILE=1048576

            [Install]
            WantedBy=multi-user.target
            """),
            "enable_command": (
                "systemctl daemon-reload\n"
                "systemctl enable frpc\n"
                "systemctl start frpc\n"
                "systemctl status frpc"
            ),
        },
        "install_binary": (
            "wget https://github.com/fatedier/frp/releases/latest/download/frp_linux_amd64.tar.gz\n"
            "tar -xzf frp_linux_amd64.tar.gz\n"
            "cp frp_*/frps /usr/local/bin/frps\n"
            "cp frp_*/frpc /usr/local/bin/frpc\n"
            "国内：https://github.com/fatedier/frp/releases 可能慢，国内镜像见 skill"
        ),
    }


def _check_tcp_port(host: str, port: int, timeout: float = 3.0) -> str:
    """检测 TCP 端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return "open" if result == 0 else "timeout"
    except socket.gaierror:
        return "dns_error"
    except Exception:
        return "error"
    finally:
        sock.close()


def _suggest_password() -> str:
    """生成一个建议密码"""
    import string, random
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choice(chars) for _ in range(12))

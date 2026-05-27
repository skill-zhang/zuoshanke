"""rustdesk_generate_setup — RustDesk 中继服务器一键部署配置生成器

功能：为基础 Docker/podman 部署生成完整配置，
     端口可用性检测（TCP connect），
     客户端配置生成，
     nginx 反向代理配置

使用场景：
  - 用户有一台云 VPS，想搭自己的 RustDesk 中继（自建远程桌面）
  - 解决公网中继服务器（rs-ny.rustdesk.com）无法连接的问题

作者: 坐山客工具系统
"""

import json
import socket
import textwrap
from typing import Optional


def rustdesk_generate_setup(
    server_ip: str = "",
    domain: str = "",
    use_podman: bool = False,
    check_ports: bool = True,
    mirror: str = "docker.m.daocloud.io",
) -> str:
    """生成 RustDesk 中继服务器部署配置

    根据服务器 IP、域名、容器运行时等参数，生成完整的部署方案。
    包括：Docker/podman 命令、docker-compose.yml、nginx 配置、客户端配置。

    Args:
        server_ip: 云服务器公网 IP（必填）
        domain: 绑定的域名（可选，有则生成 nginx 配置）
        use_podman: 用 podman 替代 docker（Alibaba Cloud Linux 等用）
        check_ports: 是否检测端口连通性（默认开启）
        mirror: Docker Hub 镜像源，国内必须用 daoCloud 等镜像

    Returns:
        JSON 字符串，包含 sections: setup_guide, docker_commands,
        docker_compose, nginx_config, client_config, port_check
    """
    if not server_ip:
        return json.dumps({
            "success": False,
            "error": "必须提供 server_ip 参数（云服务器公网 IP）",
        }, ensure_ascii=False)

    runtime = "podman" if use_podman else "docker"
    result = {
        "success": True,
        "server_ip": server_ip,
        "domain": domain or "",
        "runtime": runtime,
        "sections": {},
    }

    # ── 端口检测 ──
    port_check = {}
    if check_ports:
        ports = [21115, 21116, 21117]
        for port in ports:
            protocol = "TCP+UDP" if port == 21116 else "TCP"
            status = _check_tcp_port(server_ip, port)
            port_check[str(port)] = {
                "protocol": protocol,
                "status": status,
                "note": (
                    "ID 注册/会合端口" if port == 21116
                    else "NAT 类型测试" if port == 21115
                    else "中继数据转发"
                ),
            }
            if status == "open":
                port_check[str(port)]["hint"] = "✅ 已开放"
            elif status == "timeout":
                port_check[str(port)]["hint"] = "⛔ 未开放或防火墙拦截（检查云安全组）"
            else:
                port_check[str(port)]["hint"] = "⚠️ 无法检测（可能被防火墙 silent drop）"
    result["sections"]["port_check"] = port_check

    # ── Docker 运行命令 ──
    docker_commands = {
        "data_dir": "mkdir -p /root/rustdesk-data",
        "hbbs": (
            f"{runtime} run -d --name hbbs --restart=always \\\n"
            f"  -p 21115:21115 -p 21116:21116 -p 21116:21116/udp -p 21118:21118 \\\n"
            f"  -v /root/rustdesk-data:/data \\\n"
            f"  {mirror}/rustdesk/rustdesk-server-s6:latest"
        ),
        "hbbr": (
            f"{runtime} run -d --name hbbr --restart=always \\\n"
            f"  -p 21117:21117 -p 21119:21119 \\\n"
            f"  -v /root/rustdesk-data:/data \\\n"
            f"  {mirror}/rustdesk/rustdesk-server-s6:latest hbbr"
        ),
        "pull_command": f"{runtime} pull {mirror}/rustdesk/rustdesk-server-s6:latest",
    }

    if use_podman:
        docker_commands["auto_start_note"] = (
            "podman --restart=always 依赖 systemd 服务文件以持久化。"
            "用以下命令生成并启用：\n"
            f"  podman generate systemd --name hbbs --files --new\n"
            f"  podman generate systemd --name hbbr --files --new\n"
            f"  cp /root/container-hbbs.service /etc/systemd/system/\n"
            f"  cp /root/container-hbbr.service /etc/systemd/system/\n"
            f"  systemctl daemon-reload\n"
            f"  systemctl enable container-hbbs container-hbbr"
        )

    # Alibaba Cloud Linux 的 Docker 替代方案
    docker_commands["alternative_note"] = None
    if use_podman:
        docker_commands["alternative_note"] = (
            "Alibaba Cloud Linux / Anolis OS 不支持 Docker 官方安装脚本。"
            "推荐使用 podman（yum install -y podman）。"
        )

    result["sections"]["docker_commands"] = docker_commands

    # ── Docker Compose ──
    compose_content = textwrap.dedent(f"""\
    version: "3"

    services:
      hbbs:
        image: {mirror}/rustdesk/rustdesk-server-s6:latest
        container_name: hbbs
        restart: always
        ports:
          - "21115:21115"
          - "21116:21116"
          - "21116:21116/udp"
          - "21118:21118"
        volumes:
          - ./rustdesk-data:/data

      hbbr:
        image: {mirror}/rustdesk/rustdesk-server-s6:latest
        container_name: hbbr
        restart: always
        ports:
          - "21117:21117"
          - "21119:21119"
        volumes:
          - ./rustdesk-data:/data
        command: hbbr
    """)
    result["sections"]["docker_compose"] = {
        "path": "docker-compose.yml",
        "content": compose_content,
        "note": "如果用 podman 代替 docker，命令行加 `--compat` 或直接用 podman-compose",
    }

    # ── Nginx 反向代理配置（Web 客户端端口转发） ──
    available_ports = [k for k, v in port_check.items() if v.get("status") == "open"]
    nginx_config = None
    if domain:
        nginx_config = {
            "path": "/etc/nginx/conf.d/rustdesk.conf",
            "content": textwrap.dedent(f"""\
            server {{
                listen 80;
                server_name {domain};

                # RustDesk Web 控制台（port 21118）
                location / {{
                    proxy_pass http://127.0.0.1:21118;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header Upgrade $http_upgrade;
                    proxy_set_header Connection "upgrade";
                }}
            }}
            """),
            "https_note": (
                "部署后建议用 certbot 申请 HTTPS 证书：\n"
                f"  certbot --nginx -d {domain}"
            ),
        }
    result["sections"]["nginx_config"] = nginx_config

    # ── 客户端配置 ──
    client_config = {
        "file_path": "%APPDATA%\\RustDesk\\config\\RustDesk2.toml",
        "content": textwrap.dedent(f"""\
            rendezvous_server = '{server_ip}:21116'

            [options]
            custom-rendezvous-server = '{server_ip}:21116'
            """),
        "note": (
            "部署完成后，在服务器执行以下命令获取公钥：\n"
            "  cat /root/rustdesk-data/id_ed25519.pub\n"
            "然后将 key 填入客户端配置\n\n"
            "⚠️ 写完后必须将文件设为只读防止 RustDesk 覆盖：\n"
            '  Windows: 属性 → 勾选"只读"\n'
            "  Linux/Mac: chmod 444 RustDesk2.toml"
        ),
        "gui_guide": (
            "推荐用 GUI 方式配置（更可靠）：\n"
            "1. 右击系统托盘 RustDesk 图标 → 设置 → 网络\n"
            "2. ID 中继服务器填入：{server_ip}:21116\n"
            "3. Key 填入服务器公钥\n"
            "4. 重启 RustDesk 客户端"
        ).format(server_ip=server_ip),
    }
    result["sections"]["client_config"] = client_config

    # ── 部署步骤总览 ──
    setup_guide = [
        {"step": 1, "action": "登录云服务器",
         "command": f"ssh root@{server_ip}",
         "note": "确保已在云控制台安全组开放 21115-21117/TCP，21116/UDP"},
        {"step": 2, "action": "安装容器运行时",
         "command": "yum install -y podman" if use_podman else "curl -fsSL https://get.docker.com | sh",
         "note": "国内服务器如果 Docker Hub 不通，用 daoCloud 镜像"},
        {"step": 3, "action": "拉取镜像",
         "command": docker_commands["pull_command"],
         "note": f"镜像源: {mirror}"},
        {"step": 4, "action": "创建数据目录",
         "command": docker_commands["data_dir"]},
        {"step": 5, "action": "启动 hbbs（ID/会合服务器）",
         "command": docker_commands["hbbs"]},
        {"step": 6, "action": "启动 hbbr（中继服务器）",
         "command": docker_commands["hbbr"]},
        {"step": 7, "action": "验证运行状态",
         "command": f"{runtime} ps",
         "note": "两个容器都应为 Up 状态"},
        {"step": 8, "action": "获取公钥",
         "command": "cat /root/rustdesk-data/id_ed25519.pub",
         "note": "保存这个 key，客户端配置需要"},
    ]

    if use_podman:
        setup_guide.insert(6, {
            "step": "5.5", "action": "配置 systemd 自启",
            "command": docker_commands.get("auto_start_note", ""),
            "note": "podman 需要 systemd 服务文件保证重启后容器自启",
        })

    result["sections"]["setup_guide"] = setup_guide

    # ── 镜像源说明 ──
    result["sections"]["mirror_info"] = {
        "current": mirror,
        "note": "国内服务器推荐镜像源：docker.m.daocloud.io（DaoCloud）、mirror.ccs.tencentyun.com（腾讯云内网）",
        "permanent_config": {
            "podman": "编辑 /etc/containers/registries.conf 添加 [[registry]] 配置",
            "docker": "编辑 /etc/docker/daemon.json 添加 registry-mirrors",
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def _check_tcp_port(host: str, port: int, timeout: float = 3.0) -> str:
    """检测 TCP 端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            return "open"
        else:
            return "timeout"
    except socket.gaierror:
        return "dns_error"
    except Exception:
        return "error"
    finally:
        sock.close()

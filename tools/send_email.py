"""📧 邮件发送工具 — 通过 SMTP 发送邮件

基于 Python smtplib + email 标准库，无需额外依赖。
支持纯文本/HTML 正文、附件（文件路径）、多收件人。

用户需要在系统环境变量或工具参数中配置 SMTP 信息。
默认支持常见邮箱（QQ/163/Gmail）的 SMTP 配置参考。

## 用法
    from tools.send_email import send_email
    r = json.loads(send_email(
        to="user@example.com",
        subject="测试邮件",
        body="这是一封测试邮件",
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_user="your@qq.com",
        smtp_password="your_smtp_code"
    ))
"""

import json
import os
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# ── 常见邮箱 SMTP 配置 ──
SMTP_PRESETS = {
    "qq":     {"host": "smtp.qq.com",     "port": 465, "ssl": True},
    "qq_ex":  {"host": "smtp.qq.com",     "port": 587, "ssl": False},
    "163":    {"host": "smtp.163.com",    "port": 465, "ssl": True},
    "126":    {"host": "smtp.126.com",    "port": 465, "ssl": True},
    "gmail":  {"host": "smtp.gmail.com",  "port": 465, "ssl": True},
    "outlook":{"host": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "aliyun": {"host": "smtp.aliyun.com", "port": 465, "ssl": True},
    "sina":   {"host": "smtp.sina.com.cn","port": 465, "ssl": True},
}


def _resolve_smtp_config(provider: str, host: str, port: int, use_ssl: bool) -> dict:
    """解析 SMTP 配置，preset 优先"""
    if provider and provider.lower() in SMTP_PRESETS:
        cfg = SMTP_PRESETS[provider.lower()]
        return {"host": cfg["host"], "port": cfg["port"], "ssl": cfg["ssl"]}

    # 手动配置
    if host and port:
        return {"host": host, "port": port, "ssl": use_ssl if use_ssl else (port == 465)}

    # 尝试从环境变量读取
    env_host = os.environ.get("ZUOSHANKE_SMTP_HOST", "")
    env_port = os.environ.get("ZUOSHANKE_SMTP_PORT", "")
    if env_host and env_port:
        return {"host": env_host, "port": int(env_port), "ssl": os.environ.get("ZUOSHANKE_SMTP_SSL", "1") == "1"}

    return {}


def send_email(
    to: str,
    subject: str = "",
    body: str = "",
    body_type: str = "plain",
    cc: str = "",
    bcc: str = "",
    attachments: str = "",
    smtp_provider: str = "",
    smtp_host: str = "",
    smtp_port: int = 465,
    smtp_ssl: bool = True,
    smtp_user: str = "",
    smtp_password: str = "",
    from_name: str = "",
) -> str:
    """发送邮件，返回 JSON 字符串

    Args:
        to:              收件人邮箱，多个用逗号分隔（必填）
        subject:         邮件主题
        body:            邮件正文
        body_type:       正文类型，plain(纯文本) / html(HTML)，默认 plain
        cc:              抄送，多个用逗号分隔
        bcc:             密送，多个用逗号分隔
        attachments:     附件文件路径，多个用逗号分隔
        smtp_provider:   邮箱提供商预设，可选 qq/163/126/gmail/outlook/aliyun/sina
        smtp_host:       手动 SMTP 服务器地址（provider 为空时生效）
        smtp_port:       手动 SMTP 端口，默认 465
        smtp_ssl:        是否使用 SSL，默认 True（端口 465 自动 SSL）
        smtp_user:       SMTP 用户名（通常为邮箱地址）
        smtp_password:   SMTP 密码（QQ邮箱需用授权码，非登录密码）
        from_name:       发件人显示名称（可选）

    环境变量（当 smtp_user/password 为空时读取）:
        ZUOSHANKE_SMTP_USER, ZUOSHANKE_SMTP_PASSWORD
        ZUOSHANKE_SMTP_HOST, ZUOSHANKE_SMTP_PORT, ZUOSHANKE_SMTP_SSL

    Returns:
        JSON string:
        {
            "success": true/false,
            "to": ["user@example.com"],
            "subject": "主题",
            "from_addr": "发件人地址",
            "sent_at": "发送时间",
            "error": "错误信息"
        }
    """
    try:
        if not to or not to.strip():
            return json.dumps({"success": False, "error": "收件人邮箱不能为空"}, ensure_ascii=False)

        to_list = [addr.strip() for addr in to.split(",") if addr.strip()]
        cc_list = [addr.strip() for addr in cc.split(",") if addr.strip()] if cc else []
        bcc_list = [addr.strip() for addr in bcc.split(",") if addr.strip()] if bcc else []

        if not to_list:
            return json.dumps({"success": False, "error": "收件人邮箱无效"}, ensure_ascii=False)

        # 解析 SMTP 配置
        cfg = _resolve_smtp_config(smtp_provider, smtp_host, smtp_port, smtp_ssl)
        if not cfg:
            return json.dumps({
                "success": False,
                "error": "未配置 SMTP 服务器。请指定 smtp_provider（如 qq/163/gmail）或手动填写 smtp_host/smtp_port",
                "presets": list(SMTP_PRESETS.keys()),
            }, ensure_ascii=False)

        host = cfg["host"]
        port = cfg["port"]
        use_ssl = cfg["ssl"]

        # 获取认证信息
        user = smtp_user or os.environ.get("ZUOSHANKE_SMTP_USER", "")
        password = smtp_password or os.environ.get("ZUOSHANKE_SMTP_PASSWORD", "")

        if not user:
            return json.dumps({
                "success": False,
                "error": "未配置发件人邮箱。请设置 smtp_user 或环境变量 ZUOSHANKE_SMTP_USER",
            }, ensure_ascii=False)
        if not password:
            return json.dumps({
                "success": False,
                "error": "未配置 SMTP 密码。请设置 smtp_password 或环境变量 ZUOSHANKE_SMTP_PASSWORD（QQ邮箱使用授权码）",
            }, ensure_ascii=False)

        # 构建邮件
        msg = MIMEMultipart() if attachments else MIMEText(body, body_type, "utf-8")

        if isinstance(msg, MIMEMultipart):
            msg.attach(MIMEText(body, body_type, "utf-8"))

        sender_name = from_name or user.split("@")[0]
        msg["From"] = f"{sender_name} <{user}>"
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject or "(无主题)"

        # 处理附件
        if attachments:
            attach_files = [f.strip() for f in attachments.split(",") if f.strip()]
            for file_path in attach_files:
                if not os.path.exists(file_path):
                    continue
                with open(file_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    filename = os.path.basename(file_path)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{filename}"',
                    )
                    msg.attach(part)

        # 发送
        all_recipients = to_list + cc_list + bcc_list

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()

        server.login(user, password)
        server.sendmail(user, all_recipients, msg.as_string())
        server.quit()

        sent_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return json.dumps({
            "success": True,
            "to": to_list,
            "cc": cc_list if cc_list else None,
            "subject": subject or "(无主题)",
            "from_addr": user,
            "from_name": sender_name,
            "smtp_host": host,
            "smtp_port": port,
            "attachments": len(attach_files) if attachments else 0,
            "sent_at": sent_at,
        }, ensure_ascii=False)

    except smtplib.SMTPAuthenticationError:
        return json.dumps({
            "success": False,
            "error": "SMTP 认证失败，请检查用户名和密码。QQ邮箱需使用授权码（设置→账户→POP3/SMTP服务）",
        }, ensure_ascii=False)
    except smtplib.SMTPRecipientsRefused:
        return json.dumps({
            "success": False,
            "error": "收件人被拒，请检查邮箱地址是否正确",
        }, ensure_ascii=False)
    except smtplib.SMTPException as e:
        return json.dumps({
            "success": False,
            "error": f"SMTP 错误: {str(e)}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"邮件发送失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)

---
name: send-email
description: 发送邮件 — 通过 SMTP 发送纯文本/HTML 邮件，支持附件、多收件人、抄送。内置主流邮箱预设
version: 1.0
category: system
triggers: [发邮件, 发送邮件, 邮件, email, 写信, 通知邮件, 发送, 邮件通知, 邮件发送, 帮我发邮件, 发一封邮件, 通知]
---

# 发送邮件

## 配套工具

坐山客内置了 `send_email` 工具（⚙️ 系统分类），帮你发送邮件：

```bash
# 简单文本邮件（需配置 SMTP）
send_email(
    to="friend@example.com",
    subject="你好",
    body="这是一封测试邮件",
    smtp_provider="qq",
    smtp_user="your@qq.com",
    smtp_password="你的授权码"
)

# 带附件
send_email(
    to="user@example.com",
    subject="报告",
    body="请查收附件",
    attachments="/path/to/file.pdf",
    smtp_provider="163",
    smtp_user="your@163.com",
    smtp_password="授权码"
)

# HTML 邮件
send_email(
    to="user@example.com",
    subject="欢迎",
    body="<h1>欢迎使用</h1><p>感谢注册</p>",
    body_type="html",
    smtp_provider="gmail",
    smtp_user="you@gmail.com",
    smtp_password="应用专用密码"
)
```

## 内置 SMTP 预设

| 提供商 | 服务器 | 端口 | 说明 |
|--------|--------|------|------|
| qq | smtp.qq.com | 465 | 需开启 POP3/SMTP + 获取授权码 |
| qq_ex | smtp.qq.com | 587 | QQ 邮箱 TLS 端口 |
| 163 | smtp.163.com | 465 | 需开启 SMTP 服务 |
| 126 | smtp.126.com | 465 | 需开启 SMTP 服务 |
| gmail | smtp.gmail.com | 465 | 需应用专用密码 |
| outlook | smtp-mail.outlook.com | 587 | TLS 加密 |
| aliyun | smtp.aliyun.com | 465 | 企业邮箱 |
| sina | smtp.sina.com.cn | 465 | 新浪邮箱 |

## 配置方式

1. **每次调用传参** — 在 tool 参数中直接传 smtp_user/smtp_password
2. **环境变量**（推荐） — 设置以下变量，之后调用无需重复传参：

```bash
export ZUOSHANKE_SMTP_HOST=smtp.qq.com
export ZUOSHANKE_SMTP_PORT=465
export ZUOSHANKE_SMTP_SSL=1
export ZUOSHANKE_SMTP_USER=your@qq.com
export ZUOSHANKE_SMTP_PASSWORD=your_auth_code
```

## 注意事项

- QQ 邮箱需要**授权码**（设置 → 账户 → POP3/SMTP 服务 → 生成授权码），不是登录密码
- Gmail 需要开启两步验证 + 生成**应用专用密码**
- 邮件发送需要网络连接
- 附件路径必须是坐山客服务器上可访问的本地路径

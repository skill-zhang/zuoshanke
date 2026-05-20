"""向 Agent Loop 提交博物馆 HTML 构建任务"""
import json, requests, os, sys

TASK = """你是一个 AI 助手，帮我构建一个关于中国博物馆的 HTML 信息网页。

要求：
1. 用 web_search 搜索 3-5 次，获取国内主要博物馆的信息（名称、链接、馆藏特点、展览简介）
2. 搜索时用不同的关键词：如「中国国家级博物馆列表」「省级博物馆推荐」「博物馆馆藏介绍」
3. 搜索完成后，根据搜索结果和我已有的知识，生成一个完整的 HTML 信息页面
4. 用 run_code 工具生成 HTML 文件，保存到 ~/zuoshanke/capability-demo/museum-guide.html
5. HTML 页面内容需要包括：
   - 博物馆分类：国家级、省级、专题类
   - 每个博物馆的简介、馆藏特色、展览亮点
   - 带链接可点击
   - 星级推荐（五星制）
   - 页面设计美观，暗色风格，适合浏览器打开

注意：
- 搜索 3-5 次就够了，不要无限制搜索
- 搜索到足够信息后就生成 HTML，不要在搜索上花太多步数
- HTML 用 run_code 的 code_b64 参数传 base64 编码，避免 JSON 转义问题
- 如果 run_code 的 code 参数报错，改用分批 bash heredoc 写入
"""

URL = "http://localhost:8000/api/agent-loop/stream"
LOG = os.path.expanduser("~/zuoshanke/capability-demo/museum-agent-log.txt")

print(f"提交任务...")
print(f"日志: {LOG}")

resp = requests.post(URL, json={
    "task": TASK,
    "max_steps": 80,
}, stream=True, timeout=600)
resp.raise_for_status()

with open(LOG, "w", encoding="utf-8") as f:
    step = 0
    for line in resp.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8", errors="replace")
        if not text.startswith("data: "):
            continue
        data = json.loads(text[6:])
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
        f.flush()

        et = data.get("type", "")
        if et == "tool_start":
            step += 1
            print(f"  ⚡ [{step}] {data.get('tool')} → {str(data.get('args',{}).get('query','') or data.get('args',{}).get('path',''))[:80]}")
        elif et == "tool_done":
            r = str(data.get('result',''))[:60]
            print(f"     ✅ {data.get('tool')}: {r}")
        elif et == "tool_error":
            print(f"     ❌ {data.get('tool')}: {str(data.get('error',''))[:100]}")
        elif et == "thinking":
            print(f"  💬 {data.get('text','')[:120]}")
        elif et == "done":
            summary = data.get('summary', '')[:200]
            print(f"\n✅ 完成! 步数={data.get('steps')}, 原因={data.get('finish_reason')}")
            print(f"   摘要: {summary}")
        elif et == "error":
            print(f"\n❌ 错误: {data.get('message')}")

# 检查产物
out_path = os.path.expanduser("~/zuoshanke/capability-demo/museum-guide.html")
if os.path.isfile(out_path):
    size = os.path.getsize(out_path)
    print(f"\n📄 产物已生成: {out_path} ({size/1024:.1f} KB)")
    with open(out_path) as f:
        first = f.read(200)
        print(f"   开头: {first[:100]}...")
else:
    print(f"\n⚠️ 产物未找到: {out_path}")
    # 检查是否有别的产物
    for f in os.listdir(os.path.expanduser("~/zuoshanke/capability-demo/")):
        if f.endswith(".html"):
            print(f"  找到替代产物: {f}")

#!/usr/bin/env python3
"""Send a game-building task to zuoshanke Agent Loop - using run_code for file creation."""

import json
import requests
import sys
import os

TASK = """你是一个AI游戏开发者，请创建一个像素风格的RPG冒险小游戏，作为单个自包含的HTML文件。

【保存路径】~/zuoshanke/capability-demo/adventure-game-agent.html

【重要】由于 JSON 转义限制，`run_code` 的 `code` 参数不能超过 3000 字符。
有两种方式写大文件：
  方式A（推荐）：分批写 + bash 追加（每个部分 < 2000 字符）
    cat > /tmp/game_part1.txt << 'ENDPART1'
    <!DOCTYPE html>
    <html>
    ...约2KB的HTML代码...
    ENDPART1
    
    cat > /tmp/game_part2.txt << 'ENDPART2'
    ...更多HTML代码...
    ENDPART2
    
    # 最后拼接
    cat /tmp/game_part*.txt > ~/zuoshanke/capability-demo/adventure-game-agent.html
    rm /tmp/game_part*.txt
    echo "Game file created: $(wc -c < ~/zuoshanke/capability-demo/adventure-game-agent.html) bytes"

  方式B：用 code_b64 参数传 base64 编码的 Python 代码
    先用 bash 写一个文件，然后读取并 base64 编码后再提交

请用方式A分批写，每批约1500-2000字符，避免JSON转义问题。

【游戏规格】
- 地图: 500×500px, 50×50网格(10px/格), Canvas全图渲染
- 地形: 山脉(右上)、河流(蜿蜒)、桥×2(可通行)、草地、石头、树、花
- 村庄: 左下角, 3个茅草屋(土墙+红顶), 可用方向键+Space交互
- 主角: 小男孩(棕帽+蓝衣+棕裤), ↑↓←→移动, Space交互
- NPC: 3个村民(村长给木剑, 大叔提示危险, 小姑娘说怪物)
- 怪物: 5+种(史莱姆/小妖精/幽灵/野狼/蜘蛛), 随机分布村外, 回合制战斗
- 救援: 4-6个遇险者(❗标记), 对话→打怪→加入队伍(提升ATK/DEF)
- 物品: 地上拾取黄色标记, 自动装备/用药水, 怪物掉落
- UI: 状态栏(HP/ATK/DEF/队伍/装备), 背包(I键), 休息(R键)
- 胜利: 救所有人OR打完怪物 → 胜利画面+重玩按钮
- 放大: 点击画布弹出全屏蒙层
- 纯JS + Canvas 2D, 单HTML文件, 无第三方依赖

【接口说明】
你可用工具：
- run_code(language="bash", code=...) — 执行 bash 命令，用于查看目录、写文件、拼接文件
- run_code(language="python", code=...) — 执行 Python（代码<3000字符）
- run_code(code_b64="base64编码的代码", language="python") — 执行长代码
- read_file(path=...) — 读取文件

【开发步骤】
1. 先跑 bash 查看目录结构和已有文件
2. 用分批写入方式，每批一个 bash cat heredoc 命令
3. 拼接所有分片为最终 HTML 文件
4. 用 read_file 检查关键部分
5. 用 node 验证 JS 语法
6. 如果报错，分析修复

开始吧！
"""

def send_task():
    url = "http://localhost:8000/api/agent-loop/stream"
    payload = {"task": TASK}
    log_file = os.path.expanduser("~/zuoshanke/capability-demo/agent-loop-log.txt")
    
    print(f"[Agent Loop] 🚀 发送任务...\n", flush=True)
    
    try:
        resp = requests.post(url, json=payload, stream=True, timeout=900)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Agent Loop] ❌ 请求失败: {e}", flush=True)
        return False

    tool_count = 0
    with open(log_file, 'w', encoding='utf-8') as f:
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode('utf-8', errors='replace')
            if not text.startswith('data: '):
                continue
            try:
                data = json.loads(text[6:])
            except json.JSONDecodeError:
                continue
            
            event_type = data.get('type', '')
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
            f.flush()
            
            if 'tool_start' in event_type:
                tool_count += 1
                tool = data.get('tool', '?')
                args = data.get('args', {})
                path = args.get('path', '')
                code_preview = (args.get('code', '') or '')[:80].replace('\n', ' ')
                detail = path or code_preview or ''
                print(f"  🛠️ Step {tool_count}: {tool} → {detail}", flush=True)
            elif 'tool_done' in event_type:
                r = str(data.get('result', {}))[:80]
                print(f"     ✅ {r}", flush=True)
            elif 'tool_error' in event_type:
                err = str(data.get('error', ''))[:120]
                print(f"     ❌ {err}", flush=True)
            elif 'thinking' in event_type:
                txt = data.get('text', '')[:100].replace('\n', ' ')
                print(f"  💬 {txt}", flush=True)
                f.write(f"[AI REPLY] {data.get('text','')}\n\n")
                f.flush()
            elif 'done' in event_type:
                steps = data.get('steps', tool_count)
                reason = data.get('finish_reason', '')
                print(f"\n[Agent Loop] ✅ 完成! {steps}步, 原因: {reason}", flush=True)
            elif 'error' in event_type:
                print(f"\n[Agent Loop] ❌ 错误: {data.get('message','')}", flush=True)

    # Check what was created
    demo_dir = os.path.expanduser("~/zuoshanke/capability-demo")
    files = [f for f in os.listdir(demo_dir) if f.endswith('.html')]
    if files:
        print(f"\n[Agent Loop] 📄 生成的文件: {files}", flush=True)
        for fn in files:
            fp = os.path.join(demo_dir, fn)
            size = os.path.getsize(fp)
            print(f"     {fn}: {size} bytes", flush=True)
    else:
        print(f"\n[Agent Loop] ⚠️ 没有找到生成的HTML文件", flush=True)
    
    return True

if __name__ == '__main__':
    success = send_task()
    sys.exit(0 if success else 1)

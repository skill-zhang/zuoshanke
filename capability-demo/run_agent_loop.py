#!/usr/bin/env python3
"""Send a game-building task to zuoshanke Agent Loop - using run_code for file creation."""

import json
import requests
import sys
import os

TASK = """你是一个AI游戏开发者，请创建一个像素风格的RPG冒险小游戏，作为单个自包含的HTML文件。

【保存路径】~/zuoshanke/capability-demo/adventure-game-agent.html

【重要】由于 JSON 参数限制，不要用 write_file 工具！也避免在 run_code 的 code 参数中传大段代码。
用 run_code 的 code_b64 参数传 base64 编码的代码。步骤：
1. 先用 run_code(python) 生成 HTML 内容并 base64 编码保存到临时文件
2. 再用 run_code(bash) 解码并写入目标路径
示例：
  python -c "import base64; open('_tmp.b64','w').write(base64.b64encode(open('/dev/stdin','rb').read()).decode())" < <(cat << 'PYEOF'
  ... 你的 Python 代码（相对较短）生成 HTML ...
  PYEOF
  )
  base64 -d _tmp.b64 > ~/zuoshanke/capability-demo/adventure-game-agent.html

或者更简单：用 run_code(python) 时把大段 HTML 拆成小块，用 Python 的字符串拼接/列表追加构建。

【地图规格】整个地图 500×500 像素，50×50 瓦片网格（每个瓦片10px），Canvas 渲染。
不需要滚动/视口——全地图在一屏内可见。

【地图内容】
- 右上区域：山脉（灰色/棕色山峰簇）
- 蜿蜒的河流（蓝色，2-3格宽），从地图中上部流向右下
- 河上有1-2座桥（棕色，可通行）
- 左下角：小村庄（3个茅草屋——土墙+红色斜顶）
- 树（深绿，散布）、石头（灰色）、花（彩色，点缀）
- 野草/平地作为基底

【NPC】村庄里3个，按Space对话：
- 村长（红衣）：给你木剑
- 商人大叔：提示村外危险
- 小姑娘：说有怪物在外游荡

【主角】小男孩，方向键移动，棕色帽子+蓝衣+棕裤
在村庄里按 R 恢复HP

【怪物系统】
- 村外随机生成：史莱姆、小妖精、幽灵、野狼、蜘蛛（至少5种）
- 走近按Space → 回合制战斗（玩家攻击→敌人攻击→循环）
- 胜利：怪物消失，随机掉落（回复药水、木剑、铁剑、皮甲等）
- 失败：在村庄复活，HP减半，怪物消失
- 占着怪物格子的地方不能走上去（除非战斗）

【拾取系统】
- 地上有物品（黄色闪烁方块标记），走过去自动拾取
- 自动装备更好的武器/防具
- 自动使用回复药水（HP不满时）

【救援系统】地图上4-6个遇险的人（❗标记）
- 走近按Space对话 → 附近出现怪物 → 打败后加入队伍（增加ATK/DEF）

【UI】
- 画布上方：标题 "小村庄大冒险"
- 画布下方状态栏：❤️HP条 ⚔️ATK 🛡️DEF 👥队伍 🎒装备
- 状态栏右侧显示当前消息
- 底部操作提示

【胜利条件】救所有人 OR 打败所有怪物 → 胜利画面+重新游戏按钮

【放大】点击画布 → 弹出全屏蒙层显示完整地图

【操作】
↑↓←→移动 | Space/Enter交互/攻击 | I背包 | R休息 | 点击放大

【技术限定】
- 单HTML，CSS/JS全部内联
- Canvas 2D，像素风格（image-rendering: pixelated）
- 全部用纯JS，无第三方依赖
- 先用 run_code(bash) 查看目录结构
- 然后用 run_code(code_b64=...) 写文件——把 Python 代码 base64 编码后传入
- 写完之后用 node -e 检查JS语法
- 如果第一次运行失败，分析错误后修复重试
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

"""🍳 菜谱推荐 — 根据食材/菜名/口味推荐家常菜谱

基于本地 Qwen LLM 生成详细菜谱，支持：
- 按已有食材推荐（输入有什么就做什么）
- 按菜名搜索（想吃什么做什么）
- 按口味/菜系筛选（川菜/粤菜/清淡/下饭等）

## 用法
    from tools.recipe import recipe
    r = json.loads(recipe(ingredients="鸡蛋,番茄"))
    r = json.loads(recipe(dish="麻婆豆腐"))
"""

import json
import traceback
import urllib.request
import urllib.error

# ── Qwen LLM API ──
LLM_URL = "http://localhost:8083/v1/chat/completions"

# ── 口味/菜系 ──
CUISINES = {
    "sichuan": "川菜（麻辣）",
    "cantonese": "粤菜（清淡鲜美）",
    "jiangzhe": "江浙菜（甜鲜）",
    "hunan": "湘菜（香辣）",
    "northern": "北方菜（咸香）",
    "japanese": "日式料理",
    "western": "西餐",
    "fusion": "创意融合菜",
}


def _call_llm(system_prompt: str, user_text: str) -> str:
    """调用本地 Qwen LLM"""
    payload = json.dumps({
        "model": "Qwen3.5-9B-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.4,
        "max_tokens": 2048,
    }).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def recipe(ingredients: str = "", dish: str = "", cuisine: str = "", difficulty: str = "easy") -> str:
    """推荐菜谱，返回 JSON 字符串

    Args:
        ingredients: 已有的食材，逗号分隔。如 "鸡蛋,番茄,葱"
        dish:        想做的菜名。如设定了 dish 则优先按菜名生成
        cuisine:     菜系偏好。可选：sichuan(川菜)/cantonese(粤菜)/jiangzhe(江浙)
                     /northern(北方)/japanese(日式)/western(西餐)，默认自动
        difficulty:  难度。easy(简单)/medium(中等)/hard(复杂)，默认 easy

    至少需要 ingredients 或 dish 之一。

    Returns:
        JSON string:
        {
            "success": true/false,
            "dish_name": "番茄炒蛋",
            "cuisine_label": "家常菜",
            "difficulty": "easy",
            "prep_time": "10分钟",
            "cook_time": "10分钟",
            "ingredients": [
                {"name": "番茄", "amount": "2个", "note": ""},
                ...
            ],
            "steps": [
                {"step": 1, "action": "番茄切块"},
                ...
            ],
            "tips": ["小贴士..."],
            "nutrition": "大约 200 卡路里",
            "error": "错误信息"
        }
    """
    try:
        if not ingredients and not dish:
            return json.dumps({
                "success": False,
                "error": "请提供食材（ingredients）或菜名（dish），至少填一个",
            }, ensure_ascii=False)

        # 构建 prompt
        cuisine_label = CUISINES.get(cuisine, "家常菜")
        diff_label = {"easy": "简单快手", "medium": "中等难度", "hard": "有挑战"}.get(difficulty, "简单快手")

        if dish:
            user_intent = f"我想做「{dish}」"
            if ingredients:
                user_intent += f"，手头有这些食材：{ingredients}"
        else:
            user_intent = f"我手头有这些食材：{ingredients}，帮我推荐一道菜"

        user_intent += f"。风格偏好：{cuisine_label}，难度要求：{diff_label}"

        system_prompt = (
            "你是一个专业厨师。请根据用户提供的食材或菜名，生成一道家常菜的完整菜谱。\n"
            "输出必须是严格的 JSON 格式，不要包含任何 markdown 标记或额外的文字说明。\n"
            "JSON 结构如下：\n"
            "{\n"
            '  "dish_name": "菜名",\n'
            '  "cuisine": "菜系",\n'
            '  "difficulty": "难度",\n'
            '  "prep_time": "准备时间",\n'
            '  "cook_time": "烹饪时间",\n'
            '  "ingredients": [{"name": "食材名", "amount": "用量", "note": "备注(可选)"}],\n'
            '  "steps": [{"step": 1, "action": "步骤描述"}],\n'
            '  "tips": ["小贴士1", "小贴士2"],\n'
            '  "nutrition": "营养信息"\n'
            "}\n"
            "规则：\n"
            "1. ingredients 至少包含 3 种食材\n"
            "2. steps 至少 4 步，每步清晰可操作\n"
            "3. 如果用户只给了食材，推荐的菜要能用这些食材做（再额外补充 1-2 种常见调料）\n"
            "4. 用量用中文单位（个/克/勺/碗/适量等）\n"
            "5. 步骤中的「适量」「少许」要给出大致参考量\n"
            "6. JSON 必须合法，不要有注释"
        )

        llm_output = _call_llm(system_prompt, user_intent)

        # 尝试解析 JSON
        try:
            data = json.loads(llm_output)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', llm_output)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # 直接尝试从花括号提取
                brace_match = re.search(r'\{[\s\S]*\}', llm_output)
                if brace_match:
                    data = json.loads(brace_match.group())
                else:
                    raise

        # 补充字段
        result = {
            "success": True,
            "dish_name": data.get("dish_name", dish or "家常菜"),
            "cuisine": data.get("cuisine", cuisine_label),
            "difficulty": data.get("difficulty", difficulty),
            "prep_time": data.get("prep_time", "约10分钟"),
            "cook_time": data.get("cook_time", "约15分钟"),
            "ingredients": data.get("ingredients", []),
            "steps": data.get("steps", []),
            "tips": data.get("tips", []),
            "nutrition": data.get("nutrition", ""),
        }

        return json.dumps(result, ensure_ascii=False)

    except urllib.error.URLError as e:
        return json.dumps({
            "success": False,
            "error": f"无法连接本地 LLM 服务: {e.reason}",
        }, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return json.dumps({
            "success": False,
            "error": f"LLM 返回格式异常: {str(e)}",
            "raw": llm_output if 'llm_output' in dir() else "",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"菜谱生成失败: {str(e)}",
            "detail": traceback.format_exc(),
        }, ensure_ascii=False)

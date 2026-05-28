"""💬 每日一言 — 名言/鸡汤/人生感悟生成器

基于嵌入的名人名言库和本地 Qwen LLM 双重来源，
支持多种风格（励志/哲思/治愈/幽默），
适合早安晚安推送、桌面装饰、心理调节。

## 用法
    from tools.daily_quote import daily_quote
    r = json.loads(daily_quote())
    r = json.loads(daily_quote(category="motivation"))
"""

import json
import random
import traceback
import urllib.request
import urllib.error

# ── Qwen LLM API ──
LLM_URL = "http://localhost:8083/v1/chat/completions"

# ── 分类 ──
CATEGORIES = {
    "motivation": "励志",
    "philosophy": "哲思",
    "healing": "治愈",
    "life": "人生",
    "humor": "幽默",
    "love": "爱情",
    "wisdom": "智慧",
}

# ── 名人名言库（LLM 不可用时回退） ──
QUOTES = {
    "motivation": [
        {"text": "千里之行，始于足下。", "author": "老子"},
        {"text": "天行健，君子以自强不息。", "author": "《周易》"},
        {"text": "不积跬步，无以至千里；不积小流，无以成江海。", "author": "荀子"},
        {"text": "世上无难事，只怕有心人。", "author": "中国谚语"},
        {"text": "The only way to do great work is to love what you do.", "author": "Steve Jobs"},
        {"text": "Believe you can and you're halfway there.", "author": "Theodore Roosevelt"},
        {"text": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius"},
        {"text": "行百里者半九十。", "author": "《战国策》"},
        {"text": "不为失败找理由，要为成功找方法。", "author": "中国谚语"},
        {"text": "有志者，事竟成。", "author": "《后汉书》"},
    ],
    "philosophy": [
        {"text": "知之为知之，不知为不知，是知也。", "author": "孔子"},
        {"text": "存在即合理。", "author": "黑格尔"},
        {"text": "我思故我在。", "author": "笛卡尔"},
        {"text": "认识你自己的无知，就是最大的智慧。", "author": "苏格拉底"},
        {"text": "人生而自由，却无往不在枷锁之中。", "author": "卢梭"},
        {"text": "幸福的家庭都是相似的，不幸的家庭各有各的不幸。", "author": "托尔斯泰"},
        {"text": "The unexamined life is not worth living.", "author": "Socrates"},
        {"text": "人皆知有用之用，而莫知无用之用也。", "author": "庄子"},
        {"text": "道可道，非常道；名可名，非常名。", "author": "老子"},
        {"text": "世事洞明皆学问，人情练达即文章。", "author": "曹雪芹"},
    ],
    "healing": [
        {"text": "慢慢来，比较快。", "author": "蒋勋"},
        {"text": "一切都是最好的安排。", "author": "佚名"},
        {"text": "万物皆有裂痕，那是光照进来的地方。", "author": "莱昂纳德·科恩"},
        {"text": "不要因为结束而哭泣，要因为它发生过而微笑。", "author": "泰戈尔"},
        {"text": "生活就像一盒巧克力，你永远不知道下一颗是什么味道。", "author": "《阿甘正传》"},
        {"text": "Tomorrow is another day.", "author": "Margaret Mitchell"},
        {"text": "允许一切发生，因为一切都会过去。", "author": "佚名"},
        {"text": "你已经做得够好了，休息一下吧。", "author": "佚名"},
        {"text": "心有猛虎，细嗅蔷薇。", "author": "萨松"},
        {"text": "山重水复疑无路，柳暗花明又一村。", "author": "陆游"},
    ],
    "life": [
        {"text": "人生如逆旅，我亦是行人。", "author": "苏轼"},
        {"text": "生活不止眼前的苟且，还有诗和远方的田野。", "author": "高晓松"},
        {"text": "人生得意须尽欢，莫使金樽空对月。", "author": "李白"},
        {"text": "活着本身就是一件很了不起的事。", "author": "余华"},
        {"text": "Life is what happens when you're busy making other plans.", "author": "John Lennon"},
        {"text": "纵有千般不舍，终究各有渡口。", "author": "佚名"},
        {"text": "人生自古谁无死，留取丹心照汗青。", "author": "文天祥"},
        {"text": "此情可待成追忆，只是当时已惘然。", "author": "李商隐"},
        {"text": "不如意事常八九，可与人言无二三。", "author": "方岳"},
        {"text": "人生如戏，戏如人生。", "author": "中国谚语"},
    ],
    "humor": [
        {"text": "我最大的缺点就是没有缺点——哦不，是钱不够花。", "author": "佚名"},
        {"text": "如果你觉得自己又胖又丑，别担心，你的感觉是对的。", "author": "佚名"},
        {"text": "我本来想减肥的，但是美食先动手了。", "author": "佚名"},
        {"text": "今天不想起床，我要和被子私奔。", "author": "佚名"},
        {"text": "所谓成长，就是不断地发现以前的自己是个傻子。", "author": "佚名"},
        {"text": "昨天是历史，明天是谜团，今天是礼物——所以叫present。", "author": "佚名"},
        {"text": "我很懒，但我很有拖延症。", "author": "佚名"},
        {"text": "你以为我想加班？我只是不想回家面对猫鄙视的眼神。", "author": "佚名"},
        {"text": "人生就像打电话，不是你先挂就是我先挂。", "author": "佚名"},
        {"text": "不要着急，最好的总会在最不经意的时候出现——除了你要的外卖。", "author": "佚名"},
    ],
    "love": [
        {"text": "众里寻他千百度，蓦然回首，那人却在灯火阑珊处。", "author": "辛弃疾"},
        {"text": "两情若是久长时，又岂在朝朝暮暮。", "author": "秦观"},
        {"text": "愿得一心人，白首不相离。", "author": "卓文君"},
        {"text": "曾经沧海难为水，除却巫山不是云。", "author": "元稹"},
        {"text": "爱情不是寻找一个完美的人，而是学会用完美的眼光看待一个不完美的人。", "author": "佚名"},
        {"text": "You had me at hello.", "author": "Jerry Maguire"},
        {"text": "世间安得双全法，不负如来不负卿。", "author": "仓央嘉措"},
        {"text": "喜欢是乍见之欢，爱是久处不厌。", "author": "佚名"},
        {"text": "月色与雪色之间，你是第三种绝色。", "author": "余光中"},
        {"text": "既见君子，云胡不喜。", "author": "《诗经》"},
    ],
    "wisdom": [
        {"text": "三人行，必有我师焉。", "author": "孔子"},
        {"text": "学而不思则罔，思而不学则殆。", "author": "孔子"},
        {"text": "授人以鱼，不如授人以渔。", "author": "《老子》"},
        {"text": "宽以待人，严以律己。", "author": "古训"},
        {"text": "The only true wisdom is in knowing you know nothing.", "author": "Socrates"},
        {"text": "静以修身，俭以养德。", "author": "诸葛亮"},
        {"text": "知者不惑，仁者不忧，勇者不惧。", "author": "孔子"},
        {"text": "水至清则无鱼，人至察则无徒。", "author": "《大戴礼记》"},
        {"text": "良药苦口利于病，忠言逆耳利于行。", "author": "《增广贤文》"},
        {"text": "塞翁失马，焉知非福。", "author": "《淮南子》"},
    ],
}


def _call_llm(category_label: str) -> str:
    """调用本地 Qwen LLM 生成一条语录"""
    prompt = (
        "你是一个博学的语录大师。请生成一条引人深思的名言或语录。\n"
        f"风格：{category_label}\n"
        "要求：\n"
        "1. 可以是原创的，也可以是经典名句\n"
        "2. 中英文皆可\n"
        "3. 最后一行必须是：——作者名（如为原创则写「坐山客」）\n"
        "4. 不要解释，只输出句子和作者\n"
        "5. 句子不要太长，1-2句话即可"
    )

    payload = json.dumps({
        "model": "Qwen3.5-9B-Q4_K_M.gguf",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请给我一条{category_label}风格的语录。"},
        ],
        "temperature": 0.8,
        "max_tokens": 256,
    }).encode("utf-8")

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def daily_quote(category: str = "motivation", source: str = "auto") -> str:
    """获取一条每日一言，返回 JSON 字符串

    Args:
        category: 分类。motivation(励志) / philosophy(哲思) / healing(治愈)
                  / life(人生) / humor(幽默) / love(爱情) / wisdom(智慧)
                  默认 motivation
        source:   来源。auto(LLM生成，LLM不可用时回退名言库)
                  / curated(仅从名言库选取) / llm(仅LLM生成)

    Returns:
        JSON string:
        {
            "success": true/false,
            "quote": "语录正文",
            "author": "作者名",
            "category": "motivation",
            "category_label": "励志",
            "source_type": "llm" or "curated",
            "error": "错误信息"
        }
    """
    try:
        if category not in CATEGORIES:
            category = "motivation"

        category_label = CATEGORIES[category]

        # 从名言库随机选一条
        curated_quotes = QUOTES.get(category, QUOTES["motivation"])
        curated_pick = random.choice(curated_quotes)

        if source == "curated":
            return json.dumps({
                "success": True,
                "quote": curated_pick["text"],
                "author": curated_pick["author"],
                "category": category,
                "category_label": category_label,
                "source_type": "curated",
            }, ensure_ascii=False)

        if source == "llm":
            # 仅 LLM
            llm_output = _call_llm(category_label)
            quote_text, author = _parse_llm_output(llm_output)
            return json.dumps({
                "success": True,
                "quote": quote_text,
                "author": author,
                "category": category,
                "category_label": category_label,
                "source_type": "llm",
            }, ensure_ascii=False)

        # auto: 先试 LLM，失败回退名言库
        try:
            llm_output = _call_llm(category_label)
            quote_text, author = _parse_llm_output(llm_output)
            return json.dumps({
                "success": True,
                "quote": quote_text,
                "author": author,
                "category": category,
                "category_label": category_label,
                "source_type": "llm",
            }, ensure_ascii=False)
        except Exception:
            return json.dumps({
                "success": True,
                "quote": curated_pick["text"],
                "author": curated_pick["author"],
                "category": category,
                "category_label": category_label,
                "source_type": "curated",
            }, ensure_ascii=False)

    except Exception as e:
        # 终极回退
        curated_pick = random.choice(QUOTES["motivation"])
        return json.dumps({
            "success": True,
            "quote": curated_pick["text"],
            "author": curated_pick["author"],
            "category": "motivation",
            "category_label": "励志",
            "source_type": "curated_fallback",
            "error_detail": str(e),
        }, ensure_ascii=False)


def _parse_llm_output(text: str) -> tuple[str, str]:
    """解析 LLM 输出，提取句子和作者"""
    text = text.strip()
    # 移除可能的引号
    text = text.strip('"').strip('"').strip("'")

    # 查找 "——" 或 "—" 或 "-" 分隔的作者
    import re
    for sep in ["——", "—", " -- ", " - "]:
        if sep in text:
            parts = text.rsplit(sep, 1)
            return parts[0].strip(), parts[1].strip()

    return text, "佚名"

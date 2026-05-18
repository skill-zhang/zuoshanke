"""技能管理器 — 文件式可复用流程知识系统

Skills 是"怎么写"的知识（how），Memory 是"用户是谁"的知识（what）。

存储: ~/zuoshanke/skills/<name>/SKILL.md
格式: YAML 元信息（含 triggers）+ Markdown 正文

匹配: 按 trigger 关键词匹配用户查询，只加载命中 trigger 的 skill
Token 预算: 每次最多注入 2 个 skill
"""

import json
import os
import re
from pathlib import Path
from typing import Optional
from config.paths import SKILLS_DIR

# ── Skill Schema ──
# SKILL.md format:
# ---
# name: weather-formatting
# description: 天气查询结果格式化规范
# version: 1.0
# category: formatting
# triggers: [天气, 气温, 预报, 温度]
# ---
# # 天气格式化规范
# ...


class Skill:
    """单个 Skill 的内存表示"""
    def __init__(self, name: str, description: str = "",
                 version: str = "1.0", category: str = "general",
                 triggers: list[str] = None,
                 content: str = ""):
        self.name = name
        self.description = description
        self.version = version
        self.category = category
        self.triggers = triggers or []
        self.content = content

    def to_dict(self, include_content: bool = False) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "triggers": self.triggers,
        }
        if include_content:
            d["content"] = self.content
        return d


class SkillManager:
    """技能管理器 — 文件读写 + 触发器匹配 + 缓存"""

    def __init__(self):
        self._cache: dict[str, Skill] = {}
        self._cache_mtime: dict[str, float] = {}
        self._ensure_dir()

    # ── 目录管理 ──────────────────────────────────

    def _ensure_dir(self):
        os.makedirs(SKILLS_DIR, exist_ok=True)

    def _skill_path(self, name: str) -> str:
        return os.path.join(SKILLS_DIR, name, "SKILL.md")

    # ── 读写 ──────────────────────────────────────

    def _parse_skill(self, name: str) -> Optional[Skill]:
        """解析 SKILL.md 文件"""
        path = self._skill_path(name)
        if not os.path.isfile(path):
            return None

        # 检查缓存
        mtime = os.path.getmtime(path)
        cached = self._cache.get(name)
        if cached and self._cache_mtime.get(name) == mtime:
            return cached

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        # 解析 YAML 前注
        meta = {}
        rest = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                yaml_block = parts[1].strip()
                rest = parts[2].strip()
                for line in yaml_block.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip()
                        # 解析列表值 [a, b, c]
                        if v.startswith("[") and v.endswith("]"):
                            try:
                                v = json.loads(v)
                            except json.JSONDecodeError:
                                v = v.strip("[]").replace('"', '').split(",")
                                v = [x.strip() for x in v if x.strip()]
                        meta[k] = v

        skill = Skill(
            name=meta.get("name", name),
            description=meta.get("description", ""),
            version=str(meta.get("version", "1.0")),
            category=meta.get("category", "general"),
            triggers=meta.get("triggers", []),
            content=rest,
        )
        self._cache[name] = skill
        self._cache_mtime[name] = mtime
        return skill

    def create(self, name: str, description: str,
               content: str, triggers: list[str] = None,
               category: str = "general",
               version: str = "1.0") -> Skill:
        """创建一个新 skill"""
        dir_path = os.path.join(SKILLS_DIR, name)
        os.makedirs(dir_path, exist_ok=True)

        triggers_str = json.dumps(triggers or [], ensure_ascii=False)

        skill_text = f"""---
name: {name}
description: {description}
version: {version}
category: {category}
triggers: {triggers_str}
---

{content}
"""
        path = self._skill_path(name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(skill_text)

        skill = Skill(
            name=name,
            description=description,
            version=version,
            category=category,
            triggers=triggers or [],
            content=content,
        )
        self._cache[name] = skill
        self._cache_mtime[name] = os.path.getmtime(path)
        return skill

    def update(self, name: str, **kwargs) -> Optional[Skill]:
        """更新 skill 的元信息或内容"""
        skill = self.get(name)
        if not skill:
            return None

        content = kwargs.get("content", skill.content)
        description = kwargs.get("description", skill.description)
        triggers = kwargs.get("triggers", skill.triggers)
        category = kwargs.get("category", skill.category)
        version = kwargs.get("version", skill.version)

        return self.create(
            name=name,
            description=description,
            content=content,
            triggers=triggers,
            category=category,
            version=version,
        )

    def delete(self, name: str) -> bool:
        """删除 skill"""
        path = self._skill_path(name)
        dir_path = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(dir_path):
            return False
        import shutil
        shutil.rmtree(dir_path)
        self._cache.pop(name, None)
        self._cache_mtime.pop(name, None)
        return True

    def get(self, name: str) -> Optional[Skill]:
        """获取完整 skill（含正文）"""
        return self._parse_skill(name)

    def list_all(self) -> list[dict]:
        """列出所有 skill（不含正文，仅元信息）"""
        if not os.path.isdir(SKILLS_DIR):
            return []
        skills = []
        for entry in sorted(os.listdir(SKILLS_DIR)):
            skill_path = os.path.join(SKILLS_DIR, entry, "SKILL.md")
            if os.path.isfile(skill_path):
                skill = self._parse_skill(entry)
                if skill:
                    skills.append(skill.to_dict(include_content=False))
        return skills

    # ── 触发器匹配（用于 context 注入） ────────────

    def match_for_context(self, query: str, max_count: int = 2) -> list[Skill]:
        """根据用户查询匹配相关 skill

        匹配规则:
            1. 对 query 分词（去重）
            2. 每个 skill 的 trigger 与 query 分词做交集
            3. 按命中数量排序，取 Top-N
        """
        if not query:
            return []

        query_tokens = set(self._tokenize(query))
        skills = self.list_all()
        scored = []

        for s_meta in skills:
            skill = self._parse_skill(s_meta["name"])
            if not skill or not skill.triggers:
                continue

            # 计算 trigger 命中数
            hits = 0
            for trigger in skill.triggers:
                if trigger in query:
                    hits += 1

            if hits > 0:
                scored.append((hits, skill))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:max_count]]

    def _tokenize(self, text: str) -> list[str]:
        """分词"""
        if not text:
            return []
        tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text)
        return [t for t in tokens if len(t) >= 1]

    # ── 分类管理 ──────────────────────────────────

    def list_categories(self) -> list[dict]:
        """列出所有分类及每个分类的技能数量"""
        skills = self.list_all()
        counts: dict[str, int] = {}
        for s in skills:
            cat = s.get("category", "general")
            counts[cat] = counts.get(cat, 0) + 1
        protected = {"development", "reference", "formatting", "workflow", "general"}
        result = []
        for cat in sorted(counts.keys()):
            result.append({
                "name": cat,
                "count": counts[cat],
                "protected": cat in protected,
            })
        return result

    def rename_category(self, old_name: str, new_name: str) -> int:
        """批量重命名分类，返回受影响技能数"""
        if not new_name or not old_name:
            return 0
        count = 0
        for s_meta in self.list_all():
            if s_meta.get("category") == old_name:
                skill = self.get(s_meta["name"])
                if skill:
                    self.update(s_meta["name"], category=new_name)
                    count += 1
        return count

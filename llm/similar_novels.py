"""相似小说检索分析。

流程：
  1. 从问卷答案拼出小说信息 + 搜索 query
  2. 若配置了联网搜索（llm.search_tool），拉取候选作品
  3. 交给 LLM 分析「市面上是否有相近小说」，输出结构化结果

未配置联网搜索时降级为「仅基于模型已有知识」，结果里会标注 source。
"""
from __future__ import annotations

import json
import re

from logger import logger

# 问卷答案里对判断相似度最有用的字段（顺序即展示顺序）
_INFO_FIELDS = [
    ("novel_title", "书名"),
    ("genre", "题材"),
    ("core_hook", "核心看点"),
    ("theme", "主题"),
    ("protagonist", "主角"),
    ("protagonist_name", "主角名"),
    ("antagonist", "反派/冲突"),
    ("world_setting", "世界观"),
    ("society_structure", "社会结构"),
    ("tone", "基调"),
    ("style", "文风"),
    ("pacing", "节奏"),
    ("summary", "故事简介"),
]


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value if v)
    if isinstance(value, dict):
        return "、".join(f"{k}:{v}" for k, v in value.items() if v)
    return str(value)


def build_novel_info(answers: dict, novel_title: str = "") -> str:
    answers = answers or {}
    lines = []
    title = novel_title or _as_text(answers.get("novel_title"))
    if title:
        lines.append(f"书名：{title}")
    for key, label in _INFO_FIELDS:
        if key == "novel_title":
            continue
        text = _as_text(answers.get(key))
        if text:
            lines.append(f"{label}：{text}")
    # 兜底：把未列出的答案也带上
    known = {k for k, _ in _INFO_FIELDS}
    for key, value in answers.items():
        if key in known:
            continue
        text = _as_text(value)
        if text:
            lines.append(f"{key}：{text}")
    return "\n".join(lines) or "（问卷信息为空）"


def _build_query(answers: dict, novel_title: str = "") -> str:
    answers = answers or {}
    title = novel_title or _as_text(answers.get("novel_title"))
    parts = [title]
    for key in ("genre", "theme", "core_hook", "world_setting"):
        text = _as_text(answers.get(key))
        if text:
            parts.append(text)
    query = " ".join(p for p in parts if p).strip()
    return f"类似《{query}》的小说 相似作品" if query else "最近热门小说 相似设定"


def _parse_json(text: str) -> dict:
    clean = (text or "").strip()
    clean = re.sub(r"^```json\s*", "", clean)
    clean = re.sub(r"^```\s*", "", clean)
    clean = re.sub(r"\s*```$", "", clean).strip()
    clean = re.sub(r",\s*]", "]", clean)
    clean = re.sub(r",\s*}", "}", clean)
    try:
        return json.loads(clean)
    except Exception:
        pass
    # 尝试截取第一个 JSON 对象
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(clean[start:end + 1])
        except Exception:
            pass
    raise ValueError("LLM 返回内容不是有效 JSON")


def analyze_similar_novels(
    answers: dict,
    novel_title: str = "",
    provider: str | None = None,
    db=None,
) -> dict:
    """返回结构化分析结果。

    Raises:
        ValueError: LLM 不可用 / 返回无法解析时抛出，由路由层转成错误响应。
    """
    from llm.factory import LLMFactory
    from llm.roles import get_role
    from llm import search_tool

    novel_info = build_novel_info(answers, novel_title)

    search_used = False
    search_results = None
    try:
        if search_tool.is_search_configured(db):
            search_results = search_tool.web_search(_build_query(answers, novel_title), db=db)
            search_used = search_results is not None
    except Exception as e:
        logger.warning(f"[SimilarNovel] 联网搜索异常，降级为模型知识: {e}")

    search_text = search_tool.format_search_results(search_results)

    llm = LLMFactory.create(provider=provider, db=db)
    role = get_role("similar_novel_analyst")
    system_prompt = role.system_prompt.format(
        novel_info=novel_info, search_results=search_text
    )
    raw = llm.generate(
        prompt=role.user_prompt_template,
        system_prompt=system_prompt,
        max_tokens=getattr(role, "max_tokens", 4096),
        temperature=getattr(role, "temperature", 0.4),
        task_type="similar_novel_search",
    )

    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM 返回结构异常")

    data["search_used"] = search_used
    data["search_query"] = _build_query(answers, novel_title)
    data.setdefault("verdict", "some_overlap")
    data.setdefault("summary", "")
    data.setdefault("similar_works", [])
    data.setdefault("suggestions", [])
    logger.info(
        f"[SimilarNovel] 分析完成 search_used={search_used} "
        f"works={len(data.get('similar_works') or [])} verdict={data.get('verdict')}"
    )
    return data

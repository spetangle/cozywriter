"""
章节生成流水线（9 步）

Step 1: 聚合章节准备信息
Step 2: LLM 生成章节细纲
Step 3: 细纲评审（仅过滤 high severity）
Step 4: 按最终细纲生成正文
Step 5: 字数检查（过多→缩写 / 过少→扩写）
Step 6: 正文评审（8 维度）
Step 7: 自动决策修订
Step 8: 保存到 Chapter.content
Step 9: 章节后处理（弧光/关系/伏笔/黄金3/一致性）

每次章节生成触发自动后处理：
- 每 1 章：弧光 + 关系 + 伏笔更新
- 每 3 章：黄金三章检查（仅第 3 章）
- 每 5 章：一致性 + 连续性检查（推送用户）
"""
import json
import re
import time
import traceback
from typing import Any, Callable, Optional

from logger import logger

from llm.factory import LLMFactory
from llm.roles import get_role, ROLES, build_ai_removal_instruction
from rag.retrieval import RetrievalService


# ═══════════════════════════════════════════════════════════════
# 工具：JSON 解析
# ═══════════════════════════════════════════════════════════════

def _parse_json(text: str) -> dict | list | str:
    """宽松 JSON 解析（容忍 markdown / 前缀后缀 / 字符串内换行等常见问题）"""
    if not text or not text.strip():
        raise ValueError("empty response from LLM")
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    # 第一次尝试：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 第二次尝试：逐字符修复字符串值内的裸换行/tabs（LLM 常见问题）
    try:
        result = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(text):
            ch = text[i]
            if escape_next:
                result.append(ch)
                escape_next = False
                i += 1
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape_next = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                i += 1
                continue
            if in_string and ch == '\n':
                result.append('\\n')
                i += 1
                continue
            if in_string and ch == '\r':
                result.append('\\r')
                i += 1
                continue
            if in_string and ch == '\t':
                result.append('\\t')
                i += 1
                continue
            result.append(ch)
            i += 1
        return json.loads(''.join(result))
    except json.JSONDecodeError as e:
        # 第四次尝试：更激进的修复 - 处理未转义的引号和特殊字符
        try:
            # 尝试用正则提取JSON结构
            import re as _re
            # 找到所有顶层键值对
            json_pattern = _re.compile(r'\{[^{}]*\}', _re.DOTALL)
            matches = json_pattern.findall(text)
            if matches:
                # 取最大的匹配（最可能是完整的JSON）
                best = max(matches, key=len)
                return json.loads(best)
        except Exception:
            pass

        # 第五次尝试：逐行修复常见的JSON格式问题
        try:
            lines = text.split(chr(10))
            fixed_lines = []
            for line in lines:
                # 修复行尾缺少逗号的问题（如果下一行以"或}开头）
                stripped = line.rstrip()
                if stripped and not stripped.endswith(',') and not stripped.endswith('{') and not stripped.endswith('['):
                    # 检查是否需要添加逗号
                    next_line_idx = lines.index(line) + 1
                    if next_line_idx < len(lines):
                        next_stripped = lines[next_line_idx].strip()
                        if next_stripped.startswith('"') or next_stripped.startswith('}') or next_stripped.startswith(']'):
                            if not stripped.endswith(':') and not stripped.endswith('"'):
                                stripped += ','
                fixed_lines.append(stripped)
            fixed_text = chr(10).join(fixed_lines)
            return json.loads(fixed_text)
        except Exception:
            pass

        raise json.JSONDecodeError(
            f"JSON parse failed after all attempts: {e.msg}",
            e.doc,
            e.pos,
        ) from e


def _count_chinese_chars(text: str) -> int:
    """中文字符数（忽略标点空白）"""
    return sum(1 for c in text if "一" <= c <= "鿿")


def _call_llm(role_name: str, ctx: dict, user_msg: str, provider: str | None = None, db=None) -> str:
    """通用 LLM 调用 helper"""
    role = ROLES.get(role_name)
    if role is None:
        raise ValueError(f"Unknown role: {role_name}")
    system = role.build_system(ctx)
    user = role.build_user({**ctx, "context": user_msg})
    llm = LLMFactory.create(provider=provider, db=db)
    return llm.generate(
        prompt=user,
        system_prompt=system,
        max_tokens=role.max_tokens,
        temperature=role.temperature,
        task_type=f"chapter_pipeline_{role_name}",  # 入 log 时按 role 分类
    )


# ═══════════════════════════════════════════════════════════════
# Step 1: 章节准备信息聚合
# ═══════════════════════════════════════════════════════════════

def build_chapter_prep_info(
    db,
    project_id: int,
    chapter_id: int,
) -> dict:
    """
    聚合章节生成所需的全部上下文

    Returns:
        {
            "project_meta": ...,
            "project_outline": ...,
            "chapter_outline": ...,  # 本章细纲
            "prev_chapters_summary": "...",  # 前 N 章摘要
            "prev_chapter_ending": "...",  # 上一章结尾
            "characters": [...],  # 登场人物 + 弧光
            "active_foreshadowings": [...],
            "consistency_issues": [...],  # 当前未解决的一致性问题
            "themes": "...",
        }
    """
    from storage.models import (
        Project, Chapter, ChapterOutline, ProjectOutline,
        Theme, Character, CharacterArc, Foreshadowing, ConsistencyRecord,
        CharacterRelation,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise ValueError(f"Chapter {chapter_id} not found")

    # 本章细纲
    chapter_outline = (
        db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).first()
    )

    # 前 3 章摘要
    prev_chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.order < chapter.order)
        .order_by(Chapter.order.desc())
        .limit(3)
        .all()
    )
    prev_chapters_summary = "\n\n".join(
        [f"【第{c.order + 1}章 {c.title}】\n{(c.content or c.synopsis or '')[:500]}"
         for c in reversed(prev_chapters)]
    ) or "（这是第一章）"

    # 上一章结尾
    prev_chapter_ending = ""
    if prev_chapters:
        latest_prev = prev_chapters[0]
        prev_chapter_ending = (latest_prev.content or "")[-800:]

    # 登场人物：本章细纲的 character_ids + 当前活跃角色
    character_ids = list(chapter_outline.character_ids or []) if chapter_outline else []
    if not character_ids:
        # 兜底：取项目前 5 个角色
        chars = db.query(Character).filter(Character.project_id == project_id).limit(5).all()
    else:
        chars = db.query(Character).filter(Character.id.in_(character_ids)).all()

    arc_map = {}
    for arc in db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all():
        arc_map[arc.character_id] = arc

    character_blocks = []
    for c in chars:
        arc = arc_map.get(c.id)
        block = f"【{c.name}】({c.role})\n{c.description or ''}"
        if c.profile:
            profile_str = " / ".join(f"{k}: {v}" for k, v in c.profile.items() if v)
            if profile_str:
                block += f"\n  设定: {profile_str}"
        if arc:
            block += f"\n  弧光: {arc.arc_type} (起始={arc.start_state} → 当前={arc.current_state} → 目标={arc.end_state})"
        character_blocks.append(block)
    characters_text = "\n".join(character_blocks) or "（暂无人物设定）"

    # 活跃伏笔
    fores = db.query(Foreshadowing).filter(
        Foreshadowing.project_id == project_id,
        Foreshadowing.status.in_(["active", "planted"]),
    ).all()
    foreshadowings_text = "\n".join(
        [f"- 【{f.title}】({f.status}) {f.content[:100]}" for f in fores[:10]]
    ) or "（暂无活跃伏笔）"

    # 当前未解决的一致性问题
    issues = db.query(ConsistencyRecord).filter(
        ConsistencyRecord.project_id == project_id,
        ConsistencyRecord.is_consistent == False,
    ).limit(5).all()
    issues_text = "\n".join(
        [f"- [{i.entity_type}] {i.property_name}: {i.inconsistency_note[:100]}"
         for i in issues]
    ) or "（暂无未解决问题）"

    # 项目大纲
    proj_outline = db.query(ProjectOutline).filter(
        ProjectOutline.project_id == project_id
    ).first()
    proj_outline_text = proj_outline.outline_text if proj_outline else ""

    # 核心主旨
    themes = db.query(Theme).filter(Theme.project_id == project_id).all()
    themes_text = "\n".join(
        [f"- [{t.theme_type}] {t.title}: {t.description}" for t in themes]
    ) or "（暂无主旨）"

    return {
        "project_meta": {
            "title": project.title,
            "writing_style": project.writing_style,
            "ai_removal": project.ai味去除程度,
            "target_word_count": project.target_word_count,
            "min_words": project.word_count_min,
            "max_words": project.word_count_max,
            "description": project.description,
        },
        "project_outline_text": proj_outline_text,
        "chapter_outline": {
            "order": chapter.order,
            "title": chapter.title,
            "position": chapter_outline.chapter_position if chapter_outline else "",
            "act": chapter_outline.act_name if chapter_outline else "",
            "pacing": chapter_outline.pacing if chapter_outline else "平稳",
            "key_content": chapter_outline.key_content if chapter_outline else "",
            "plot_advance": chapter_outline.plot_advance if chapter_outline else "",
            "foreshadow_notes": chapter_outline.foreshadow_notes if chapter_outline else "",
            "conflicts": chapter_outline.conflicts if chapter_outline else [],
            "highlights": chapter_outline.highlights if chapter_outline else [],
        } if chapter_outline else None,
        "prev_chapters_summary": prev_chapters_summary,
        "prev_chapter_ending": prev_chapter_ending,
        "characters": character_blocks,
        "active_foreshadowings": foreshadowings_text,
        "consistency_issues": issues_text,
        "themes": themes_text,
    }


# ═══════════════════════════════════════════════════════════════
# Step 2: 章节细纲生成
# ═══════════════════════════════════════════════════════════════

def generate_chapter_outline(db, project_id: int, chapter_id: int, provider: str | None = None, guide: str = "") -> dict:
    """LLM 生成章节细纲（不存库，返回给上层走评审）"""
    prep = build_chapter_prep_info(db, project_id, chapter_id)
    project = db.query(__import__("storage.models", fromlist=["Project"]).Project).filter(
        __import__("storage.models", fromlist=["Project"]).Project.id == project_id
    ).first()

    outline_ctx = {
        "chapter_position": (prep["chapter_outline"] or {}).get("position", "发展"),
        "pacing": (prep["chapter_outline"] or {}).get("pacing", "平稳"),
        "key_content": (prep["chapter_outline"] or {}).get("key_content", ""),
        "plot_advance": (prep["chapter_outline"] or {}).get("plot_advance", ""),
        "prep_info": _format_prep_for_llm(prep),
        "target_word_count": prep["project_meta"]["target_word_count"],
        "guide": guide,
    }

    raw = _call_llm("chapter_outline_gen", outline_ctx, "", provider)
    return _parse_json(raw)


# ═══════════════════════════════════════════════════════════════
# Step 3: 细纲评审
# ═══════════════════════════════════════════════════════════════

def review_chapter_outline(outline: dict, prep_info: dict, provider: str | None = None) -> dict:
    """评审细纲，仅过滤 high severity"""
    ctx = {
        "outline": json.dumps(outline, ensure_ascii=False, indent=2),
    }
    raw = _call_llm("outline_reviewer", ctx, "", provider)
    return _parse_json(raw)


# ═══════════════════════════════════════════════════════════════
# Step 4: 章节正文生成
# ═══════════════════════════════════════════════════════════════

def generate_chapter_text(
    db, project_id: int, chapter_id: int,
    final_outline: dict, provider: str | None = None,
) -> str:
    """按最终细纲生成章节正文"""
    from storage.models import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    prep = build_chapter_prep_info(db, project_id, chapter_id)

    # 用现有的 writing role，但拼更厚的 context
    writing_ctx = {
        "writing_style": project.writing_style or "平实",
        "ai_removal_instruction": build_ai_removal_instruction(project.ai味去除程度) if project.ai味去除程度 else "",
        "themes": prep["themes"],
        "characters": "\n".join(prep["characters"]) or "（无）",
        "character_arcs": "（参见上文 character 段）",
        "world": prep["project_outline_text"] or "（无项目大纲）",
        "foreshadowings": prep["active_foreshadowings"],
        "chapters": prep["prev_chapters_summary"],
        "target_word_count": prep["project_meta"]["target_word_count"],
        "word_count_range": f"{prep['project_meta']['min_words']}~{prep['project_meta']['max_words']} 字",
    }

    system = ROLES["writing"].build_system(writing_ctx)

    # user：拼细纲 + 准备信息 + 上章结尾
    user_msg = (
        f"【本章细纲（严格遵循）】\n{json.dumps(final_outline, ensure_ascii=False, indent=2)}\n\n"
        f"【上章结尾（衔接用）】\n{prep['prev_chapter_ending']}\n\n"
        f"【登场人物】\n" + "\n".join(prep["characters"]) + "\n\n"
        f"【目标字数】{prep['project_meta']['target_word_count']} 字\n\n"
        f"请按细纲生成正文，**不要偏离细纲**。"
    )

    llm = LLMFactory.create(provider=provider)
    return llm.generate(
        prompt=user_msg,
        system_prompt=system,
        max_tokens=ROLES["writing"].max_tokens,
        temperature=ROLES["writing"].temperature,
        task_type="chapter_pipeline_writing",  # 入 log 时分类
    )


# ═══════════════════════════════════════════════════════════════
# Step 5: 字数调整
# ═══════════════════════════════════════════════════════════════

def adjust_word_count(
    content: str, target: int, min_w: int, max_w: int,
    outline: dict, provider: str | None = None,
) -> str:
    """根据目标字数调整正文（过多缩写 / 过少扩写）"""
    actual = _count_chinese_chars(content)
    if min_w <= actual <= max_w:
        return content
    ctx = {
        "target_word_count": target,
        "current_word_count": actual,
        "outline": json.dumps(outline, ensure_ascii=False, indent=2) if isinstance(outline, dict) else str(outline),
        "content": content[:6000],  # 截断避免超长
    }
    try:
        if actual > max_w:
            raw = _call_llm("compressor", ctx, "", provider)
            data = _parse_json(raw)
            return data.get("compressed_text", content)
        else:
            raw = _call_llm("expander", ctx, "", provider)
            data = _parse_json(raw)
            return data.get("expanded_text", content)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[adjust_word_count] JSON parse failed: {e}, returning original content")
        return content


# ═══════════════════════════════════════════════════════════════
# Step 6: 正文评审
# ═══════════════════════════════════════════════════════════════

def review_chapter_text(
    db, project_id: int, chapter_id: int, content: str, provider: str | None = None,
) -> dict:
    """8 维度评审"""
    from storage.models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    ctx = {
        "title": project.title if project else "",
        "content": content[:8000],
    }
    raw = _call_llm("review", ctx, "", provider)
    return _parse_json(raw)


# ═══════════════════════════════════════════════════════════════
# Step 7: 修订决策
# ═══════════════════════════════════════════════════════════════

def decide_revision(review_data: dict, outline: dict, content: str, provider: str | None = None) -> dict:
    """根据评审分决定是否自动修订

    决策依据：综合分（满分 100），由 8 维度加权求和得出。
    """
    from llm.scoring import calculate_overall_score
    scores = review_data.get("scores", {})
    overall = calculate_overall_score(scores)
    # 同时给出平均分供 LLM 决策时参考（避免单维度极端值干扰）
    avg = (sum(scores.values()) / len(scores)) if scores else 0
    ctx = {
        "scores": json.dumps(scores, ensure_ascii=False, indent=2),
        "overall_score": overall,            # 加权综合分（0-100）
        "avg_score": round(avg, 2),          # 简单平均分（0-10），仅供决策参考
        "outline": json.dumps(outline, ensure_ascii=False, indent=2),
        "content": content[:4000],
    }
    raw = _call_llm("revision_decider", ctx, "", provider)
    return _parse_json(raw)


def revise_chapter_text(
    content: str, focus_areas: list, outline: dict,
    review_data: dict, provider: str | None = None,
) -> str:
    """调用现有 revision role 修订"""
    ctx = {
        "critique": review_data.get("critique", ""),
        "suggestions": "\n".join(review_data.get("suggestions", [])),
    }
    system = ROLES["revision"].build_system(ctx)
    user = (
        f"原文：\n{content[:6000]}\n\n"
        f"重点关注：{', '.join(focus_areas or [])}\n\n"
        f"请按评审意见修订。"
    )
    llm = LLMFactory.create(provider=provider)
    return llm.generate(
        prompt=user,
        system_prompt=system,
        max_tokens=ROLES["revision"].max_tokens,
        temperature=ROLES["revision"].temperature,
        task_type="chapter_pipeline_revision",  # 入 log 时分类
    )


# ═══════════════════════════════════════════════════════════════
# Step 9: 章节后处理
# ═══════════════════════════════════════════════════════════════

def run_post_chapter_processing(
    db, project_id: int, chapter_id: int, content: str,
    provider: str | None = None,
) -> dict:
    """章节后处理：弧光 + 关系 + 伏笔 + 黄金3 + 一致性"""
    from storage.models import (
        Character, CharacterArc, CharacterRelation, Foreshadowing, Chapter,
    )

    result = {
        "arc_updates": [],
        "relation_updates": [],
        "foreshadow_updates": [],
        "new_characters": [],
        "notifications": [],
    }

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return result
    
    # 确保 content 不为 None
    if not chapter.content:
        logger.warning(f"[PostChapter] chapter {chapter_id} has no content, skipping LLM calls")
        chapter.content = ""
        db.commit()
    chars = db.query(Character).filter(Character.project_id == project_id).all()
    current_state = "\n".join(
        [f"- {c.name}: 描述={c.description or ''}, profile={json.dumps(c.profile, ensure_ascii=False)}"
         for c in chars]
    )
    relations = db.query(CharacterRelation).filter(
        CharacterRelation.project_id == project_id
    ).all()
    char_map = {c.id: c.name for c in chars}
    current_relations = "\n".join(
        [f"- {char_map.get(r.from_character_id, '?')} → {char_map.get(r.to_character_id, '?')}: {r.relation_type} (强度{r.strength}, {r.status})"
         for r in relations]
    ) or "（暂无关系）"

    ctx = {
        "content": (chapter.content or "")[:8000],
        "current_state": current_state,
        "current_relations": current_relations,
    }
    try:
        raw = _call_llm("post_chapter", ctx, "", provider)
        post_data = _parse_json(raw)
    except Exception as e:
        logger.warning(f"[PostChapter] LLM failed: {e}")
        post_data = {}

    # 应用弧光更新
    for arc_upd in post_data.get("arc_updates", []):
        cname = arc_upd.get("character_name", "")
        target_char = next((c for c in chars if c.name == cname), None)
        if target_char:
            arc = (
                db.query(CharacterArc)
                .filter(CharacterArc.character_id == target_char.id)
                .first()
            )
            if arc:
                arc.current_state = arc_upd.get("current_state", arc.current_state)
                arc.key_behavior = arc_upd.get("key_behavior", arc.key_behavior)
                if arc_upd.get("arc_type") and arc_upd["arc_type"] != arc.arc_type:
                    arc.arc_type = arc_upd["arc_type"]
                result["arc_updates"].append({
                    "character": cname,
                    "new_state": arc.current_state,
                })

    # 应用关系更新
    for rel_upd in post_data.get("relation_updates", []):
        from_name = rel_upd.get("from", "")
        to_name = rel_upd.get("to", "")
        from_char = next((c for c in chars if c.name == from_name), None)
        to_char = next((c for c in chars if c.name == to_name), None)
        if not from_char or not to_char or from_char.id == to_char.id:
            continue
        rel = (
            db.query(CharacterRelation)
            .filter(
                CharacterRelation.from_character_id == from_char.id,
                CharacterRelation.to_character_id == to_char.id,
            )
            .first()
        )
        if rel:
            if rel_upd.get("new_type"):
                rel.relation_type = rel_upd["new_type"]
            if rel_upd.get("description"):
                rel.description = rel_upd["description"]
            if "strength_delta" in rel_upd:
                new_strength = max(1, min(10, rel.strength + int(rel_upd["strength_delta"])))
                rel.strength = new_strength
            if rel_upd.get("status"):
                rel.status = rel_upd["status"]
            result["relation_updates"].append({
                "from": from_name, "to": to_name,
                "new_type": rel.relation_type, "strength": rel.strength,
            })

    # 创建新角色
    for new_c in post_data.get("new_characters", []):
        nc = Character(
            project_id=project_id,
            name=new_c.get("name", "未命名"),
            role=new_c.get("role", "配角"),
            profile={k: v for k, v in new_c.items() if k in ["identity", "personality"]},
            description=new_c.get("first_appearance_note", ""),
        )
        db.add(nc)
        result["new_characters"].append({"name": nc.name, "role": nc.role})

    db.commit()

    # 9.2 伏笔状态管理
    active_fores = db.query(Foreshadowing).filter(
        Foreshadowing.project_id == project_id,
        Foreshadowing.status.in_(["active", "planted"]),
    ).all()
    fores_text = "\n".join(
        [f"- [{f.id}] {f.title} ({f.status}): {f.content[:80]}" for f in active_fores]
    ) or "（暂无活跃伏笔）"
    ctx = {
        "content": content[:6000],
        "active_foreshadowings": fores_text,
    }
    try:
        raw = _call_llm("foreshadow_updater", ctx, "", provider)
        fore_data = _parse_json(raw)
    except Exception as e:
        logger.warning(f"[ForeshadowUpdate] LLM failed: {e}")
        fore_data = {}

    for f_upd in fore_data.get("foreshadow_updates", []):
        title = f_upd.get("title", "")
        target = next((f for f in active_fores if f.title == title), None)
        if target and f_upd.get("new_status") in ["active", "planted", "resolved", "abandoned"]:
            target.status = f_upd["new_status"]
            result["foreshadow_updates"].append({
                "title": title,
                "new_status": target.status,
            })

    for new_f in fore_data.get("new_foreshadowings", []):
        fore = Foreshadowing(
            project_id=project_id,
            title=new_f.get("title", "未命名"),
            content=new_f.get("content", ""),
            plant_order=chapter.order,
            status="planted",
        )
        db.add(fore)
        result["foreshadow_updates"].append({
            "title": fore.title,
            "new_status": "planted (新)",
        })

    db.commit()

    # 9.3 / 9.4 自动检查触发
    if chapter.order == 2:  # 第 3 章（order 从 0 起）
        result["notifications"].append({
            "type": "golden_3",
            "title": "黄金三章检查",
            "message": "前 3 章已写完，自动诊断开局质量...",
            "auto_run": True,
        })
        # 立即跑黄金 3 章检查
        golden3_result = run_golden_3_check(db, project_id, provider)
        result["golden_3"] = golden3_result
        if golden3_result.get("verdict") in ("needs_adjustment", "poor"):
            result["notifications"].append({
                "type": "golden_3_warning",
                "title": "⚠️ 黄金三章需关注",
                "message": golden3_result.get("summary", ""),
                "score": golden3_result.get("score"),
                "recommendations": golden3_result.get("recommendations", []),
                "requires_user_action": True,
            })

    if (chapter.order + 1) % 5 == 0:  # 第 5、10、15... 章
        result["notifications"].append({
            "type": "consistency_check",
            "title": f"5 章一致性检查（第 {chapter.order + 1} 章）",
            "message": "自动检查前 5 章连续性...",
            "auto_run": True,
        })
        consistency_result = run_quick_consistency_check(db, project_id, chapter.order, provider)
        result["consistency"] = consistency_result
        if consistency_result.get("has_issues"):
            result["notifications"].append({
                "type": "consistency_warning",
                "title": "⚠️ 一致性问题",
                "message": consistency_result.get("summary", ""),
                "issues": consistency_result.get("issues", []),
                "requires_user_action": True,
            })

    return result


def run_golden_3_check(db, project_id: int, provider: str | None = None) -> dict:
    """黄金三章检查"""
    from storage.models import ProjectOutline, Chapter, Theme
    proj_outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    themes = db.query(Theme).filter(Theme.project_id == project_id).all()
    first_3 = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.order)
        .limit(3)
        .all()
    )
    summary = "\n\n".join(
        [f"【第{c.order + 1}章 {c.title}】\n{(c.content or c.synopsis or '')[:800]}"
         for c in first_3]
    )
    ctx = {
        "chapters_summary": summary,
        "opening_outline": (proj_outline.outline_text if proj_outline else "")[:1500],
        "themes": "\n".join([f"- [{t.theme_type}] {t.title}: {t.description}" for t in themes]),
    }
    try:
        raw = _call_llm("golden_3_checker", ctx, "", provider)
        return _parse_json(raw)
    except Exception as e:
        logger.warning(f"[Golden3] LLM failed: {e}")
        return {"verdict": "unknown", "score": 0, "summary": str(e)}


def run_quick_consistency_check(
    db, project_id: int, current_chapter_order: int, provider: str | None = None,
) -> dict:
    """每 5 章跑一次连续性检查"""
    from storage.models import Chapter, Character, ProjectOutline
    last_5 = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.order <= current_chapter_order,
        )
        .order_by(Chapter.order.desc())
        .limit(5)
        .all()
    )
    last_5 = list(reversed(last_5))
    if not last_5:
        return {"has_issues": False, "issues": [], "summary": "（章节不足）"}

    content = "\n\n".join(
        [f"【第{c.order + 1}章 {c.title}】\n{(c.content or '')[:1500]}" for c in last_5]
    )
    chars = db.query(Character).filter(Character.project_id == project_id).all()
    char_text = "\n".join(
        [f"- {c.name}: {c.description or ''} | profile={json.dumps(c.profile, ensure_ascii=False)}"
         for c in chars]
    )
    proj_outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    outline_text = proj_outline.outline_text if proj_outline else ""

    # 复用 consistency_checker role
    ctx = {
        "characters": char_text,
        "world": outline_text[:1500],
        "foreshadowings": "（参见前文）",
    }
    user = f"【近 5 章正文】\n{content[:8000]}"
    try:
        raw = _call_llm("consistency", ctx, user, provider)
        data = _parse_json(raw)
        return {
            "has_issues": bool(data.get("issues")),
            "issues": data.get("issues", []),
            "summary": data.get("summary", ""),
        }
    except Exception as e:
        logger.warning(f"[ConsistencyCheck] LLM failed: {e}")
        return {"has_issues": False, "issues": [], "summary": str(e)}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _format_prep_for_llm(prep: dict) -> str:
    """把 prep_info dict 格式化成 LLM 可读的文本块"""
    # 防御：chapter_outline 可能是 None（项目未建 ChapterOutline）→ 用 {} 兜底
    co = prep.get("chapter_outline") if isinstance(prep.get("chapter_outline"), dict) else {}

    parts = [
        f"【项目元信息】\n标题: {prep['project_meta']['title']}\n文风: {prep['project_meta']['writing_style']}\n去AI味: {prep['project_meta']['ai_removal']}",
        f"【项目大纲】\n{prep['project_outline_text'] or '（无）'}",
        f"【核心主旨】\n{prep['themes']}",
        f"【本章细纲（来自 ChapterOutline）】\n"
        f"  位置: {co.get('position', '')} · 节奏: {co.get('pacing', '')}\n"
        f"  关键内容: {co.get('key_content', '')}\n"
        f"  剧情推进: {co.get('plot_advance', '')}\n"
        f"  伏笔动作: {co.get('foreshadow_notes', '')}",
        f"【前 3 章摘要】\n{prep['prev_chapters_summary']}",
        f"【上章结尾】\n{prep['prev_chapter_ending'][-500:]}",
        f"【登场人物】\n" + "\n".join(prep["characters"]),
        f"【活跃伏笔】\n{prep['active_foreshadowings']}",
        f"【未解决的一致性问题】\n{prep['consistency_issues']}",
    ]
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 主编排：9 步流水线
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 9 步流水线元数据：供前端展示任务清单/进度
# ═══════════════════════════════════════════════════════════════

# 9 步的"展示名 + 权重"（用于前端进度条）
PIPELINE_STAGES_META = [
    {"id": "1_prep",          "label": "准备上下文",   "weight": 1},
    {"id": "2_outline_gen",   "label": "生成章节细纲", "weight": 2},
    {"id": "3_outline_review","label": "细纲评审",     "weight": 1},
    {"id": "4_text_gen",      "label": "生成正文",     "weight": 4},
    {"id": "5_word_adjust",   "label": "字数调整",     "weight": 1},
    {"id": "6_review",        "label": "正文评审",     "weight": 2},
    {"id": "7_revise",        "label": "自动修订",     "weight": 3},
    {"id": "8_save",          "label": "保存到数据库", "weight": 1},
    {"id": "9_post",          "label": "后处理",       "weight": 2},
]
_TOTAL_WEIGHT = sum(s["weight"] for s in PIPELINE_STAGES_META)  # 17


def run_chapter_generation_pipeline(
    db, project_id: int, chapter_id: int, provider: str | None = None,
    auto_revise: bool = True, revision_threshold: float = 6.5,
    progress_cb: Optional[Callable[[str, str, dict], None]] = None,
    guide: str = "",
) -> dict:
    """
    9 步章节生成流水线

    Args:
        progress_cb: 可选回调 fn(stage_id, status, info) → None
                     status: "running" | "completed" | "failed"
                     info: {"label", "duration_ms", "weight", ...}
                     用于把 stage 状态实时回写到 task.result / task.progress

    Returns:
        {
            "status": "completed" | "failed",
            "stages": {step_name: {status, data, duration_ms}},
            "chapter_content": "...",
            "review": {...},
            "post_processing": {...},
            "final_word_count": int,
        }
    """
    from storage.models import Chapter, ChapterVersion
    start_time = time.time()
    stages = {}
    completed_weight = 0  # 累计已完成权重（用于计算 task.progress）

    def _notify(stage_id: str, status: str, info: dict):
        if progress_cb:
            try:
                progress_cb(stage_id, status, info)
            except Exception as cb_err:
                logger.warning(f"[Pipeline] progress_cb error: {cb_err}")

    def _run_stage(name: str, fn) -> tuple[Any, float]:
        nonlocal completed_weight
        t0 = time.time()
        meta = next((m for m in PIPELINE_STAGES_META if m["id"] == name), None)
        label = meta["label"] if meta else name
        # 通知"开始"
        _notify(name, "running", {
            "label": label,
            "weight": meta["weight"] if meta else 1,
            "started_at": t0,
        })
        try:
            result = fn()
            duration_ms = (time.time() - t0) * 1000
            stages[name] = {"status": "completed", "duration_ms": duration_ms, "data": result}
            completed_weight += (meta["weight"] if meta else 1)
            # 通知"完成"（带最新进度）
            notify_info = {
                "label": label,
                "weight": meta["weight"] if meta else 1,
                "duration_ms": duration_ms,
                "progress_pct": min(99, round(completed_weight / _TOTAL_WEIGHT * 100)),
            }
            # 如果是评审阶段，提取评审得分
            # 综合分改用加权求和（满分 100），前端用 0-100 展示
            if name in ("3_outline_review", "6_review") and isinstance(result, dict):
                from llm.scoring import calculate_overall_score
                scores = result.get("scores", {})
                if scores:
                    notify_info["score"] = calculate_overall_score(scores)
                elif "overall_score" in result:
                    notify_info["score"] = result["overall_score"]
            _notify(name, "completed", notify_info)
            return result, duration_ms
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            tb = traceback.format_exc()
            logger.error(f"[Pipeline] stage {name} failed: {e}\n{tb}")
            stages[name] = {"status": "failed", "error": str(e), "duration_ms": duration_ms}
            _notify(name, "failed", {
                "label": label,
                "error": str(e),
                "duration_ms": duration_ms,
            })
            raise


    try:
        # Step 1: 准备
        stages["1_prep"], _ = _run_stage(
            "1_prep",
            lambda: build_chapter_prep_info(db, project_id, chapter_id),
        )

        # Step 2: 细纲生成
        stages["2_outline_gen"], _ = _run_stage(
            "2_outline_gen",
            lambda: generate_chapter_outline(db, project_id, chapter_id, provider, guide),
        )

        # Step 3: 细纲评审
        def _review():
            r = review_chapter_outline(
                stages["2_outline_gen"],
                stages["1_prep"],
                provider,
            )
            # 如果有 high severity 且建议明确 → 修订
            if r.get("verdict") == "needs_revision":
                high_issues = [i for i in r.get("issues", []) if i.get("severity") == "high"]
                if high_issues:
                    # 修订一遍：把 issues 喂回去再生成
                    suggestions = "\n".join(
                        [f"- {i.get('type')}: {i.get('description')} → 修复: {i.get('suggestion', '')}"
                         for i in high_issues]
                    )
                    new_outline = _revise_outline(
                        stages["2_outline_gen"],
                        stages["1_prep"],
                        suggestions,
                        provider,
                    )
                    stages["2_outline_gen"] = new_outline
            return r
        stages["3_outline_review"], _ = _run_stage("3_outline_review", _review)

        # Step 4: 正文生成
        stages["4_text_gen"], _ = _run_stage(
            "4_text_gen",
            lambda: generate_chapter_text(
                db, project_id, chapter_id, stages["2_outline_gen"], provider,
            ),
        )

        # Step 5: 字数调整
        def _adjust():
            meta = stages["1_prep"]["project_meta"]
            return adjust_word_count(
                stages["4_text_gen"],
                meta["target_word_count"],
                meta["min_words"],
                meta["max_words"],
                stages["2_outline_gen"],
                provider,
            )
        stages["5_word_adjust"], _ = _run_stage("5_word_adjust", _adjust)

        # Step 6: 正文评审
        stages["6_review"], _ = _run_stage(
            "6_review",
            lambda: review_chapter_text(
                db, project_id, chapter_id, stages["5_word_adjust"], provider,
            ),
        )

        # Step 7: 修订决策
        def _decide():
            decision = decide_revision(
                stages["6_review"],
                stages["2_outline_gen"],
                stages["5_word_adjust"],
                provider,
            )
            if decision.get("decision") == "revise" and auto_revise:
                revised = revise_chapter_text(
                    stages["5_word_adjust"],
                    decision.get("focus_areas", []),
                    stages["2_outline_gen"],
                    stages["6_review"],
                    provider,
                )
                # 修订后重审（可选）
                return {"decision": decision, "revised_text": revised, "was_revised": True}
            return {"decision": decision, "revised_text": stages["5_word_adjust"], "was_revised": False}
        stages["7_revise"], _ = _run_stage("7_revise", _decide)

        # Step 8: 保存
        def _save():
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                raise ValueError("Chapter not found")
            final_text = stages["7_revise"]["revised_text"]
            chapter.content = final_text
            chapter.word_count = _count_chinese_chars(final_text)
            # 备份版本
            version = ChapterVersion(
                chapter_id=chapter_id,
                content=final_text,
                version_num=_next_version_num(db, chapter_id),
            )
            db.add(version)
            db.commit()
            return final_text
        final_text, _ = _run_stage("8_save", _save)

        # Step 9: 后处理
        stages["9_post"], _ = _run_stage(
            "9_post",
            lambda: run_post_chapter_processing(
                db, project_id, chapter_id, final_text, provider,
            ),
        )

        # ─── 保存细纲到数据库 ───
        try:
            from storage.models import ChapterOutline
            # 修复：stage id 应对齐 PIPELINE_STAGES_META ("2_outline_gen")
            # 之前误写为 "3_outline"，导致细纲从未入库 → 前端显示"暂无细纲"
            outline_raw = stages.get("2_outline_gen", {})
            outline_data = outline_raw.get("data", outline_raw) if isinstance(outline_raw, dict) else {}
            if isinstance(outline_data, dict):
                # 简单字段（顶层）—— 与 chapter_outline_gen role 顶层输出对齐
                chapter_position = outline_data.get("chapter_position", "")
                key_content      = outline_data.get("key_content", "")
                plot_advance     = outline_data.get("plot_advance", "")
                foreshadow_notes = outline_data.get("foreshadow_notes", "")
                conflicts        = outline_data.get("conflicts", [])
                highlights       = outline_data.get("highlights", [])
                target_word_count = outline_data.get("target_word_count", 0)
                min_word_count   = outline_data.get("min_word_count", 0)
                max_word_count   = outline_data.get("max_word_count", 0)
                pacing           = outline_data.get("pacing", "平稳")
                # 丰富结构（保存到 JSON 列）—— role 输出中的 qi_cheng_zhuan_he / pacing_hooks / reversals
                qi_cheng_zhuan_he = outline_data.get("qi_cheng_zhuan_he", {})
                pacing_hooks     = outline_data.get("pacing_hooks", [])
                reversals        = outline_data.get("reversals", [])
                # 详细字段（保存到 notes）—— 给后续修订阶段做上下文
                notes_payload = {
                    "scenes": outline_data.get("scenes", []),
                    "foreshadow_actions": outline_data.get("foreshadow_actions", []),
                    "character_developments": outline_data.get("character_developments", []),
                    "word_count_check": outline_data.get("word_count_check", ""),
                }
                notes_text = json.dumps(notes_payload, ensure_ascii=False)

                existing = db.query(ChapterOutline).filter(
                    ChapterOutline.chapter_id == chapter_id
                ).first()
                if existing:
                    existing.chapter_position = chapter_position
                    existing.key_content       = key_content
                    existing.plot_advance      = plot_advance
                    existing.foreshadow_notes  = foreshadow_notes
                    existing.conflicts         = conflicts
                    existing.highlights        = highlights
                    existing.target_word_count = target_word_count
                    existing.min_word_count    = min_word_count
                    existing.max_word_count    = max_word_count
                    existing.pacing            = pacing
                    existing.qi_cheng_zhuan_he = qi_cheng_zhuan_he
                    existing.pacing_hooks      = pacing_hooks
                    existing.reversals         = reversals
                    existing.notes             = notes_text
                    existing.status            = "completed"
                else:
                    outline = ChapterOutline(
                        chapter_id=chapter_id,
                        chapter_position=chapter_position,
                        key_content=key_content,
                        plot_advance=plot_advance,
                        foreshadow_notes=foreshadow_notes,
                        conflicts=conflicts,
                        highlights=highlights,
                        target_word_count=target_word_count,
                        min_word_count=min_word_count,
                        max_word_count=max_word_count,
                        pacing=pacing,
                        qi_cheng_zhuan_he=qi_cheng_zhuan_he,
                        pacing_hooks=pacing_hooks,
                        reversals=reversals,
                        notes=notes_text,
                        status="completed",
                    )
                    db.add(outline)
                db.commit()
                logger.info(
                    f"[Pipeline] saved outline for chapter {chapter_id} "
                    f"(key_content={len(key_content)}字 plot_advance={len(plot_advance)}字)"
                )
        except Exception as e:
            logger.warning(f"[Pipeline] failed to save outline: {e}")

        # ─── 保存评审报告到数据库 ───
        try:
            from storage.models import ReviewSession
            from llm.scoring import calculate_overall_score
            # 修复：stage id 应对齐 PIPELINE_STAGES_META ("6_review")
            # 之前误写为 "7_review"，导致评审报告从未入库 → 前端"章节评分/评审报告"为空
            # 综合分改用 llm.scoring.calculate_overall_score：8 维度加权求和，满分 100
            review_raw = stages.get("6_review", {})
            review_data = review_raw.get("data", review_raw) if isinstance(review_raw, dict) else {}
            if isinstance(review_data, dict):
                scores = review_data.get("scores", {})
                overall = calculate_overall_score(scores)  # 0-100 加权综合分
                session = ReviewSession(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    session_type="chapter",
                    content_reviewed=final_text[:2000],
                    score_consistency=scores.get("consistency", 0),
                    score_pacing=scores.get("pacing", 0),
                    score_style=scores.get("style", 0),
                    score_ai_removal=scores.get("ai_removal", 0),
                    score_word_count=scores.get("word_count", 0),
                    score_foreshadowing=scores.get("foreshadowing", 0),
                    score_character_arc=scores.get("character_arc", 0),
                    score_thematic=scores.get("thematic", 0),
                    overall_score=overall,
                    critique=review_data.get("critique", ""),
                    suggestions=review_data.get("suggestions", []),
                )
                db.add(session)
                db.commit()
                logger.info(f"[Pipeline] saved review for chapter {chapter_id}, weighted score={overall}/100")
        except Exception as e:
            logger.warning(f"[Pipeline] failed to save review: {e}")

        total_ms = (time.time() - start_time) * 1000
        logger.info(f"[Pipeline] chapter {chapter_id} done in {total_ms/1000:.1f}s")

        return {
            "status": "completed",
            "stages": stages,
            "chapter_content": final_text,
            "final_word_count": _count_chinese_chars(final_text),
            "post_processing": stages["9_post"],
            "total_duration_ms": total_ms,
        }

    except Exception as e:
        logger.error(f"[Pipeline] failed: {e}")
        return {
            "status": "failed",
            "stages": stages,
            "error": str(e),
            "total_duration_ms": (time.time() - start_time) * 1000,
        }


def _revise_outline(outline: dict, prep: dict, suggestions: str, provider: str | None = None) -> dict:
    """细纲修订：在原细纲基础上根据评审建议重做"""
    ctx = {
        "chapter_position": (prep["chapter_outline"] or {}).get("position", "发展"),
        "pacing": (prep["chapter_outline"] or {}).get("pacing", "平稳"),
        "key_content": (prep["chapter_outline"] or {}).get("key_content", ""),
        "plot_advance": (prep["chapter_outline"] or {}).get("plot_advance", ""),
        "prep_info": _format_prep_for_llm(prep) + f"\n\n【需修复的严重问题】\n{suggestions}",
        "target_word_count": prep["project_meta"]["target_word_count"],
    }
    raw = _call_llm("chapter_outline_gen", ctx, "", provider)
    return _parse_json(raw)


def _next_version_num(db, chapter_id: int) -> int:
    from storage.models import ChapterVersion
    last = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .first()
    )
    return (last.version_num + 1) if last else 1



# ═══════════════════════════════════════════════════════════════
# 章节修订（根据细纲和评审报告重新生成正文）
# ═══════════════════════════════════════════════════════════════

def run_chapter_revise(
    db, project_id: int, chapter_id: int, provider: str | None = None,
    progress_cb: Optional[Callable[[str, str, dict], None]] = None,
    task_id: str = "",
) -> dict:
    """
    章节修订：根据已生成的细纲和评审报告，由LLM重新生成正文。
    旧版正文标记为废稿，移入废纸篓（ChapterVersion）。
    """
    from sqlalchemy import func
    from storage.models import Chapter, ChapterVersion, ChapterOutline

    start_time = time.time()
    stages = {}
    completed_weight = 0
    total_weight = 8  # 8 steps

    def _notify(stage_id: str, status: str, info: dict):
        if progress_cb:
            try:
                progress_cb(stage_id, status, info)
            except Exception as cb_err:
                logger.warning(f"[Revise] progress_cb error: {cb_err}")

    def _run_stage(name: str, fn, weight: int = 1) -> tuple:
        """执行单个阶段，捕获异常，通知进度"""
        nonlocal completed_weight
        label = name
        _notify(name, "running", {"label": label})
        t0 = time.time()
        try:
            result = fn()
            duration_ms = (time.time() - t0) * 1000
            stages[name] = {"status": "completed", "duration_ms": duration_ms, "data": result}
            completed_weight += weight
            notify_info = {
                "label": label,
                "duration_ms": duration_ms,
                "progress_pct": min(99, round(completed_weight / total_weight * 100)),
            }
            # 评审阶段提取得分（加权综合分，满分 100）
            if "review" in name and isinstance(result, dict):
                from llm.scoring import calculate_overall_score
                scores = result.get("scores", {})
                if scores:
                    notify_info["score"] = calculate_overall_score(scores)
                elif "overall_score" in result:
                    notify_info["score"] = result["overall_score"]
            _notify(name, "completed", notify_info)
            return result, duration_ms
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            tb = traceback.format_exc()
            logger.error(f"[Revise] stage {name} failed: {e}\n{tb}")
            stages[name] = {"status": "failed", "error": str(e), "duration_ms": duration_ms}
            _notify(name, "failed", {"label": label, "error": str(e), "duration_ms": duration_ms})
            raise

    try:
        # 获取章节
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise ValueError(f"章节不存在: {chapter_id}")
        if not chapter.content:
            raise ValueError("章节没有正文内容，无法修订")

        # Step 1: 获取细纲
        def _get_outline():
            outline = db.query(ChapterOutline).filter(
                ChapterOutline.chapter_id == chapter_id
            ).first()
            if outline:
                return {
                    "key_content": outline.key_content or "",
                    "plot_advance": outline.plot_advance or "",
                    "conflicts": outline.conflicts or [],
                    "highlights": outline.highlights or [],
                    "foreshadows": outline.foreshadows or [],
                    "character_changes": outline.character_changes or [],
                }
            return {}

        stages["1_get_outline"], _ = _run_stage("1_get_outline", _get_outline)

        # Step 2: 保存旧正文为废稿
        def _save_old_version():
            # 获取当前最大版本号
            max_ver = db.query(func.max(ChapterVersion.version_num)).filter(
                ChapterVersion.chapter_id == chapter_id
            ).scalar() or 0
            old_version = ChapterVersion(
                chapter_id=chapter_id,
                content=chapter.content,
                version_num=max_ver + 1,
            )
            db.add(old_version)
            db.commit()
            return {"saved": True, "version_num": max_ver + 1}

        stages["2_save_old"], _ = _run_stage("2_save_old", _save_old_version)

        # Step 3: 获取评审报告
        def _get_review():
            from storage.models import ReviewSession
            review = db.query(ReviewSession).filter(
                ReviewSession.chapter_id == chapter_id,
                ReviewSession.session_type == "chapter"
            ).order_by(ReviewSession.created_at.desc()).first()
            if review:
                return {
                    "overall_score": review.overall_score,
                    "critique": review.critique or "",
                    "suggestions": review.suggestions or [],
                }
            return {}

        stages["3_get_review"], _ = _run_stage("3_get_review", _get_review)

        # Step 4: 根据细纲+评审生成新正文
        def _generate_new_content():
            from storage.models import Project
            project = db.query(Project).filter(Project.id == project_id).first()
            prep = build_chapter_prep_info(db, project_id, chapter_id)
            
            # 正确提取 outline 和 review 数据（从 stage 结果中解包）
            def _unwrap(stage_val):
                """从 stage 结果中提取实际数据"""
                if isinstance(stage_val, dict):
                    if "data" in stage_val:
                        return stage_val["data"]
                return stage_val
            
            outline_data = _unwrap(stages["1_get_outline"])
            review_data = _unwrap(stages["3_get_review"])
            
            logger.info(f"[Revise] outline_data keys: {list(outline_data.keys()) if isinstance(outline_data, dict) else type(outline_data)}")
            logger.info(f"[Revise] review_data keys: {list(review_data.keys()) if isinstance(review_data, dict) else type(review_data)}")

            # 使用 writing 角色生成正文
            writing_ctx = {
                "writing_style": project.writing_style or "平实",
                "ai_removal_instruction": build_ai_removal_instruction(project.ai味去除程度) if project.ai味去除程度 else "",
                "themes": prep["themes"],
                "characters": "\n".join(prep["characters"]) or "（无）",
                "character_arcs": "（参见上文 character 段）",
                "world": prep["project_outline_text"] or "（无项目大纲）",
                "foreshadowings": prep["active_foreshadowings"],
                "chapters": prep["prev_chapters_summary"],
                "target_word_count": prep["project_meta"]["target_word_count"],
                "word_count_range": f"{prep['project_meta']['min_words']}~{prep['project_meta']['max_words']} 字",
            }

            system = ROLES["writing"].build_system(writing_ctx)

            # 拼接用户消息：细纲 + 评审建议 + 上章结尾
            critique = review_data.get("critique", "") if isinstance(review_data, dict) else ""
            suggestions = review_data.get("suggestions", []) if isinstance(review_data, dict) else []
            suggestion_text = "\n".join([f"- {s}" for s in suggestions]) if suggestions else "（无）"
            
            # 序列化细纲数据
            outline_text = json.dumps(outline_data, ensure_ascii=False, indent=2) if isinstance(outline_data, dict) else str(outline_data) if outline_data else "（无细纲）"

            user_msg = (
                f"【本章细纲（严格遵循）】\n{outline_text}\n\n"
                f"【评审意见】\n{critique or '（无评审意见）'}\n\n"
                f"【修改建议】\n{suggestion_text}\n\n"
                f"【上章结尾（衔接用）】\n{prep.get('prev_chapter_ending', '')}\n\n"
                f"【登场人物】\n" + "\n".join(prep.get("characters", [])[:5]) + "\n\n"
                f"请根据以上信息重新生成本章正文。"
            )

            logger.info(f"[Revise] user_msg preview: {user_msg[:200]}...")

            llm = LLMFactory.create(provider=provider, db=db)
            raw = llm.generate(
                prompt=user_msg,
                system_prompt=system,
                max_tokens=ROLES["writing"].max_tokens,
                temperature=ROLES["writing"].temperature,
                task_type="chapter_pipeline_revise_content",
            )
            return raw

        stages["4_generate"], _ = _run_stage("4_generate", _generate_new_content)

        # Step 5: 字数调整
        def _adjust():
            prep = build_chapter_prep_info(db, project_id, chapter_id)
            meta = prep["project_meta"]
            gen_result = stages["4_generate"]
            if isinstance(gen_result, dict):
                content_text = gen_result.get("data", "")
            else:
                content_text = gen_result
            if not isinstance(content_text, str):
                content_text = str(content_text)
            # 获取outline数据（从stage结果中提取）
            outline_result = stages["1_get_outline"]
            if isinstance(outline_result, dict):
                outline_data = outline_result.get("data", outline_result)
            else:
                outline_data = outline_result
            return adjust_word_count(
                content_text,
                meta["target_word_count"],
                meta["min_words"],
                meta["max_words"],
                outline_data,
                provider,
            )

        stages["5_adjust"], _ = _run_stage("5_adjust", _adjust)

        # Step 6: 章节评审
        def _review():
            adj_result = stages["5_adjust"]
            if isinstance(adj_result, dict):
                final_content = adj_result.get("data", adj_result)
                if isinstance(final_content, dict):
                    final_content = final_content.get("adjusted_content", str(final_content))
            else:
                final_content = adj_result
            if not isinstance(final_content, str):
                final_content = str(final_content)
            return review_chapter_text(
                db, project_id, chapter_id, final_content, provider,
            )

        stages["6_review"], _ = _run_stage("6_review", _review)

        # Step 7: 保存新正文
        def _save():
            # 从多个可能的位置获取最终内容
            final_content = None
            
            # 尝试从 5_adjust 结果获取
            adj_result = stages.get("5_adjust")
            if isinstance(adj_result, dict):
                data = adj_result.get("data", adj_result)
                if isinstance(data, dict):
                    final_content = data.get("adjusted_content")
                elif isinstance(data, str):
                    final_content = data
            
            # 如果没有，从 4_generate 获取
            if not final_content:
                gen_result = stages.get("4_generate")
                if isinstance(gen_result, dict):
                    data = gen_result.get("data", gen_result)
                    if isinstance(data, str):
                        final_content = data
                elif isinstance(gen_result, str):
                    final_content = gen_result
            
            if not final_content:
                logger.error("[Revise] No content found in stages, using original")
                final_content = chapter.content or ""
            
            if not isinstance(final_content, str):
                final_content = str(final_content)
            
            chapter.content = final_content
            chapter.word_count = _count_chinese_chars(final_content)
            db.commit()
            return {"word_count": chapter.word_count}

        stages["7_save"], _ = _run_stage("7_save", _save)

        # Step 8: 后处理
        def _post_process():
            return run_post_chapter_processing(db, project_id, chapter_id, provider)

        stages["8_post"], _ = _run_stage("8_post", _post_process)

        # ─── 保存评审报告到数据库（修订后重新评审） ───
        try:
            from storage.models import ReviewSession
            from llm.scoring import calculate_overall_score
            review_data_raw = stages.get("6_review")
            review_data = None
            if isinstance(review_data_raw, dict):
                review_data = review_data_raw.get("data", review_data_raw)
            if isinstance(review_data, dict):
                scores = review_data.get("scores", {})
                overall = calculate_overall_score(scores)  # 加权综合分 0-100
                session = ReviewSession(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    session_type="chapter",
                    content_reviewed=(chapter.content or "")[:2000],
                    score_consistency=scores.get("consistency", 0),
                    score_pacing=scores.get("pacing", 0),
                    score_style=scores.get("style", 0),
                    score_ai_removal=scores.get("ai_removal", 0),
                    score_word_count=scores.get("word_count", 0),
                    score_foreshadowing=scores.get("foreshadowing", 0),
                    score_character_arc=scores.get("character_arc", 0),
                    score_thematic=scores.get("thematic", 0),
                    overall_score=overall,
                    critique=review_data.get("critique", ""),
                    suggestions=review_data.get("suggestions", []),
                )
                db.add(session)
                db.commit()
                logger.info(f"[Revise] saved review for chapter {chapter_id}, weighted score={overall}/100")
        except Exception as e:
            logger.warning(f"[Revise] failed to save review: {e}")

        total_ms = (time.time() - start_time) * 1000
        return {
            "status": "completed",
            "stages": {k: {**v, "duration_ms": v.get("duration_ms", 0)} for k, v in stages.items()},
            "chapter_content": chapter.content,
            "final_word_count": chapter.word_count,
            "total_duration_ms": total_ms,
        }

    except Exception as e:
        logger.error(f"[Revise] failed: {e}")
        return {
            "status": "failed",
            "stages": stages,
            "error": str(e),
            "total_duration_ms": (time.time() - start_time) * 1000,
        }


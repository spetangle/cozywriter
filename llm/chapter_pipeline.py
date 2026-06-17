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
    """宽松 JSON 解析（容忍 markdown / 前缀后缀 / 字符串内换行 / 缺逗号等常见问题）

    7 次尝试（按顺序）：
    1. 直接解析
    2. 修复字符串内裸 \\n/\\r/\\t → 转义符
    3. 移除尾部多余逗号（[1,2,3,] → [1,2,3]）
    4. 补缺失逗号（值-值/值-键 之间漏写 ,）
    5. 移除 // 单行注释和 /* */ 块注释
    6. 正则提取最大 {…} 块
    7. 全部失败 → 抛异常（调用方应有兜底）
    """
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

    # ── 1. 直接解析 ──
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ── 2. 修复字符串内裸换行/tabs ──
    text_unescaped = _fix_unescaped_string_chars(text)
    try:
        return json.loads(text_unescaped)
    except json.JSONDecodeError:
        pass

    # ── 3. 移除尾部多余逗号 ──
    text_no_trail = _remove_trailing_commas(text_unescaped)
    try:
        return json.loads(text_no_trail)
    except json.JSONDecodeError:
        pass

    # ── 4. 补缺失逗号（值与值/值与键之间漏 ,）──
    text_commas = _insert_missing_commas(text_no_trail)
    try:
        return json.loads(text_commas)
    except json.JSONDecodeError:
        pass

    # ── 5. 移除 // / /* */ 注释 ──
    text_no_comments = _remove_json_comments(text_commas)
    try:
        return json.loads(text_no_comments)
    except json.JSONDecodeError:
        pass

    # ── 6. 正则提取最大 {…} 块 ──
    try:
        import re as _re
        json_pattern = _re.compile(r'\{[^{}]*\}', _re.DOTALL)
        matches = json_pattern.findall(text_no_comments)
        if matches:
            best = max(matches, key=len)
            return json.loads(best)
    except Exception:
        pass

    # ── 7. 全部失败 → 抛异常 ──
    raise json.JSONDecodeError(
        f"JSON parse failed after 7 attempts (text len={len(text)})",
        text[:200],
        0,
    )


def _fix_unescaped_string_chars(text: str) -> str:
    """将字符串字面量内的裸 \\n/\\r/\\t 替换为 \\n/\\r/\\t 转义符。

    状态机扫描，跟踪是否在 JSON 字符串内（正确处理 \\\" 转义）。
    """
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
    return ''.join(result)


def _remove_trailing_commas(text: str) -> str:
    """移除对象/数组末尾的多余逗号（如 [1,2,3,] → [1,2,3]）"""
    # 状态机：跟踪当前是否在 string 内，只在 string 外替换
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if in_string:
            result.append(ch)
            i += 1
            continue
        # Not in string
        if ch == ',':
            # 看看跳过空白后是不是 } 或 ]
            j = i + 1
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1
            if j < len(text) and text[j] in '}]':
                # 这是个尾部逗号，跳过
                i += 1
                continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _insert_missing_commas(text: str) -> str:
    """在相邻值/值-键之间补缺失的逗号。

    处理以下常见 LLM 错误：
    - "value" "key"      → "value", "key"
    - "value"\n"key"     → "value",\n"key"
    - } {                → }, {
    - ] [                → ], [
    - } "key"            → }, "key"
    - ] "key"            → ], "key"
    - "value" {          → "value", {
    - "value" [          → "value", [
    - 1 "key"            → 1, "key"  (数字 → 字符串)
    - 1.5 {              → 1.5, {    (数字 → 对象)
    - true "key"         → true, "key"
    - null [             → null, [
    """
    result = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            # 出字符串后：检查下一个非空白字符是否是 value-starter
            if not in_string:
                j = i + 1
                while j < n and text[j] in ' \t\n\r':
                    j += 1
                if j < n and text[j] in '"[{':
                    result.append(',')
            i += 1
            continue
        if in_string:
            result.append(ch)
            i += 1
            continue
        # Not in string
        result.append(ch)
        # 遇到 } 或 ]，检查下一个非空白字符是否是 value-starter
        if ch in '}]':
            j = i + 1
            while j < n and text[j] in ' \t\n\r':
                j += 1
            if j < n and text[j] in '"[{':
                result.append(',')
        # 数字、true、false、null 结尾后跟 value-starter
        # 数字：最后一个字符是数字
        if ch.isdigit() or ch in '.eE':
            # 找当前数字 token 结束位置（向后扫描到非数字/非.非e字符）
            j = i + 1
            # 简化处理：如果下一个非空白是 value-starter 且当前 char 是数字结尾
            while j < n and text[j] in ' \t\n\r':
                j += 1
            if j < n and text[j] in '"[{':
                # 确认前面确实是数字 token（连续数字或数字+e/E+数字等）
                # 简单方法：检查当前字符前是否是数字的一部分
                # 这里只在数字后面跟 " 时加逗号，避免误伤像 1e10 这样的科学计数法
                result.append(',')
        i += 1
    return ''.join(result)


def _remove_json_comments(text: str) -> str:
    """移除 JSON 内的 // 单行注释和 /* */ 块注释（JSON 不允许，但 LLM 偶尔会加）"""
    # 状态机跟踪 string 状态，只在 string 外删除注释
    result = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if in_string:
            result.append(ch)
            i += 1
            continue
        # Not in string
        if ch == '/' and i + 1 < n:
            if text[i + 1] == '/':
                # 单行注释，跳到行尾
                while i < n and text[i] != '\n':
                    i += 1
                continue
            if text[i + 1] == '*':
                # 块注释，跳到 */
                i += 2
                while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                    i += 1
                i += 2  # 跳过 */
                continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _count_chinese_chars(text: str) -> int:
    """中文字符数（忽略标点空白）"""
    return sum(1 for c in text if "一" <= c <= "鿿")


def _normalize_character_name(name: str) -> str:
    """规范化角色名用于 dedup 比对。

    规则：
    - 去首尾空白
    - 去除所有半角 / 全角括号及其内容（"玄机子（林玄）" → "玄机子"）
    - 全角空格 → 半角空格
    - 统一小写
    - 去除常见称谓前缀（"老" "小" 不去，避免误合并）
    """
    if not name:
        return ""
    n = name.strip()
    # 去除全角 / 半角括号及其内容
    n = re.sub(r"[（(][^）)]*[）)]", "", n)
    n = n.replace("　", " ").strip()
    return n.lower()


def _find_existing_character(db, project_id: int, name: str) -> "Character | None":
    """在同项目下查同名角色（已规范化处理）。

    匹配规则（按优先级）：
    1. 规范化后完全相等（"玄机子" == "玄机子（林玄）"）
    2. 规范化后是已有名字的子串 / 已有名字是它的子串（短名匹配）
    3. 规范化后相等（去 "（xxx）" 后）
    """
    from storage.models import Character
    target = _normalize_character_name(name)
    if not target:
        return None
    candidates = db.query(Character).filter(Character.project_id == project_id).all()
    # 1) 完全匹配
    for c in candidates:
        if _normalize_character_name(c.name) == target:
            return c
    # 2) 子串匹配（短名命中长名；如 "秦夜" 命中 "秦夜-前传"）
    for c in candidates:
        cn = _normalize_character_name(c.name)
        if cn and (target in cn or cn in target):
            return c
    return None


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
            "project_outline_text": ...,
            "chapter_outline": ...,
            "prev_chapters_summary": "...",  # 前 3 章摘要（每章 2000 字）
            "prev_chapter_ending": "...",
            "next_chapter_opening": "...",
            "characters": [...],
            "active_foreshadowings": "...",
            "consistency_issues": "...",
            "themes": "...",
            # === 新增：去重相关 ===
            "previous_event_signatures": [...],  # 全部前章的 event_signature
            "previous_event_signatures_text": "...",  # 格式化文本（给 prompt 用）
            "event_dedup_matches": [...],  # RAG 检索到的相似过去事件
            "event_dedup_text": "...",  # 格式化文本（给 prompt 用）
            "max_dedup_similarity": 0.0,  # 最高相似度（评审 role 用）
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

    # 前 3 章摘要（从 500 字扩到 2000 字，覆盖关键中段剧情）
    prev_chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.order < chapter.order)
        .order_by(Chapter.order.desc())
        .limit(3)
        .all()
    )
    prev_chapters_summary = "\n\n".join(
        [f"【第{c.order + 1}章 {c.title}】\n{(c.content or c.synopsis or '')[:2000]}"
         for c in reversed(prev_chapters)]
    ) or "（这是第一章）"

    # 上一章结尾
    prev_chapter_ending = ""
    if prev_chapters:
        latest_prev = prev_chapters[0]
        prev_chapter_ending = (latest_prev.content or "")[-800:]

    # 下一章开头（中间章节衔接用，避免重新生成时与后文脱节）
    next_chapter = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.order == chapter.order + 1)
        .first()
    )
    next_chapter_opening = ""
    if next_chapter and (next_chapter.content or "").strip():
        next_chapter_opening = (next_chapter.content or "")[:600]

    # 登场人物：本章细纲的 character_ids + 当前活跃角色
    character_ids = list(chapter_outline.character_ids or []) if chapter_outline else []
    if not character_ids:
        # 兜底：取项目前 5 个角色
        chars = db.query(Character).filter(Character.project_id == project_id).limit(5).all()
    else:
        chars = db.query(Character).filter(Character.id.in_(character_ids)).all()

    # ════════════════════════════════════════════════════════════════
    # 兜底：检查是否有「主角」，没有则从 workflow_run._meta.user_input.protagonist
    #       解析后作为虚拟角色加入 chars（不写库，只在本 prep_info 用）
    # ════════════════════════════════════════════════════════════════
    has_protagonist = any((c.role or "") == "主角" for c in chars)
    if not has_protagonist:
        try:
            from storage.models.workflow import WorkflowRun
            run = (
                db.query(WorkflowRun)
                .filter(WorkflowRun.project_id == project_id)
                .order_by(WorkflowRun.created_at.desc())
                .first()
            )
            if run:
                _meta = (run.stage_results or {}).get("_meta", {})
                _ui = _meta.get("user_input", {}) or {}
                _protagonist_text = (_ui.get("protagonist") or "").strip()
                if _protagonist_text:
                    # 简易解析：从文本里抽 "姓名：X" + 整段作为 description
                    import re as _re
                    _name_m = _re.search(r"姓\s*名\s*[:：]\s*([^\n\r*#-]+)", _protagonist_text)
                    _name = _name_m.group(1).strip() if _name_m else "（用户自定义主角）"
                    # 用一个 _VirtualCharacter 命名空间类，让下面的循环把它当 Character 处理
                    class _VC:
                        pass
                    _vc = _VC()
                    _vc.id = -1
                    _vc.name = _name
                    _vc.role = "主角（来自用户输入）"
                    _vc.description = _protagonist_text[:1000]
                    _vc.profile = {}
                    chars = [_vc] + list(chars)
                    logger.info(
                        f"[build_chapter_prep_info] chars 表缺主角，已从 user_input 兜底注入「{_name}」"
                    )
        except Exception as e:
            logger.warning(f"[build_chapter_prep_info] 主角兜底注入失败: {e}")

    arc_map = {}
    for arc in db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all():
        arc_map[arc.character_id] = arc

    character_blocks = []
    for c in chars:
        arc = arc_map.get(c.id) if getattr(c, "id", -1) > 0 else None
        block = f"【{c.name}】({c.role})\n{c.description or ''}"
        if getattr(c, "profile", None):
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
    # 取出结构化分卷/剧情线/四幕结构,作为章节生成的"宏观上下文"
    # （注意：key_content 才是单章的主要依据;这些是辅助参考,提供故事走向）
    proj_volumes = list(proj_outline.volumes) if proj_outline and proj_outline.volumes else []
    proj_plot_lines = list(proj_outline.plot_lines) if proj_outline and proj_outline.plot_lines else []
    proj_structure = dict(proj_outline.structure) if proj_outline and proj_outline.structure else {}
    proj_pacing_notes = (proj_outline.pacing_notes or "") if proj_outline else ""
    # 本章所属卷号（按 from_chapter/to_chapter 匹配）
    chapter_volume = None
    if proj_volumes and chapter is not None:
        for v in proj_volumes:
            try:
                if int(v.get("from_chapter", 0)) <= (chapter.order + 1) <= int(v.get("to_chapter", 0)):
                    chapter_volume = v
                    break
            except (ValueError, TypeError):
                continue
    # 本章所属剧情线（粗略匹配：从 key_content / plot_advance 文本里搜 plot_lines 关键词）
    chapter_plot_lines = []
    if proj_plot_lines and chapter_outline:
        co_text = ((chapter_outline.key_content or "") + " " + (chapter_outline.plot_advance or "")).strip()
        if co_text:
            for pl in proj_plot_lines:
                pl_title = (pl.get("title") or "").strip()
                if not pl_title:
                    continue
                # 简单匹配：plot_line.title 任意 2 字 出现在本章细纲中
                if any(pl_title[i:i+2] in co_text for i in range(len(pl_title) - 1) if pl_title[i:i+2]):
                    chapter_plot_lines.append(pl)
        # 兜底：至少附上第 1 条剧情线（总览用）
        if not chapter_plot_lines and proj_plot_lines:
            chapter_plot_lines = proj_plot_lines[:1]

    # 核心主旨
    themes = db.query(Theme).filter(Theme.project_id == project_id).all()
    themes_text = "\n".join(
        [f"- [{t.theme_type}] {t.title}: {t.description}" for t in themes]
    ) or "（暂无主旨）"

    # ════════════════════════════════════════════════════════════════
    # 新增：去重相关 - 聚合全部前章事件签名
    # ════════════════════════════════════════════════════════════════
    all_prev_chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.order < chapter.order)
        .order_by(Chapter.order)
        .all()
    )
    # 关联 ChapterOutline 取 key_content
    prev_outlines = {
        co.chapter_id: co
        for co in db.query(ChapterOutline).filter(
            ChapterOutline.chapter_id.in_([c.id for c in all_prev_chapters] or [0])
        ).all()
    }
    previous_event_signatures = []
    for c in all_prev_chapters:
        co = prev_outlines.get(c.id)
        # 优先级: event_signature > chapter_outline.key_content > synopsis
        sig = (c.event_signature or "").strip()
        if not sig and co:
            sig = (co.key_content or "").strip()
        if not sig:
            sig = (c.synopsis or "").strip()
        if sig:
            previous_event_signatures.append({
                "chapter": c.order + 1,
                "chapter_id": c.id,
                "title": c.title,
                "signature": sig[:200],
            })
    previous_event_signatures_text = "\n".join(
        [f"- 第{e['chapter']}章《{e['title']}》: {e['signature']}" for e in previous_event_signatures]
    ) or "（暂无已发生事件，这是首章）"

    # RAG 检索相似过去事件（基于本章 tentative key_content）
    event_dedup_matches = []
    max_dedup_similarity = 0.0
    try:
        from rag.retrieval import RetrievalService
        # 用 chapter_outline.key_content 或 plot_advance 作为查询
        query_text = ""
        if chapter_outline:
            query_text = (chapter_outline.key_content or "") + " " + (chapter_outline.plot_advance or "")
        query_text = query_text.strip() or chapter.title or ""
        if query_text:
            retrieval = RetrievalService()
            dedup_ctx = retrieval.build_event_dedup_context(
                project_id=project_id,
                query=query_text,
                exclude_chapter_id=chapter_id,
                db=db,
                top_k=3,
                similarity_threshold=0.45,  # 阈值偏宽，让 LLM 看到更多候选
            )
            event_dedup_matches = dedup_ctx.get("matches", [])
            max_dedup_similarity = dedup_ctx.get("max_similarity", 0.0)
    except Exception as e:
        logger.warning(f"[build_chapter_prep_info] RAG dedup 检索失败: {e}")

    event_dedup_text = "\n".join(
        [f"- 第{m['chapter']}章《{m['title']}》(相似度 {m['similarity']:.2f}): {m['signature'][:150]}"
         for m in event_dedup_matches]
    ) or "（RAG 未检索到相似过去事件）"

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
        # === 新增：结构化宏观上下文(分卷/剧情线/结构)给 LLM 做"辅助参考" ===
        "project_volumes": proj_volumes,
        "project_plot_lines": proj_plot_lines,
        "project_structure": proj_structure,
        "project_pacing_notes": proj_pacing_notes,
        "chapter_volume": chapter_volume,           # 本章所属卷(主:位置)
        "chapter_plot_lines": chapter_plot_lines, # 本章相关剧情线(辅:背景)
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
        "next_chapter_opening": next_chapter_opening,  # 下一章开头（中间章节衔接用）
        "characters": character_blocks,
        "active_foreshadowings": foreshadowings_text,
        "consistency_issues": issues_text,
        "themes": themes_text,
        # === 新增字段 ===
        "previous_event_signatures": previous_event_signatures,
        "previous_event_signatures_text": previous_event_signatures_text,
        "event_dedup_matches": event_dedup_matches,
        "event_dedup_text": event_dedup_text,
        "max_dedup_similarity": max_dedup_similarity,
    }


# ═══════════════════════════════════════════════════════════════
# Step 2: 章节细纲生成
# ═══════════════════════════════════════════════════════════════

def generate_chapter_outline(db, project_id: int, chapter_id: int, provider: str | None = None, guide: str = "") -> dict:
    """LLM 生成章节细纲（不存库，返回给上层走评审）

    失败兜底：JSON 解析失败时返回默认空细纲，pipeline 继续跑。
    """
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
        "previous_events": prep.get("previous_event_signatures_text", "（暂无，这是首章）"),
        "target_word_count": prep["project_meta"]["target_word_count"],
        "guide": guide,
    }

    raw = _call_llm("chapter_outline_gen", outline_ctx, "", provider)
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        # 兜底：返回默认空细纲，pipeline 不中断
        logger.warning(
            f"[generate_chapter_outline] JSON 解析失败，使用默认空细纲: {e}\n"
            f"原始返回前 300 字: {raw[:300]!r}"
        )
        return {
            "chapter_position": "",
            "pacing": "平稳",
            "key_content": "",
            "plot_advance": "",
            "foreshadow_notes": "",
            "conflicts": [],
            "highlights": [],
            "target_word_count": outline_ctx.get("target_word_count", 3000),
            "min_word_count": 0,
            "max_word_count": 0,
            "qi_cheng_zhuan_he": {},
            "scenes": [],
            "pacing_hooks": [],
            "reversals": [],
            "foreshadow_actions": [],
            "character_developments": [],
            "word_count_check": "（细纲生成失败，跳过）",
        }


# ═══════════════════════════════════════════════════════════════
# Step 3: 细纲评审
# ═══════════════════════════════════════════════════════════════

def review_chapter_outline(outline: dict, prep_info: dict, provider: str | None = None) -> dict:
    """评审细纲，仅过滤 high severity

    失败兜底：JSON 解析失败时返回 verdict=pass（默认通过），pipeline 继续。
    """
    # 准备 RAG 检索的过去事件（给评审 role 看）
    dedup_matches = prep_info.get("event_dedup_matches", []) if isinstance(prep_info, dict) else []
    dedup_text_for_reviewer = "\n".join(
        [f"- 第{m['chapter']}章《{m['title']}》(相似度 {m['similarity']:.2f}): {m['signature'][:150]}"
         for m in dedup_matches]
    ) or "（RAG 未命中）"

    previous_events = prep_info.get("previous_event_signatures_text", "（暂无）") if isinstance(prep_info, dict) else "（暂无）"

    ctx = {
        "outline": json.dumps(outline, ensure_ascii=False, indent=2),
        "previous_events": previous_events,
    }
    raw = _call_llm("outline_reviewer", ctx, "", provider)
    try:
        data = _parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            f"[review_chapter_outline] JSON 解析失败，默认通过: {e}\n"
            f"原始返回前 300 字: {raw[:300]!r}"
        )
        return {
            "issues": [],
            "duplicate_risk": [],
            "verdict": "pass",
            "summary": "（评审解析失败，已默认通过）",
        }

    # ════════════════════════════════════════════════════════════════
    # 兜底去重：RAG 已命中的高相似事件直接进 issues + 强制 needs_revision
    # 即便 LLM 评审没看出来，我们也要挡住
    # ════════════════════════════════════════════════════════════════
    max_sim = prep_info.get("max_dedup_similarity", 0.0) if isinstance(prep_info, dict) else 0.0
    if dedup_matches:
        # 取相似度最高的 1 条作为"硬去重依据"
        top_match = max(dedup_matches, key=lambda x: x.get("similarity", 0))
        if top_match.get("similarity", 0) >= 0.65:
            # 加进 issues（如果 LLM 没加的话）
            has_dup_issue = any(
                (iss.get("type") == "duplicate") for iss in data.get("issues", [])
            )
            if not has_dup_issue:
                data.setdefault("issues", []).append({
                    "severity": "high",
                    "type": "duplicate",
                    "description": (
                        f"RAG 命中第{top_match['chapter']}章《{top_match['title']}》(相似度 {top_match['similarity']:.2f})，"
                        f"事件签名: {top_match['signature'][:100]}"
                    ),
                    "suggestion": "必须换角度展开本章，避免与上章同一关键事件重复",
                })
            data.setdefault("duplicate_risk", []).append({
                "past_chapter": top_match["chapter"],
                "similarity": top_match["similarity"],
                "reason": f"RAG 命中事件签名高度相似: {top_match['signature'][:100]}",
            })
            # 强制 needs_revision
            if data.get("verdict") == "pass":
                logger.warning(
                    f"[review_chapter_outline] RAG 命中相似度 {top_match['similarity']:.2f} 强制 needs_revision"
                )
                data["verdict"] = "needs_revision"
                data["summary"] = (
                    f"（RAG 自动拦截）{data.get('summary', '')} "
                    f"与第{top_match['chapter']}章《{top_match['title']}》事件签名相似度过高"
                ).strip()

    return data


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
        f"请按细纲生成正文，**不要偏离细纲**。\n\n【重要约束】：请务必在生成完毕后检查字数，确保最终输出严格在{prep['project_meta']['min_words']}~{prep['project_meta']['max_words']}字之间，不要超出或过少。"
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
    """根据目标字数调整正文（过多缩写 / 过少扩写）

    流程日志：
    - 调整前：当前字数 / 目标字数 / 计划动作（缩写 or 扩写）/ 偏差
    - 调整后：调整前字数 → 调整后字数（净增/减 + 是否落进 min~max 区间）
    """
    actual = _count_chinese_chars(content)
    if min_w <= actual <= max_w:
        logger.info(
            f"[WordAdjust] 调整前={actual}字, 目标={target}字, 范围={min_w}~{max_w}字, "
            f"动作=无需调整（在区间内）, 偏差={actual - target:+d}字"
        )
        return content

    # ── 决定动作方向 ──
    if actual > max_w:
        action = "缩写"
        delta = actual - max_w
    else:
        action = "扩写"
        delta = min_w - actual

    logger.info(
        f"[WordAdjust] 调整前={actual}字, 目标={target}字, 范围={min_w}~{max_w}字, "
        f"动作={action}, 预计需调整={delta}字 (偏差={actual - target:+d}字)"
    )

    ctx = {
        "target_word_count": target,
        "current_word_count": actual,
        "min_words": min_w,            # 用于 LLM 重要约束 prompt
        "max_words": max_w,            # 用于 LLM 重要约束 prompt
        "outline": json.dumps(outline, ensure_ascii=False, indent=2) if isinstance(outline, dict) else str(outline),
        "content": content[:6000],  # 截断避免超长
    }
    try:
        t0 = time.time()
        if actual > max_w:
            raw = _call_llm("compressor", ctx, "", provider)
            data = _parse_json(raw)
            new_content = data.get("compressed_text", content)
            claimed_count = data.get("final_word_count")
        else:
            raw = _call_llm("expander", ctx, "", provider)
            data = _parse_json(raw)
            new_content = data.get("expanded_text", content)
            claimed_count = data.get("final_word_count")
        duration_ms = (time.time() - t0) * 1000
        new_actual = _count_chinese_chars(new_content)
        in_range = min_w <= new_actual <= max_w
        # 验证 LLM 自报字数与实际字数差距过大时报警
        claimed_str = ""
        if claimed_count is not None:
            try:
                claimed_int = int(claimed_count)
                diff = abs(claimed_int - new_actual)
                if diff > 100:  # 偏差 > 100 字说明 LLM 自报不准
                    claimed_str = f", LLM自报={claimed_int}字 (差{diff}字 ⚠️ 不准)"
                else:
                    claimed_str = f", LLM自报={claimed_int}字 ✓"
            except (ValueError, TypeError):
                pass
        logger.info(
            f"[WordAdjust] 调整完成: 调整前={actual}字 → 调整后={new_actual}字 "
            f"(净{'减' if new_actual < actual else '增'}{abs(actual - new_actual)}字, "
            f"用时={duration_ms:.0f}ms{claimed_str}), "
            f"{'✅ 已落进目标区间' if in_range else f'⚠️ 仍未落进区间 {min_w}~{max_w}'}"
        )
        return new_content
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            f"[WordAdjust] 调整失败: JSON parse error={e}, "
            f"调整前={actual}字, 保持原内容"
        )
        return content


# ═══════════════════════════════════════════════════════════════
# Step 6: 正文评审
# ═══════════════════════════════════════════════════════════════

def review_chapter_text(
    db, project_id: int, chapter_id: int, content: str, provider: str | None = None,
) -> dict:
    """8 维度评审

    失败兜底：JSON 解析失败时返回 5 分中位评分（让 pipeline 继续，
    而不是整个失败）。critique 标注解析失败原因。
    """
    from storage.models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    ctx = {
        "title": project.title if project else "",
        "content": content[:8000],
    }
    raw = _call_llm("review", ctx, "", provider)
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            f"[review_chapter_text] JSON 解析失败，使用 5 分兜底: {e}\n"
            f"原始返回前 300 字: {raw[:300]!r}"
        )
        return {
            "scores": {
                "consistency": 5, "pacing": 5, "style": 5, "ai_removal": 5,
                "word_count": 5, "foreshadowing": 5, "character_arc": 5, "thematic": 5,
            },
            "critique": "（评审解析失败，已使用默认 5 分中位值）",
            "suggestions": [],
        }


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
    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        # 兜底：解析失败默认不修订（保守）
        logger.warning(
            f"[decide_revision] JSON 解析失败，默认不修订: {e}\n"
            f"原始返回前 300 字: {raw[:300]!r}"
        )
        return {
            "decision": "pass",
            "focus_areas": [],
            "reasoning": "（决策解析失败，默认不修订）",
        }


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

    # 创建新角色（先去重，LLM 经常把同一个人用不同名字重复创建）
    for new_c in post_data.get("new_characters", []):
        new_name = new_c.get("name", "未命名").strip()
        if not new_name or new_name == "未命名":
            continue
        existing = _find_existing_character(db, project_id, new_name)
        if existing:
            logger.info(
                f"[PostChapter] 跳过新角色「{new_name}」：已存在（id={existing.id}, 当前名={existing.name}），合并而非新建"
            )
            result["new_characters"].append({
                "name": existing.name, "role": existing.role,
                "merged": True, "existing_id": existing.id,
            })
            continue
        nc = Character(
            project_id=project_id,
            name=new_name,
            role=new_c.get("role", "配角"),
            profile={k: v for k, v in new_c.items() if k in ["identity", "personality"]},
            description=new_c.get("first_appearance_note", ""),
        )
        db.add(nc)
        db.flush()  # 拿到 id，下面 dedup 才查得到刚插入的
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

    # ════════════════════════════════════════════════════════════════
    # 9.5 事件签名抽取 + RAG 索引（用于下一章去重）
    # ════════════════════════════════════════════════════════════════
    try:
        sig_ctx = {
            "title": chapter.title or "",
            "chapter_num": chapter.order + 1,
            "content": (content or chapter.content or "")[:6000],
        }
        sig_raw = _call_llm("event_signature_extractor", sig_ctx, "", provider)
        sig_data = _parse_json(sig_raw)
        sig = (sig_data.get("signature") or "").strip()[:500]
        if sig:
            chapter.event_signature = sig
            db.commit()
            result["event_signature"] = sig
            result["event_signature_chars"] = sig_data.get("characters_involved", [])

            # 索引到 ChromaDB chapter_events 集合
            try:
                from rag.knowledge_base import KnowledgeBase
                kb = KnowledgeBase()
                kb.add_chapter_event(chapter)
                result["rag_indexed"] = True
            except Exception as rag_err:
                logger.warning(f"[PostChapter] RAG event index failed: {rag_err}")
                result["rag_indexed"] = False
        else:
            logger.warning(f"[PostChapter] event_signature 抽取为空 (chapter {chapter_id})")
    except Exception as sig_err:
        logger.warning(f"[PostChapter] event_signature 抽取失败: {sig_err}")

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
    """把 prep_info dict 格式化成 LLM 可读的文本块

    结构层次：
      - 主要依据：key_content（本章必写的 1 句话核心事件）
      - 辅助参考：分卷位置、剧情线、四幕结构（故事走向）
      - 硬约束：已发生事件 + RAG 相似事件（防重复）
      - 衔接：上章结尾 / 下章开头 / 前 3 章摘要
    """
    # 防御：chapter_outline 可能是 None（项目未建 ChapterOutline）→ 用 {} 兜底
    co = prep.get("chapter_outline") if isinstance(prep.get("chapter_outline"), dict) else {}

    parts = [
        f"【项目元信息】\n标题: {prep['project_meta']['title']}\n文风: {prep['project_meta']['writing_style']}\n去AI味: {prep['project_meta']['ai_removal']}",
        f"【项目大纲】\n{prep['project_outline_text'] or '（无）'}",
        f"【核心主旨】\n{prep['themes']}",
    ]

    # === 主要依据：分卷结构(本章在哪一卷) + 剧情线(本章参与哪些线) ===
    chapter_volume = prep.get("chapter_volume")
    if chapter_volume:
        parts.append(
            f"【🎯 本章所属卷（主参考）】\n"
            f"第{chapter_volume.get('from_chapter', '?')} - {chapter_volume.get('to_chapter', '?')} 章"
            f"《{chapter_volume.get('title', '未命名')}》\n"
            f"本卷核心事件: {chapter_volume.get('core_event', '')}\n"
            f"本卷主线: {chapter_volume.get('summary', '')}"
        )
    chapter_plot_lines = prep.get("chapter_plot_lines") or []
    if chapter_plot_lines:
        pl_text = "\n".join([
            f"- 《{pl.get('title', '?')}》(第{pl.get('from_chapter', '?')}-{pl.get('to_chapter', '?')}章): {pl.get('description', '')}"
            for pl in chapter_plot_lines
        ])
        parts.append(
            f"【🎯 本章相关剧情线（主参考）】\n{pl_text}"
        )

    # === 主要依据：单章细纲（key_content 是硬约束，LLM 必须围绕这个写） ===
    parts.append(
        f"【📌 本章必写内容（PRIMARY - 围绕此核心事件展开）】\n"
        f"  位置: {co.get('position', '')} · 节奏: {co.get('pacing', '')}\n"
        f"  核心事件: {co.get('key_content', '')}\n"
        f"  剧情推进: {co.get('plot_advance', '')}\n"
        f"  伏笔动作: {co.get('foreshadow_notes', '')}\n"
        f"  ⚠️ 本章所有内容必须围绕上面的「核心事件」展开,不能偏离"
    )

    # === 辅助参考:四幕结构 + 节奏规划(整本书的故事曲线) ===
    project_structure = prep.get("project_structure") or {}
    project_pacing_notes = prep.get("project_pacing_notes") or ""
    aux_lines = []
    if project_structure.get("acts"):
        aux_lines.append("四幕结构:")
        for act in project_structure["acts"]:
            aux_lines.append(
                f"  - {act.get('name', '?')}: 第{act.get('from_chapter', '?')}-{act.get('to_chapter', '?')}章"
            )
    if project_pacing_notes:
        aux_lines.append(f"节奏规划: {project_pacing_notes}")
    if aux_lines:
        parts.append("【📊 宏观结构（AUXILIARY - 辅助参考）】\n" + "\n".join(aux_lines))

    # === 硬约束 - 已发生事件清单（必须紧贴细纲，让 LLM 看到） ===
    parts.append(
        f"【⚠️ 已发生事件清单（硬约束：不得重复以下任一事件）】\n{prep.get('previous_event_signatures_text', '（暂无，这是首章）')}"
    )
    # === 硬约束 - RAG 检索的相似过去事件（语义层去重） ===
    parts.append(
        f"【⚠️ RAG 检索到的相似过去事件（高相似度事件需规避）】\n{prep.get('event_dedup_text', '（RAG 未命中）')}"
    )

    parts.append(f"【前 3 章摘要（供文风/衔接参考）】\n{prep['prev_chapters_summary']}")
    parts.append(f"【上章结尾】\n{prep['prev_chapter_ending'][-500:]}")

    # 中间章节（前后都有正文）追加"下章开头"用于衔接
    if prep.get("next_chapter_opening"):
        parts.append(
            f"【下章开头（用于衔接，必须自然过渡到这里）】\n{prep['next_chapter_opening']}\n"
            f"⚠️ 本章结尾必须能自然衔接下章开头，避免剧情跳跃。"
        )
    parts.extend([
        f"【登场人物】\n" + "\n".join(prep["characters"]),
        f"【活跃伏笔】\n{prep['active_foreshadowings']}",
        f"【未解决的一致性问题】\n{prep['consistency_issues']}",
    ])
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


def reindex_project_rag(project_id: int, db, with_signatures: bool = True) -> dict:
    """全量 reindex 一个项目的所有数据到 ChromaDB。

    用于：
    - 迁移后回填（老项目没 event_signature 时回填索引）
    - 手动触发（修复索引漂移）

    Args:
        project_id: 项目 ID
        db: SQLAlchemy Session
        with_signatures: 若 True，对没有 event_signature 的章节调 LLM 抽取（慢）

    Returns:
        {"characters": N, "world_entries": N, "chapters": N, "chapter_events": N}
    """
    from storage.models import Character, WorldEntry, Chapter, ChapterOutline
    from rag.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    counts = {"characters": 0, "world_entries": 0, "chapters": 0, "chapter_events": 0}

    # 1. 角色
    for c in db.query(Character).filter(Character.project_id == project_id).all():
        try:
            kb.add_character(c)
            counts["characters"] += 1
        except Exception as e:
            logger.warning(f"[reindex] char {c.id} 失败: {e}")

    # 2. 世界观
    for w in db.query(WorldEntry).filter(WorldEntry.project_id == project_id).all():
        try:
            kb.add_world_entry(w)
            counts["world_entries"] += 1
        except Exception as e:
            logger.warning(f"[reindex] world {w.id} 失败: {e}")

    # 3. 章节（chapters 集合：摘要 500 字）
    for ch in db.query(Chapter).filter(Chapter.project_id == project_id).all():
        try:
            kb.add_chapter(ch)
            counts["chapters"] += 1
        except Exception as e:
            logger.warning(f"[reindex] chapter {ch.id} 失败: {e}")

    # 4. 章节事件（chapter_events 集合：用于去重检索）
    #    对没有 event_signature 的章节，若 with_signatures=True 则调 LLM 抽取
    chapters = db.query(Chapter).filter(Chapter.project_id == project_id).all()
    for ch in chapters:
        try:
            if not (ch.event_signature or "").strip() and with_signatures and (ch.content or "").strip():
                # 调 LLM 抽取事件签名
                from llm.factory import LLMFactory
                sig_ctx = {
                    "title": ch.title or "",
                    "chapter_num": ch.order + 1,
                    "content": (ch.content or "")[:6000],
                }
                role = ROLES.get("event_signature_extractor")
                if role:
                    system = role.build_system(sig_ctx)
                    user = role.build_user(sig_ctx)
                    llm = LLMFactory.create(db=db)
                    raw = llm.generate(
                        prompt=user, system_prompt=system,
                        max_tokens=role.max_tokens, temperature=role.temperature,
                        task_type="rag_reindex_event_sig",
                    )
                    try:
                        sig_data = _parse_json(raw)
                        sig = (sig_data.get("signature") or "").strip()[:500]
                        if sig:
                            ch.event_signature = sig
                            db.commit()
                    except Exception as parse_err:
                        logger.warning(f"[reindex] event_sig 解析失败 ch {ch.id}: {parse_err}")
            # 索引
            kb.add_chapter_event(ch)
            counts["chapter_events"] += 1
        except Exception as e:
            logger.warning(f"[reindex] chapter_event {ch.id} 失败: {e}")

    logger.info(f"[reindex_project_rag] project={project_id} counts={counts}")
    return counts


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
                # 章节标题（LLM 生成，与内容有关联，非"第 N 章"这种序号）
                new_title        = outline_data.get("title", "").strip()
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

                # 把 LLM 生成的标题写回 chapter.title（仅当标题有效且非默认占位）
                if new_title and not re.match(r'^第\s*[0-9一二三四五六七八九十百千]+\s*章\s*$', new_title):
                    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
                    if chapter and chapter.title != new_title:
                        old_title = chapter.title
                        chapter.title = new_title
                        logger.info(
                            f"[Pipeline] 章节 {chapter_id} 标题更新：「{old_title}」→「{new_title}」"
                        )

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


"""
剧本场景生成流水线（9 步）

Step 1: 场景准备信息聚合
Step 2: 场景区纲生成
Step 3: 场景区纲评审
Step 4: 剧本正文生成
Step 5: 剧本评审
Step 6: 修订决策
Step 7: 保存正文到 Screenplay.content
Step 8: 分镜稿生成（正文定稿后）
Step 9: 后处理（角色外貌更新、弧光更新、道具更新）
"""
import json
import re
import time
import traceback
from typing import Any, Callable, Optional

from logger import logger
from llm.factory import LLMFactory
from llm.script_roles import get_script_role, SCRIPT_ROLE_NAME_CN
from llm.usage_tracker import generate_llm_call_id


# ═══════════════════════════════════════════════════════════════
# JSON 解析（复用 chapter_pipeline 的宽松解析逻辑）
# ═══════════════════════════════════════════════════════════════

def _parse_json(text: str) -> dict | list | str:
    """解析 LLM 返回的 JSON，兼容代码块、前后说明和常见格式错误。

    剧本各阶段对 JSON 的容错要求比普通 ``json.loads`` 高：模型经常会
    在 JSON 前后加解释、使用尾逗号、在字符串中放未转义换行，或把对象/数组
    包在 Markdown 代码块中。这里先按 JSON decoder 扫描完整的结构（不会把
    字符串里的 ``{`` / ``}`` 误认为结构边界），再逐层修复；最后使用项目已
    声明的 ``json_repair`` 依赖兜底。
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response from LLM")

    original = text
    cleaned = text.strip()

    # 去掉 ```json ... ``` / ``` ... ``` 包装。LLM 也可能只在开头写
    # ```json 而没有结束标记，因此两种情况都处理。
    if cleaned.startswith("```"):
        fence = re.match(r"^```(?:json)?\s*", cleaned, flags=re.IGNORECASE)
        if fence:
            cleaned = cleaned[fence.end():]
        closing = re.search(r"```\s*$", cleaned)
        if closing:
            cleaned = cleaned[:closing.start()].strip()

    # 先尝试修复格式错误（尾逗号、raw 换行、中文逗号等），而不是一上来
    # 就扫描 raw_decode：对于“外层对象尾逗号 + 内层合法对象”的响应，
    # raw_decode 会先解析出内层对象，导致返回不完整的 JSON。
    no_control_chars = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", cleaned)
    no_trailing_commas = re.sub(r",\s*([}\]])", r"\1", no_control_chars)
    repaired_candidates = (
        cleaned,
        no_control_chars,
        no_trailing_commas,
    )
    for candidate in repaired_candidates:
        try:
            parsed = json.loads(candidate, strict=False)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, (dict, list)):
            return parsed

    # raw_decode 能正确处理字符串中的花括号/方括号，也能从解释文字中定位
    # JSON 结构。若存在多个候选，选跨度最大的那个（通常是外层完整结构）。
    decoder = json.JSONDecoder()
    best = None
    best_span = -1
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            parsed, end = decoder.raw_decode(cleaned[index:])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, (dict, list)):
            continue
        span = end
        if span > best_span:
            best, best_span = parsed, span
    if best is not None:
        return best

    # json_repair 能处理单引号、未闭合引号、注释、中文标点等 LLM 常见错误。
    try:
        import json_repair

        repaired = json_repair.repair_json(cleaned, return_objects=True)
        if isinstance(repaired, (dict, list)):
            return repaired
        if isinstance(repaired, str) and repaired.strip():
            try:
                parsed = json.loads(repaired, strict=False)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return parsed
    except ImportError:
        # requirements.txt 已声明该依赖，但保留无依赖时的安全降级。
        pass
    except Exception as exc:
        logger.warning(f"[ScriptPipeline] json_repair failed: {exc}")

    raise json.JSONDecodeError(
        f"JSON parse failed (text len={len(original)})",
        original[:200],
        0,
    )


# ═══════════════════════════════════════════════════════════════
# 分镜密度
# ═══════════════════════════════════════════════════════════════

# 与前端 script_editor.js 的 densityOptions 保持一致
STORYBOARD_DENSITY_PROMPTS = {
    "coarse": "粗略（每场景 1-2 个分镜，只保留最关键画面）",
    "standard": "标准（每场景 3-5 个分镜）",
    "fine": "精细（每场景 5-8 个分镜，覆盖完整镜头语言）",
}


def storyboard_density_prompt(density: str | None) -> str:
    """把前端传来的密度 key 映射为 prompt 文案，未知值回退到 standard"""
    return STORYBOARD_DENSITY_PROMPTS.get(density or "", STORYBOARD_DENSITY_PROMPTS["standard"])


# ═══════════════════════════════════════════════════════════════
# 分镜稿三级容错解析
# ═══════════════════════════════════════════════════════════════

def _parse_storyboard_flexible(text: str) -> list[dict]:
    """分镜稿三级容错解析

    第一级：尝试 json.loads(text)
    第二级：从文本中按分镜标记分段，提取结构化字段
    第三级：生成极简分镜（仅 shot_number + visual_description + dialogue）
    """
    if not text or not text.strip():
        return []

    # ── 第一级：JSON 直接解析 ──
    try:
        result = _parse_json(text)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            # 可能是 {"shots": [...]} 或 {"storyboard": [...]}
            for key in ("shots", "storyboard", "storyboards", "items", "data"):
                if key in result and isinstance(result[key], list):
                    return [item for item in result[key] if isinstance(item, dict)]
            # 单个分镜对象
            return [result]
    except Exception:
        pass

    # ── 第二级：文本分段解析 ──
    # 按分镜标记分段（分镜1、镜头1、Shot 1、数字编号等）
    pattern = r'(?:分镜\s*(\d+)|镜头\s*(\d+)|Shot\s*(\d+)|^#{1,3}\s*(\d+)[\.、]|^(\d+)[\.、]\s*)'
    segments = re.split(pattern, text, flags=re.MULTILINE)

    shots = []
    # segments 格式: [前文, group1, group2, ..., 片段, group1, group2, ..., 片段, ...]
    # 每个匹配有 5 个 group + 1 段文本
    current_segment_text = ""
    segment_shot_numbers = []

    # 简化：用 finditer 找到所有分镜标记位置
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if matches:
        for i, m in enumerate(matches):
            shot_num = None
            for g in m.groups():
                if g is not None:
                    try:
                        shot_num = int(g)
                    except (ValueError, TypeError):
                        pass
                    break
            if shot_num is None:
                shot_num = i + 1

            # 提取该分镜的文本（从当前匹配到下一个匹配）
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment_text = text[start:end].strip()

            shot = _extract_shot_fields(segment_text, shot_num)
            shots.append(shot)

    if shots:
        return shots

    # ── 第三级：极简输出 ──
    # 按段落分割，每段作为一个分镜
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    for i, para in enumerate(paragraphs):
        shots.append({
            "shot_number": i + 1,
            "visual_description": para[:500],
            "dialogue": "",
        })

    return shots


def _normalize_storyboard_data(data: list) -> list[dict]:
    """规范化分镜列表并按镜号去重。

    LLM 偶尔会重复输出同一个 ``shot_number``，或者给部分镜头遗漏编号。
    统一在写库前整理，避免同一场景出现重复行，也避免后续 ``.get`` 因
    非字典项崩溃。重复或非法镜号会被顺延到下一个可用编号。
    """
    normalized: list[dict] = []
    seen_numbers: set[int] = set()
    next_number = 1

    for raw in data or []:
        if not isinstance(raw, dict):
            continue

        shot = dict(raw)
        try:
            number = int(shot.get("shot_number"))
        except (TypeError, ValueError):
            number = 0
        if number <= 0 or number in seen_numbers:
            while next_number in seen_numbers:
                next_number += 1
            number = next_number
        seen_numbers.add(number)
        shot["shot_number"] = number
        normalized.append(shot)
        next_number = max(next_number, number + 1)

    return normalized


def _extract_shot_fields(text: str, shot_number: int) -> dict:
    """从分镜文本片段中提取结构化字段"""
    shot = {
        "shot_number": shot_number,
        "shot_type": "中景",
        "camera_angle": "平视",
        "camera_movement": "固定",
        "duration_estimate": "3-5秒",
        "visual_description": "",
        "dialogue": "",
        "sound_effects": "",
        "notes": "",
    }

    # 尝试提取各字段
    field_patterns = {
        "shot_type": r'(?:景别|镜头类型|shot\s*type)[:：]\s*(.+)',
        "camera_angle": r'(?:角度|镜头角度|camera\s*angle)[:：]\s*(.+)',
        "camera_movement": r'(?:运镜|镜头运动|camera\s*movement)[:：]\s*(.+)',
        "duration_estimate": r'(?:时长|预估时长|duration)[:：]\s*(.+)',
        "visual_description": r'(?:画面|画面描述|视觉|visual|画面内容)[:：]\s*(.+)',
        "dialogue": r'(?:对白|台词|dialogue)[:：]\s*(.+)',
        "sound_effects": r'(?:音效|声音|sound)[:：]\s*(.+)',
        "notes": r'(?:备注|注意|notes)[:：]\s*(.+)',
    }

    for field, pattern in field_patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            shot[field] = m.group(1).strip()

    # 如果没有提取到画面描述，使用整段文本
    if not shot["visual_description"]:
        shot["visual_description"] = text[:500]

    return shot


# ═══════════════════════════════════════════════════════════════
# LLM 调用 helpers
# ═══════════════════════════════════════════════════════════════

def _call_llm(role_name: str, ctx: dict, user_msg: str,
              provider: str | None = None, db=None,
              project_id: str | None = None, task_id: str | None = None,
              use_json: bool | None = None) -> str:
    """通用 LLM 调用 helper - 剧本专用"""
    role = get_script_role(role_name)
    system = role.build_system(ctx)
    user = role.build_user({**ctx, "context": user_msg, "prompt": user_msg})
    llm = LLMFactory.create(provider=provider, db=db)
    # 剧本正文和正文修订不需要 JSON 输出；细纲修订有独立的 JSON role。
    if use_json is None:
        use_json = role_name not in ("script_scene_gen", "script_revision")
    llm_call_id = generate_llm_call_id(task_id)
    return llm.generate(
        prompt=user,
        system_prompt=system,
        max_tokens=role.max_tokens,
        temperature=role.temperature,
        task_type=f"script_pipeline_{role_name}",
        use_json=use_json,
        project_id=project_id,
        task_id=task_id,
        llm_call_id=llm_call_id,
    )


# ═══════════════════════════════════════════════════════════════
# 场景准备信息聚合
# ═══════════════════════════════════════════════════════════════

def _build_screenplay_prep_info(db, project_id: str, screenplay_id: int) -> dict:
    """聚合场景生成所需的全部上下文"""
    from storage.models import Project, Character
    from storage.models.screenplay import Screenplay

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise ValueError(f"Screenplay {screenplay_id} not found")

    # 前序场景概要
    prev_screenplays = (
        db.query(Screenplay)
        .filter(
            Screenplay.project_id == project_id,
            Screenplay.scene_number < screenplay.scene_number,
        )
        .order_by(Screenplay.scene_number.desc())
        .limit(3)
        .all()
    )
    previous_scenes = "\n\n".join(
        [f"【场景{s.scene_number} {s.title}】\n{(s.synopsis or s.content or '')[:800]}"
         for s in reversed(prev_screenplays)]
    ) or "（这是第一个场景）"

    # 出场角色
    char_names = screenplay.characters_present or []
    if char_names:
        chars = db.query(Character).filter(
            Character.project_id == project_id,
            Character.name.in_(char_names),
        ).all()
    else:
        chars = db.query(Character).filter(Character.project_id == project_id).limit(5).all()

    characters_text = "\n\n".join(
        [f"- {c.name}（{c.role or '角色'}）：{c.description or ''}" for c in chars]
    ) or "（暂无角色信息）"

    # 角色外貌快照
    character_appearances = "\n\n".join(
        [f"- {c.name}：{c.appearance_text or (c.description or '')[:200]}" for c in chars]
    ) or "（暂无外貌信息）"

    # 项目大纲参考。ProjectOutline 没有 synopsis 字段，正文在 outline_text。
    project_outline = ""
    try:
        from storage.models import ProjectOutline
        po = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
        if po:
            outline_parts = [
                po.outline_text or "",
                po.pacing_notes or "",
            ]
            if po.structure:
                outline_parts.append(json.dumps(po.structure, ensure_ascii=False))
            project_outline = "\n".join(part for part in outline_parts if part)[:4000]
    except Exception as exc:
        logger.warning(f"[ScriptPipeline] 读取项目大纲失败: {exc}")

    # 伏笔。Foreshadowing 的正文在 content，description 字段并不存在。
    foreshadowings = ""
    try:
        from storage.models import Foreshadowing
        active = db.query(Foreshadowing).filter(
            Foreshadowing.project_id == project_id,
            Foreshadowing.status == "active",
        ).all()
        if active:
            foreshadowings = "\n".join([
                f"- {f.title or '未命名伏笔'}：{f.content or ''}"
                for f in active
            ])
    except Exception as exc:
        logger.warning(f"[ScriptPipeline] 读取伏笔失败: {exc}")

    # 角色弧光。CharacterArc 只保存 character_id，角色名需要从 Character
    # 反查；旧代码访问了不存在的 character_name/arc_description，导致整段
    # 弧光上下文被 try/except 静默吞掉。
    character_arcs = ""
    try:
        from storage.models import CharacterArc
        arcs = db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all()
        if arcs:
            character_by_id = {
                c.id: c
                for c in db.query(Character).filter(Character.project_id == project_id).all()
            }
            arc_lines = []
            for arc in arcs:
                character = character_by_id.get(arc.character_id)
                name = character.name if character else f"角色#{arc.character_id}"
                state = (
                    arc.current_state
                    or arc.start_state
                    or arc.end_state
                    or arc.key_behavior
                    or ""
                )
                if name or state:
                    arc_lines.append(f"- {name}：{state}")
            character_arcs = "\n".join(arc_lines)
    except Exception as exc:
        logger.warning(f"[ScriptPipeline] 读取角色弧光失败: {exc}")

    return {
        "project": project,
        "screenplay": screenplay,
        "previous_scenes": previous_scenes,
        "characters": characters_text,
        "character_appearances": character_appearances,
        "character_arcs": character_arcs or "（暂无弧光信息）",
        "project_outline": project_outline or "（暂无大纲）",
        "foreshadowings": foreshadowings or "（暂无进行中的伏笔）",
    }


# ═══════════════════════════════════════════════════════════════
# 主流水线
# ═══════════════════════════════════════════════════════════════

def run_script_generation_pipeline(
    db,
    project_id: str,
    screenplay_id: int,
    provider: str | None = None,
    task_id: str | None = None,
) -> dict:
    """剧本场景生成 Pipeline（9 步）

    Returns:
        {
            "status": "completed" | "failed",
            "stages": {step_name: {status, data, duration_ms}},
            "screenplay_content": "...",
            "storyboards": [...],
        }
    """
    from storage.models.screenplay import Screenplay, Storyboard

    start_time = time.time()
    stages = {}

    def _run_stage(name: str, fn) -> tuple[Any, float]:
        t0 = time.time()
        try:
            result = fn()
            duration_ms = (time.time() - t0) * 1000
            stages[name] = {"status": "completed", "duration_ms": duration_ms, "data": result}
            return result, duration_ms
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            tb = traceback.format_exc()
            logger.error(f"[ScriptPipeline] stage {name} failed: {e}\n{tb}")
            stages[name] = {"status": "failed", "error": str(e), "duration_ms": duration_ms}
            raise

    try:
        # ── Step 1: 聚合场景准备信息 ──
        prep, _ = _run_stage("1_prep", lambda: _build_screenplay_prep_info(db, project_id, screenplay_id))

        project = prep["project"]
        screenplay = prep["screenplay"]

        # 通用 context 变量
        script_format = project.script_format or "movie"
        common_ctx = {
            "script_format": script_format,
            "scene_number": screenplay.scene_number or 0,
            "scene_title": screenplay.title or "",
            "scene_type": screenplay.scene_type or "对话场景",
            "location": screenplay.location or "",
            "time_of_day": screenplay.time_of_day or "白天",
            "characters": prep["characters"],
            "character_appearances": prep["character_appearances"],
            "character_arcs": prep["character_arcs"],
            "previous_scenes": prep["previous_scenes"],
            "project_outline": prep["project_outline"],
            "foreshadowings": prep["foreshadowings"],
        }

        # ── Step 2: 生成场景细纲 ──
        def _gen_outline():
            user_msg = f"请生成场景 {screenplay.scene_number}「{screenplay.title}」的详细细纲。"
            raw = _call_llm(
                "script_scene_outline_gen", common_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )
            try:
                parsed = _parse_json(raw)
                return parsed if isinstance(parsed, dict) else {
                    "scene_goal": screenplay.synopsis or "",
                    "emotion_arc": "",
                    "dialogue_points": [],
                    "action_notes": [],
                    "transition": "",
                }
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(f"[ScriptPipeline] 场景细纲解析失败，使用最小细纲: {exc}")
                return {
                    "scene_goal": screenplay.synopsis or "",
                    "emotion_arc": "",
                    "dialogue_points": [],
                    "action_notes": [],
                    "transition": "",
                }

        outline_data, _ = _run_stage("2_outline_gen", _gen_outline)

        # ── Step 3: 细纲评审 ──
        def _review_outline():
            review_ctx = {
                **common_ctx,
                "outline": json.dumps(outline_data, ensure_ascii=False, indent=2),
                "content": "",
            }
            user_msg = f"请评审场景 {screenplay.scene_number}「{screenplay.title}」的细纲。"
            raw = _call_llm(
                "script_review", review_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )
            try:
                parsed = _parse_json(raw)
                return parsed if isinstance(parsed, dict) else {
                    "scores": {}, "issues": [], "overall_comment": "评审结果不是对象，已跳过"
                }
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(f"[ScriptPipeline] 细纲评审解析失败，跳过修订: {exc}")
                return {"scores": {}, "issues": [], "overall_comment": "评审解析失败"}

        outline_review, _ = _run_stage("3_outline_review", _review_outline)

        # ── Step 4: 细纲修订（如有 high severity 问题）──
        high_issues = []
        if isinstance(outline_review, dict):
            issues = outline_review.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            high_issues = [
                i for i in issues
                if isinstance(i, dict) and i.get("severity") == "high"
            ]

        if high_issues:
            def _revise_outline():
                suggestions = "\n".join([
                    f"- [{i.get('severity', 'high')}] {i.get('description', '')} → {i.get('suggestion', '')}"
                    for i in high_issues
                ])
                revise_ctx = {
                    **common_ctx,
                    "critique": json.dumps(outline_review, ensure_ascii=False, indent=2),
                    "suggestions": suggestions,
                    "content": json.dumps(outline_data, ensure_ascii=False, indent=2),
                }
                user_msg = f"请根据评审意见修订场景 {screenplay.scene_number} 的细纲。请以 JSON 格式输出修订后的细纲。"
                raw = _call_llm(
                    "script_outline_revision", revise_ctx, user_msg,
                    provider=provider, db=db, project_id=project_id, task_id=task_id,
                    use_json=True,
                )
                try:
                    return _parse_json(raw)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"[ScriptPipeline] outline revise parse failed ({e}), using original outline")
                    return outline_data

            outline_data, _ = _run_stage("4_outline_revise", _revise_outline)

        # ── Step 5: 生成剧本正文 ──
        def _gen_content():
            gen_ctx = {
                **common_ctx,
                "characters_with_appearance": prep["character_appearances"],
                "scene_outline": json.dumps(outline_data, ensure_ascii=False, indent=2),
                "target_words": 2000,
            }
            user_msg = f"请撰写场景 {screenplay.scene_number}「{screenplay.title}」的剧本正文。目标字数：约2000字。"
            return _call_llm(
                "script_scene_gen", gen_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )

        screenplay_content, _ = _run_stage("5_content_gen", _gen_content)

        # ── Step 5.5: 立即保存正文到 DB（避免后续步骤失败时丢失已生成内容）──
        def _save_content_intermediate():
            screenplay.content = screenplay_content
            screenplay.word_count = len(screenplay_content)
            db.commit()
            return {"word_count": screenplay.word_count, "saved_early": True}

        _run_stage("5b_save_content_early", _save_content_intermediate)

        # ── Step 6: 正文评审 ──
        def _review_content():
            review_ctx = {
                **common_ctx,
                "outline": json.dumps(outline_data, ensure_ascii=False, indent=2),
                "content": screenplay_content,
                "characters": prep["characters"],
            }
            user_msg = f"请评审场景 {screenplay.scene_number}「{screenplay.title}」的剧本正文。"
            raw = _call_llm(
                "script_review", review_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )
            try:
                return _parse_json(raw)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[ScriptPipeline] content review parse failed ({e}), skipping review")
                return {"scores": {}, "issues": [], "overall_comment": f"评审解析失败：{e}"}

        content_review, _ = _run_stage("6_content_review", _review_content)

        # ── Step 7: 修订决策 ──
        need_revision = False
        if isinstance(content_review, dict):
            scores = content_review.get("scores", {})
            if not isinstance(scores, dict):
                scores = {}
            numeric_scores = [
                float(value) for value in scores.values()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            ]
            avg_score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0
            issues = content_review.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            high_content_issues = [
                i for i in issues
                if isinstance(i, dict) and i.get("severity") == "high"
            ]
            # 平均分低于 6.5 或有 high severity 问题 → 需要修订
            need_revision = avg_score < 6.5 or len(high_content_issues) > 0

        if need_revision:
            def _revise_content():
                suggestions = "\n".join([
                    f"- [{i.get('severity', 'high')}] {i.get('description', '')} → {i.get('suggestion', '')}"
                    for i in issues
                    if isinstance(i, dict)
                ])
                revise_ctx = {
                    **common_ctx,
                    "critique": json.dumps(content_review, ensure_ascii=False, indent=2),
                    "suggestions": suggestions,
                    "content": screenplay_content,
                }
                user_msg = "请根据评审意见修订剧本正文。"
                return _call_llm(
                    "script_revision", revise_ctx, user_msg,
                    provider=provider, db=db, project_id=project_id, task_id=task_id,
                )

            screenplay_content, _ = _run_stage("7_content_revise", _revise_content)

        # ── Step 8: 保存正文到 Screenplay.content ──
        def _save_content():
            screenplay.content = screenplay_content
            screenplay.word_count = len(screenplay_content)
            screenplay.fingerprint = {
                "outline": outline_data,
                "review": content_review,
                "revised": need_revision,
            }
            db.commit()
            return {"word_count": screenplay.word_count}

        _run_stage("8_save_content", _save_content)

        # ── Step 9: 分镜稿生成 ──
        def _gen_storyboard():
            storyboard_ctx = {
                **common_ctx,
                "characters_with_appearance": prep["character_appearances"],
                "scene_content": screenplay_content,
                "density": storyboard_density_prompt(None),
            }
            user_msg = f"请为场景 {screenplay.scene_number}「{screenplay.title}」制作分镜稿。"
            raw = _call_llm(
                "script_storyboard_gen", storyboard_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )
            return _normalize_storyboard_data(_parse_storyboard_flexible(raw))

        storyboard_data, _ = _run_stage("9_storyboard_gen", _gen_storyboard)

        # 保存分镜稿到 Storyboard 表。生成任务可能重跑：同一事务里先删除
        # 该场景旧分镜，再写入本次去重后的结果，避免重复/残留镜号。
        existing_rows = (
            db.query(Storyboard)
            .filter(
                Storyboard.project_id == project_id,
                Storyboard.screenplay_id == screenplay_id,
            )
            .all()
        )
        for existing in existing_rows:
            db.delete(existing)

        for shot_data in storyboard_data:
            shot_characters = shot_data.get("characters")
            db.add(Storyboard(
                screenplay_id=screenplay_id,
                project_id=project_id,
                shot_number=int(shot_data.get("shot_number") or 1),
                shot_type=shot_data.get("shot_type") or "中景",
                camera_angle=shot_data.get("camera_angle") or "平视",
                camera_movement=shot_data.get("camera_movement") or "固定",
                duration_estimate=shot_data.get("duration_estimate") or "3-5秒",
                location=shot_data.get("location") or screenplay.location or "",
                characters=list(shot_characters) if isinstance(shot_characters, list) else list(screenplay.characters_present or []),
                visual_description=shot_data.get("visual_description") or "",
                dialogue=shot_data.get("dialogue") or "",
                sound_effects=shot_data.get("sound_effects") or "",
                notes=shot_data.get("notes") or "",
            ))
        db.commit()

        # ── Step 10: 后处理 ──
        def _post_process():
            pp_ctx = {
                "scene_content": screenplay_content,
                "characters_with_appearance": prep["character_appearances"],
                "scene_number": screenplay.scene_number or 0,
            }
            user_msg = f"请分析场景 {screenplay.scene_number} 的角色和道具变化。"
            raw = _call_llm(
                "script_post_process", pp_ctx, user_msg,
                provider=provider, db=db, project_id=project_id, task_id=task_id,
            )
            try:
                parsed = _parse_json(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError) as exc:
                # 后处理是增强步骤，解析失败不应丢弃已经生成并保存的正文/分镜。
                logger.warning(f"[ScriptPipeline] 后处理解析失败，跳过增强: {exc}")
                return {}

        post_process_result, _ = _run_stage("10_post_process", _post_process)

        # 应用后处理结果
        _apply_post_process(db, project_id, post_process_result, screenplay_id)

        total_duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"[ScriptPipeline] completed: project={project_id} screenplay={screenplay_id} "
            f"duration={total_duration_ms:.0f}ms"
        )

        return {
            "status": "completed",
            "stages": stages,
            "screenplay_content": screenplay_content,
            "storyboards": storyboard_data,
            "post_processing": post_process_result,
            "duration_ms": total_duration_ms,
        }

    except Exception as e:
        total_duration_ms = (time.time() - start_time) * 1000
        logger.error(
            f"[ScriptPipeline] failed: project={project_id} screenplay={screenplay_id} "
            f"duration={total_duration_ms:.0f}ms error={e}"
        )
        return {
            "status": "failed",
            "stages": stages,
            "error": str(e),
            "duration_ms": total_duration_ms,
        }


def _apply_post_process(db, project_id: str, pp_result: dict | list | str,
                        screenplay_id: int | None = None):
    """应用后处理结果：更新角色外貌、弧光、道具"""
    if not isinstance(pp_result, dict):
        return

    from storage.models import Character, CharacterArc
    from storage.models.screenplay import Property

    # CharacterArc 只有 character_id，没有 character_name 列，故先建名字索引
    char_map = {
        c.name: c
        for c in db.query(Character).filter(Character.project_id == project_id).all()
    }

    # ── 更新角色外貌 ──
    # appearance/appearance_changes 是普通 JSON 列（未包 Mutable），
    # 必须赋新对象，原地改同一个 list/dict 不会被 SQLAlchemy 检测到
    for change in pp_result.get("appearance_changes", []):
        if not isinstance(change, dict) or not change.get("has_change"):
            continue
        char = char_map.get(change.get("character_name", ""))
        if not char:
            logger.warning(
                f"[ScriptPipeline] appearance change for unknown character: "
                f"{change.get('character_name')!r}"
            )
            continue

        new_app = change.get("new_appearance")
        if isinstance(new_app, dict):
            merged = dict(char.appearance or {})
            merged.update({k: v for k, v in new_app.items() if v})
            char.appearance = merged

        record = {
            "scene_id": screenplay_id,
            "description": change.get("change_description", ""),
            "reason": change.get("change_reason", ""),
            "before": change.get("before", ""),
            "after": change.get("after", ""),
        }
        if not any(record[k] for k in ("description", "reason", "before", "after")):
            continue
        char.appearance_changes = list(char.appearance_changes or []) + [record]

    # ── 更新角色弧光 ──
    for arc_update in pp_result.get("arc_updates", []):
        if not isinstance(arc_update, dict):
            continue
        char_name = arc_update.get("character_name", "")
        char = char_map.get(char_name)
        if not char:
            logger.warning(f"[ScriptPipeline] arc update for unknown character: {char_name!r}")
            continue

        new_state = arc_update.get("new_state", "")
        arc_progress = arc_update.get("arc_progress", "")
        try:
            arc = (
                db.query(CharacterArc)
                .filter(CharacterArc.character_id == char.id)
                .order_by(CharacterArc.id.desc())
                .first()
            )
            if arc:
                if new_state:
                    arc.current_state = new_state
                if arc_progress:
                    arc.key_behavior = arc_progress
            else:
                db.add(CharacterArc(
                    project_id=project_id,
                    character_id=char.id,
                    arc_type="成长",
                    start_state="",
                    end_state="",
                    current_state=new_state,
                    key_behavior=arc_progress,
                ))
        except Exception as e:
            logger.warning(f"[ScriptPipeline] arc update failed for {char_name}: {e}")

    # ── 更新道具 ──
    for prop_change in pp_result.get("property_changes", []):
        if not isinstance(prop_change, dict):
            continue
        prop_name = prop_change.get("property_name", "")
        action = prop_change.get("action", "")
        desc = prop_change.get("description", "")
        if not prop_name:
            continue
        prop = db.query(Property).filter(
            Property.project_id == project_id,
            Property.name == prop_name,
        ).first()
        if prop:
            # 更新现有道具
            if action in ("损坏", "失去"):
                prop.status = action
            prop.history = list(prop.history or []) + [
                {"action": action, "description": desc}
            ]
        else:
            # 创建新道具
            new_prop = Property(
                project_id=project_id,
                name=prop_name,
                type="道具",
                description=desc,
                status="获得" if action == "获得" else "完好",
                history=[{"action": action, "description": desc}],
            )
            db.add(new_prop)

    db.commit()


# ═══════════════════════════════════════════════════════════════
# 单独修订接口
# ═══════════════════════════════════════════════════════════════

def run_screenplay_revise(
    db,
    project_id: str,
    screenplay_id: int,
    review_issues: list[dict],
    provider: str | None = None,
):
    """根据评审意见修订剧本正文"""
    from storage.models.screenplay import Screenplay

    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise ValueError(f"Screenplay {screenplay_id} not found")

    if not screenplay.content:
        raise ValueError("Screenplay has no content to revise")

    suggestions = "\n".join([
        f"- [{i.get('severity', 'high')}] {i.get('description', '')} → {i.get('suggestion', '')}"
        for i in review_issues
    ])
    critique = json.dumps({"issues": review_issues}, ensure_ascii=False, indent=2)

    ctx = {
        "critique": critique,
        "suggestions": suggestions,
        "content": screenplay.content,
    }
    user_msg = "请根据评审意见修订剧本正文。"
    revised = _call_llm(
        "script_revision", ctx, user_msg,
        provider=provider, db=db, project_id=project_id,
    )

    screenplay.content = revised
    screenplay.word_count = len(revised)
    db.commit()

    return {
        "status": "completed",
        "revised_content": revised,
        "word_count": screenplay.word_count,
    }

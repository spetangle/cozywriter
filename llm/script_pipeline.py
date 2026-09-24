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
    """宽松 JSON 解析（容忍 markdown / 前缀后缀 / 字符串内换行等常见问题）"""
    if not text or not text.strip():
        raise ValueError("empty response from LLM")
    text = text.strip()
    # 去掉 markdown 代码块包裹
    if text.startswith("```"):
        end_marker = text.find("```", 3)
        if end_marker != -1:
            text = text[3:end_marker].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        else:
            text = text[3:].strip()
            if text.startswith("json"):
                text = text[4:].strip()

    # 尝试提取最大 {…} 或 […] 块
    start_brace = text.find("{")
    start_bracket = text.find("[")
    if start_brace == -1 and start_bracket == -1:
        raise ValueError("No JSON structure found in response")

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        # 提取 {...}
        depth = 0
        end = -1
        for i in range(start_brace, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            text = text[start_brace:end + 1]
    else:
        # 提取 [...]
        depth = 0
        end = -1
        for i in range(start_bracket, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            text = text[start_bracket:end + 1]

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试修复常见问题后解析
    # 移除尾部多余逗号
    cleaned = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    raise json.JSONDecodeError(
        f"JSON parse failed (text len={len(text)})",
        text[:200],
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
            return result
        if isinstance(result, dict):
            # 可能是 {"shots": [...]} 或 {"storyboard": [...]}
            for key in ("shots", "storyboard", "storyboards", "items", "data"):
                if key in result and isinstance(result[key], list):
                    return result[key]
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
              project_id: str | None = None, task_id: str | None = None) -> str:
    """通用 LLM 调用 helper - 剧本专用"""
    role = get_script_role(role_name)
    system = role.build_system(ctx)
    user = role.build_user({**ctx, "context": user_msg, "prompt": user_msg})
    llm = LLMFactory.create(provider=provider, db=db)
    # 剧本正文和修订不需要 JSON 输出
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

    screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
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

    # 项目大纲参考
    project_outline = ""
    try:
        from storage.models import ProjectOutline
        po = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
        if po:
            project_outline = (po.synopsis or "")[:2000]
    except Exception:
        pass

    # 伏笔
    foreshadowings = ""
    try:
        from storage.models import Foreshadowing
        active = db.query(Foreshadowing).filter(
            Foreshadowing.project_id == project_id,
            Foreshadowing.status == "active",
        ).all()
        if active:
            foreshadowings = "\n".join([f"- {f.description}" for f in active])
    except Exception:
        pass

    # 角色弧光
    character_arcs = ""
    try:
        from storage.models import CharacterArc
        arcs = db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all()
        if arcs:
            character_arcs = "\n".join([
                f"- {a.character_name or ''}：{a.current_state or a.arc_description or ''}"
                for a in arcs
            ])
    except Exception:
        pass

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
            return _parse_json(raw)

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
            return _parse_json(raw)

        outline_review, _ = _run_stage("3_outline_review", _review_outline)

        # ── Step 4: 细纲修订（如有 high severity 问题）──
        high_issues = []
        if isinstance(outline_review, dict):
            issues = outline_review.get("issues", [])
            high_issues = [i for i in issues if i.get("severity") == "high"]

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
                    "script_revision", revise_ctx, user_msg,
                    provider=provider, db=db, project_id=project_id, task_id=task_id,
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
            avg_score = sum(scores.values()) / len(scores) if scores else 0
            high_content_issues = [
                i for i in content_review.get("issues", [])
                if i.get("severity") == "high"
            ]
            # 平均分低于 6.5 或有 high severity 问题 → 需要修订
            need_revision = avg_score < 6.5 or len(high_content_issues) > 0

        if need_revision:
            def _revise_content():
                suggestions = "\n".join([
                    f"- [{i.get('severity', 'high')}] {i.get('description', '')} → {i.get('suggestion', '')}"
                    for i in content_review.get("issues", [])
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
            return _parse_storyboard_flexible(raw)

        storyboard_data, _ = _run_stage("9_storyboard_gen", _gen_storyboard)

        # 保存分镜稿到 Storyboard 表
        for shot_data in storyboard_data:
            sb = Storyboard(
                screenplay_id=screenplay_id,
                project_id=project_id,
                shot_number=shot_data.get("shot_number", 1),
                shot_type=shot_data.get("shot_type", "中景"),
                camera_angle=shot_data.get("camera_angle", "平视"),
                camera_movement=shot_data.get("camera_movement", "固定"),
                duration_estimate=shot_data.get("duration_estimate", "3-5秒"),
                location=screenplay.location or "",
                characters=screenplay.characters_present or [],
                visual_description=shot_data.get("visual_description", ""),
                dialogue=shot_data.get("dialogue", ""),
                sound_effects=shot_data.get("sound_effects", ""),
                notes=shot_data.get("notes", ""),
            )
            db.add(sb)
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
            return _parse_json(raw)

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

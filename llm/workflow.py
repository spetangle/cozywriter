"""
项目引导补全 Workflow

当用户创建项目时，4 必填已锁，8 选填可空。
LLM 补全分多个 stage，按依赖关系调度：
  Stage 1    基础外推（必跑）
  Stage 2A/B/C  创意外延（3 子 stage 并行，按需跳过）
  Stage 3A/B/C/D  角色体系
  Stage 4A/B  大纲 + 伏笔
  Stage 5    章节细纲
  Stage 6    汇总入库（事务写入 + RAG 索引）

每个 stage 一次 LLM 调用，JSON 输出，失败可重跑。
"""
import json
import re
import time
from typing import Any

from logger import logger
from llm.factory import LLMFactory
from llm.roles import build_bootstrap_role


# ═══════════════════════════════════════════════════════════════
# Stage DAG 定义
# ═══════════════════════════════════════════════════════════════

STAGE_DEFS = {
    "stage_1_base": {
        "name": "基础外推",
        "description": "从 4 必填推导总章数 / AI 味强度 / 估算总字数",
        "needs_llm": True,
        "depends_on": [],
        "outputs": ["total_chapters", "est_total_words", "ai_removal"],
        "max_tokens": 1024,
        "temperature": 0.3,
    },
    "stage_2a_theme": {
        "name": "核心主旨 + 基调",
        "description": "生成核心主题与基调",
        "needs_llm_if_missing": ["theme", "tone"],
        "depends_on": ["stage_1_base"],
        "outputs": ["theme", "tone"],
        "max_tokens": 1024,
        "temperature": 0.5,
    },
    "stage_2b_style": {
        "name": "文风 + 节奏",
        "description": "生成文风与节奏偏好",
        "needs_llm_if_missing": ["style", "pacing"],
        "depends_on": ["stage_1_base"],
        "outputs": ["style", "pacing"],
        "max_tokens": 1024,
        "temperature": 0.5,
    },
    "stage_2c_world": {
        "name": "世界观骨架",
        "description": "生成世界观条目（按 category 分类）",
        "needs_llm_if_missing": ["premise"],
        "depends_on": ["stage_1_base"],
        "outputs": ["premise"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
    "stage_3a_protagonist": {
        "name": "主角细化",
        "description": "主角设定（Character + profile）",
        "needs_llm_if_missing": ["protagonist"],
        "depends_on": ["stage_2a_theme", "stage_2b_style", "stage_2c_world"],
        "outputs": ["protagonist"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3b_antagonist": {
        "name": "反派细化",
        "description": "反派设定",
        "needs_llm_if_missing": ["antagonist"],
        "depends_on": ["stage_2a_theme", "stage_2b_style", "stage_2c_world"],
        "outputs": ["antagonist"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3c_supporting": {
        "name": "配角 + 关系矩阵",
        "description": "配角角色 + CharacterRelation[]",
        "needs_llm_if_missing": ["supporting"],
        "depends_on": ["stage_3a_protagonist", "stage_3b_antagonist"],
        "outputs": ["supporting"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3d_arcs": {
        "name": "角色弧光设计",
        "description": "所有角色的弧光（CharacterArc[]）",
        "needs_llm": True,
        "depends_on": ["stage_3a_protagonist", "stage_3b_antagonist", "stage_3c_supporting"],
        "outputs": ["arcs"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
    "stage_4a_outline": {
        "name": "项目大纲",
        "description": "plot_lines + structure + pacing_notes",
        "needs_llm": True,
        "depends_on": ["stage_3d_arcs"],
        "outputs": ["outline"],
        "max_tokens": 3072,
        "temperature": 0.6,
    },
    "stage_4b_foreshadow": {
        "name": "伏笔规划",
        "description": "Foreshadowing[]（短/中/长周期）",
        "needs_llm": True,
        "depends_on": ["stage_4a_outline"],
        "outputs": ["foreshadowings"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
    "stage_5_chapters": {
        "name": "章节细纲",
        "description": "每章 ChapterOutline + Chapter 记录",
        "needs_llm": True,
        "depends_on": ["stage_4a_outline", "stage_4b_foreshadow"],
        "outputs": ["chapter_outlines"],
        "max_tokens": 4096,
        "temperature": 0.6,
    },
}


# ═══════════════════════════════════════════════════════════════
# Stage prompt 构造
# ═══════════════════════════════════════════════════════════════

STAGE_PROMPTS = {
    "stage_1_base": {
        "task": (
            "根据用户提供的 4 项必填信息，推导项目基础参数。\n"
            "要求：\n"
            "1. 根据【题材】+【创意信息】估算合适的总章节数（玄幻 30~50，都市 25~35，科幻 25~40，"
            "武侠/仙侠 30~50，历史 25~40，悬疑 20~30，现实主义 15~25，奇幻 30~50）\n"
            "2. 根据【章节字数】估算总字数 = total_chapters * chapter_word_count * 1000\n"
            "3. 推荐去 AI 味强度（1-10，默认 7；冷峻/平实风格偏高 8-9，优美/诗意偏低 5-6）\n"
            "4. 推荐 ai_removal 数值（1-10）\n"
        ),
        "json_schema": {
            "total_chapters": 30,
            "est_total_words": 90000,
            "ai_removal": 7,
            "rationale": "推导理由（1-2 句话）",
        },
    },
    "stage_2a_theme": {
        "task": (
            "根据用户的题材和一句话故事，生成：\n"
            "1. theme：核心主题（一句话，15 字内）\n"
            "2. tone：基调（必须从 热血/治愈/黑暗/轻松/史诗/悬疑紧张/浪漫/幽默/冷峻 中选一个）\n"
        ),
        "json_schema": {"theme": "...", "tone": "..."},
    },
    "stage_2b_style": {
        "task": (
            "根据题材和基调推荐：\n"
            "1. style：文风（必须从 优美/平实/诗意/幽默/冷峻 中选一个）\n"
            "2. pacing：节奏（必须从 快节奏/中等节奏/慢热型/起伏型 中选一个）\n"
        ),
        "json_schema": {"style": "...", "pacing": "..."},
    },
    "stage_2c_world": {
        "task": (
            "根据题材构建世界观骨架，输出 4-6 个分类条目。\n"
            "category 必须是以下之一：地理 / 历史 / 势力 / 规则 / 社会 / 技术\n"
            "tags 为该条目的标签数组（2-4 个关键词）。\n"
        ),
        "json_schema": {
            "world_entries": [
                {"category": "地理", "title": "...", "content": "...", "tags": ["..."]},
                {"category": "历史", "title": "...", "content": "...", "tags": ["..."]},
            ]
        },
    },
    "stage_3a_protagonist": {
        "task": (
            "根据题材 + 主旨 + 世界观，设计主角。\n"
            "要求：\n"
            "1. name：角色名（2-3 个汉字）\n"
            "2. role：固定为 '主角'\n"
            "3. profile 字段：age（数字）, gender（男/女/其他）, identity（身份 1 句）,"
            "personality（性格 2-3 个关键词）, goal（核心目标 1 句）, weakness（弱点 1 句）,"
            "ability（能力/资源 1 句）, catchphrase（口头禅 1 句，可空）, background（背景 1-2 句）\n"
            "4. description：补充描述（3-5 句）\n"
        ),
        "json_schema": {
            "name": "...",
            "role": "主角",
            "profile": {
                "age": 18,
                "gender": "男",
                "identity": "...",
                "personality": "...",
                "goal": "...",
                "weakness": "...",
                "ability": "...",
                "catchphrase": "...",
                "background": "...",
            },
            "description": "...",
        },
    },
    "stage_3b_antagonist": {
        "task": (
            "根据题材 + 主旨 + 世界观 + 主角设定，设计反派。\n"
            "要求：\n"
            "1. name：角色名（2-3 个汉字）\n"
            "2. role：固定为 '反派'\n"
            "3. profile 字段：与主角一致\n"
            "4. description：补充描述（3-5 句，包含与主角的核心矛盾）\n"
        ),
        "json_schema": {
            "name": "...",
            "role": "反派",
            "profile": {
                "age": 0,
                "gender": "...",
                "identity": "...",
                "personality": "...",
                "goal": "...",
                "weakness": "...",
                "ability": "...",
                "catchphrase": "...",
                "background": "...",
            },
            "description": "...",
        },
    },
    "stage_3c_supporting": {
        "task": (
            "根据主角与反派设定，设计 2-4 名重要配角，并建立 3-5 条关系。\n"
            "配角 role 必须是 '配角'。\n"
            "关系字段：\n"
            "  from / to：角色名（必须在主角/反派/本步骤配角中）\n"
            "  type：关系类型（友情/爱情/亲情/师徒/敌对/竞争/合作/...）\n"
            "  description：关系描述（1 句）\n"
            "  strength：1-10 的强度\n"
            "  status：stable / developing / tense / broken\n"
        ),
        "json_schema": {
            "supporting": [
                {
                    "name": "...",
                    "role": "配角",
                    "profile": {
                        "identity": "...",
                        "personality": "...",
                        "relationship_to_protagonist": "...",
                    },
                    "description": "...",
                }
            ],
            "relations": [
                {
                    "from": "主角名",
                    "to": "配角名",
                    "type": "...",
                    "description": "...",
                    "strength": 5,
                    "status": "stable",
                }
            ],
        },
    },
    "stage_3d_arcs": {
        "task": (
            "为所有已确认角色设计弧光。\n"
            "arc_type 必须是：成长 / 堕落 / 平线 / 循环\n"
            "要求：\n"
            "1. 每个角色一条弧光\n"
            "2. start_state：起点状态（1 句）\n"
            "3. end_state：终点状态（1 句）\n"
            "4. key_behavior：体现弧光的关键行为（1 句）\n"
            "5. is_stable：是否稳定（默认 true）\n"
        ),
        "json_schema": {
            "arcs": [
                {
                    "character_name": "...",
                    "arc_type": "成长",
                    "start_state": "...",
                    "end_state": "...",
                    "key_behavior": "...",
                    "is_stable": True,
                }
            ]
        },
    },
    "stage_4a_outline": {
        "task": (
            "根据所有已确定的角色与世界设定，设计完整的项目大纲。\n"
            "要求：\n"
            "1. plot_lines：3-5 条剧情线，每条包含 title, description, from_chapter, to_chapter, priority\n"
            "2. structure.acts：4 幕结构（开局/发展/高潮/结局），每幕给 from_chapter / to_chapter\n"
            "3. pacing_notes：整体节奏规划（2-3 句）\n"
            "4. outline_text：完整大纲文本（200-500 字概述）\n"
        ),
        "json_schema": {
            "plot_lines": [
                {
                    "title": "...",
                    "description": "...",
                    "from_chapter": 1,
                    "to_chapter": 10,
                    "priority": 1,
                }
            ],
            "structure": {
                "acts": [
                    {"name": "第一幕", "from_chapter": 1, "to_chapter": 8},
                    {"name": "第二幕", "from_chapter": 9, "to_chapter": 18},
                    {"name": "第三幕", "from_chapter": 19, "to_chapter": 25},
                    {"name": "第四幕", "from_chapter": 26, "to_chapter": 30},
                ]
            },
            "pacing_notes": "...",
            "outline_text": "...",
        },
    },
    "stage_4b_foreshadow": {
        "task": (
            "根据项目大纲，规划 5-8 条伏笔。\n"
            "type 必须是：短期（1-5 章内回收）/ 中期（6-15 章）/ 长期（跨幕）\n"
            "要求：\n"
            "1. suggested_plant_chapter：建议埋设章节号\n"
            "2. suggested_resolve_chapter：建议回收章节号\n"
        ),
        "json_schema": {
            "foreshadowings": [
                {
                    "title": "...",
                    "content": "...",
                    "type": "短期",
                    "suggested_plant_chapter": 1,
                    "suggested_resolve_chapter": 5,
                }
            ]
        },
    },
    "stage_5_chapters": {
        "task": (
            "为整本小说生成每章的细纲。\n"
            "要求：\n"
            "1. 总章数 = project.total_chapters（参见 locked_inputs）\n"
            "2. 每章字数参考 = chapter_word_count * 1000，min = 0.7x, max = 1.3x\n"
            "3. chapter_position：开局/发展/高潮/回落/结局\n"
            "4. pacing：铺垫/推进/高潮/回落/平稳\n"
            "5. key_content：核心内容（1-2 句）\n"
            "6. plot_advance：剧情推进（1 句）\n"
            "7. foreshadow_notes：埋设/回收伏笔说明\n"
            "8. conflicts：冲突列表（每项 {type, desc}）\n"
            "9. highlights：看点列表（2-3 个）\n"
            "10. notes：备注（可选）\n"
        ),
        "json_schema": {
            "chapters": [
                {
                    "order": 1,
                    "title": "第一章 xxx",
                    "chapter_position": "开局",
                    "act_name": "第一幕",
                    "pacing": "铺垫",
                    "key_content": "...",
                    "plot_advance": "...",
                    "foreshadow_notes": "...",
                    "conflicts": [{"type": "...", "desc": "..."}],
                    "highlights": ["..."],
                    "target_word_count": 3000,
                    "min_word_count": 2100,
                    "max_word_count": 3900,
                    "notes": "...",
                }
            ]
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# 规划：根据用户已填字段动态裁剪 stage
# ═══════════════════════════════════════════════════════════════

def plan_bootstrap_stages(required: dict, user_filled: dict) -> list[dict]:
    """
    根据 4 必填 + 用户已填选填，裁剪 stage 计划

    Returns:
        [
            {"id": "stage_1_base", "name": "...", "needs_llm": True, ...},
            ...
        ]
    """
    stages = []
    for stage_id, defn in STAGE_DEFS.items():
        if "needs_llm_if_missing" in defn:
            # 任一目标字段未填则需要 LLM
            needs = any(
                not user_filled.get(f) for f in defn["needs_llm_if_missing"]
            )
        else:
            needs = defn.get("needs_llm", False)

        stages.append({
            "id": stage_id,
            "name": defn["name"],
            "description": defn["description"],
            "needs_llm": needs,
            "depends_on": defn["depends_on"],
            "outputs": defn["outputs"],
            "status": "pending",
        })
    return stages


# ═══════════════════════════════════════════════════════════════
# 同步执行 Workflow
# ═══════════════════════════════════════════════════════════════

def run_bootstrap_sync(run_id: int, user_input: dict, db=None) -> dict:
    """
    同步执行 bootstrap workflow（在线程池中调用）

    Args:
        run_id: WorkflowRun.id
        user_input: 用户完整输入（4 必填 + 8 选填）
        db: 可选外部 Session

    Returns:
        {"status": "completed" | "failed", "stage_results": {...}, "error": "..."}
    """
    from storage.models.workflow import WorkflowRun
    from storage.database import SessionLocal

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return {"status": "failed", "error": f"Run {run_id} not found"}

        # 持久化 user_input 到 stage_results._meta（供后续 rerun_stage 读取）
        stage_results = dict(run.stage_results or {})
        stage_results["_meta"] = {
            "user_input": {k: v for k, v in user_input.items() if k != "_project_id"},
            "ts": time.time(),
        }

        # 提权 4 必填为 locked
        locked = {
            "title": user_input.get("title", ""),
            "chapter_word_count": user_input.get("chapter_word_count", 0),
            "genre": user_input.get("genre", ""),
            "description": user_input.get("description", ""),
        }

        # 用户已填的选填
        user_filled = {
            k: v for k, v in user_input.items()
            if k not in locked and v
        }

        llm_logs = list(run.llm_logs or [])

        run.status = "running"
        run.current_stage_index = 0
        db.commit()

        # 拓扑排序执行
        stages = run.stages or []
        completed_set = set()

        for stage in stages:
            stage_id = stage["id"]

            # 依赖未满足则跳过
            deps_ok = all(
                stage_results.get(d, {}).get("status") in ("ok", "skipped", "user_filled")
                for d in stage["depends_on"]
            )
            if not deps_ok:
                stage_results[stage_id] = {
                    "status": "failed",
                    "error": f"Dependency not satisfied: {stage['depends_on']}",
                }
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "skipped_dep",
                })
                continue

            if not stage["needs_llm"]:
                # 用户已填对应字段 → 标记为 user_filled
                stage_results[stage_id] = {
                    "status": "user_filled",
                    "user_values": {k: user_filled.get(k) for k in stage["outputs"] if k in user_filled},
                }
                completed_set.add(stage_id)
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "user_filled",
                })
                continue

            # 执行 LLM 调用
            logger.info(f"[Bootstrap] running stage {stage_id} ...")
            # 立即把 stage 标为 running，commit，让前端轮询能看到
            stage_results[stage_id] = {
                "status": "running",
                "started_at": time.time(),
            }
            run.stage_results = stage_results
            run.current_stage_index = sum(
                1 for r in stage_results.values()
                if r.get("status") in ("ok", "user_filled", "skipped")
            )
            db.commit()
            try:
                # 收集已完成的 stage 产物
                prev_outputs = {
                    sid: stage_results[sid].get("data", {})
                    for sid in completed_set
                    if sid in stage_results and "data" in stage_results[sid]
                }

                result = _run_single_stage(
                    stage_id=stage_id,
                    locked=locked,
                    user_filled=user_filled,
                    prev_outputs=prev_outputs,
                )

                stage_results[stage_id] = {
                    "status": "ok",
                    "data": result,
                    "completed_at": time.time(),
                }
                completed_set.add(stage_id)
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "ok",
                })
                run.current_stage_index += 1
                db.commit()

            except Exception as e:
                logger.error(f"[Bootstrap] stage {stage_id} failed: {e}")
                stage_results[stage_id] = {"status": "failed", "error": str(e)}
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "failed",
                    "error": str(e),
                })

        # 计算总状态
        has_failure = any(
            r.get("status") == "failed" for r in stage_results.values()
        )
        all_done = all(
            r.get("status") in ("ok", "user_filled", "skipped")
            for r in stage_results.values()
        )

        if has_failure:
            run.status = "failed"
        elif all_done:
            run.status = "completed"
        else:
            run.status = "partial"

        run.stage_results = stage_results
        run.llm_logs = llm_logs
        db.commit()

        return {
            "status": run.status,
            "stage_results": stage_results,
            "llm_logs": llm_logs,
        }

    finally:
        if should_close:
            db.close()


def _run_single_stage(stage_id: str, locked: dict, user_filled: dict,
                      prev_outputs: dict) -> dict:
    """单个 stage 的 LLM 调用 + JSON 解析"""
    defn = STAGE_DEFS[stage_id]
    prompt_def = STAGE_PROMPTS[stage_id]

    role = build_bootstrap_role(
        task_description=prompt_def["task"],
        locked_inputs=locked,
        prev_outputs=prev_outputs,
        max_tokens=defn["max_tokens"],
        temperature=defn["temperature"],
    )

    system_prompt = role.system_prompt
    user_prompt = (
        f"请输出 JSON，schema 参考：\n{json.dumps(prompt_def['json_schema'], ensure_ascii=False, indent=2)}\n"
        f"只输出 JSON，不要任何解释。"
    )

    llm = LLMFactory.create()
    response = llm.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=role.max_tokens,
        temperature=role.temperature,
    )

    return _parse_json(response)


def _parse_json(text: str) -> dict:
    """从 LLM 响应中解析 JSON（容错：处理 markdown 包装、尾随文本）"""
    text = text.strip()

    # 去掉 markdown 代码块
    if text.startswith("```"):
        # 取第一个代码块
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    # 找首个 { 和最后一个 } 的范围
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


# ═══════════════════════════════════════════════════════════════
# 事务写入 DB
# ═══════════════════════════════════════════════════════════════

def commit_bootstrap(project_id: int, run_id: int, db) -> dict:
    """
    把 stage_results 事务写入 DB + 索引 RAG

    Returns:
        {"status": "committed" | "failed", "summary": {...}, "error": "..."}
    """
    from storage.models.workflow import WorkflowRun
    from storage.models import (
        Project, Theme, WorldEntry, Character, CharacterArc,
        CharacterRelation, ProjectOutline, Foreshadowing, Chapter, ChapterOutline,
    )

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"status": "failed", "error": "Run not found"}

    results = run.stage_results or {}

    try:
        # ── Stage 1: 更新 Project 基础参数 ──
        if results.get("stage_1_base", {}).get("status") == "ok":
            data = results["stage_1_base"]["data"]
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                if data.get("total_chapters"):
                    project.total_chapters = int(data["total_chapters"])
                if data.get("ai_removal"):
                    project.ai味去除程度 = int(data["ai_removal"])
                if data.get("est_total_words"):
                    # 存到 description 后缀（不污染用户原文）
                    total_w = int(data["est_total_words"])
                    if project.description and "[估算总字数：" not in project.description:
                        project.description += f"\n\n[估算总字数：{total_w} 字]"
                    elif not project.description:
                        project.description = f"[估算总字数：{total_w} 字]"

        # ── Stage 2A: Theme ──
        if results.get("stage_2a_theme", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2a_theme")
            theme_title = data.get("theme") or ""
            if theme_title:
                t = Theme(
                    project_id=project_id,
                    theme_type="core_theme",
                    title=theme_title,
                    description=f"基调：{data.get('tone', '')}",
                )
                db.add(t)

        # ── Stage 2B: Style + Pacing ──
        if results.get("stage_2b_style", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2b_style")
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                if data.get("style"):
                    project.writing_style = data["style"]
                if data.get("pacing"):
                    # 节奏存为附加 metadata（暂存到 description）
                    tag = f"[节奏：{data['pacing']}]"
                    if tag not in (project.description or ""):
                        project.description = (project.description or "") + f"\n{tag}"

        # ── Stage 2C: WorldEntry[] ──
        if results.get("stage_2c_world", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2c_world")
            # data 可能是 dict（含 world_entries 列表）或字符串（premise 文本）
            if isinstance(data, str):
                we = WorldEntry(
                    project_id=project_id,
                    category="背景设定",
                    title="世界观背景",
                    content=data,
                )
                db.add(we)
            elif isinstance(data, dict):
                if data.get("world_entries"):
                    for we_data in data["world_entries"]:
                        we = WorldEntry(
                            project_id=project_id,
                            category=we_data.get("category", "背景设定"),
                            title=we_data.get("title", ""),
                            content=we_data.get("content", ""),
                            tags=we_data.get("tags", []),
                        )
                        db.add(we)
                elif data.get("premise"):
                    # user_filled 但以 dict 形式（兼容老数据）
                    we = WorldEntry(
                        project_id=project_id,
                        category="背景设定",
                        title="世界观背景",
                        content=data["premise"],
                    )
                    db.add(we)

        # ── Stage 3A/3B/3C: Characters + Relations ──
        char_map = {}  # name → id
        for stage_id, role_default in [
            ("stage_3a_protagonist", "主角"),
            ("stage_3b_antagonist", "反派"),
            ("stage_3c_supporting", "配角"),
        ]:
            stage_info = results.get(stage_id, {})
            if stage_info.get("status") == "ok" and stage_info.get("data"):
                data = stage_info["data"]
                chars = _extract_characters(data, stage_id, role_default)
                for c in chars:
                    char = Character(
                        project_id=project_id,
                        name=c.get("name", "未命名"),
                        role=c.get("role", role_default),
                        profile=c.get("profile", {}),
                        description=c.get("description", ""),
                    )
                    db.add(char)
                    db.flush()
                    if c.get("name"):
                        char_map[c["name"]] = char.id

        # Stage 3C 的 relations
        if results.get("stage_3c_supporting", {}).get("status") == "ok":
            rels = results["stage_3c_supporting"]["data"].get("relations", [])
            for rel in rels:
                from_id = char_map.get(rel.get("from"))
                to_id = char_map.get(rel.get("to"))
                if from_id and to_id and from_id != to_id:
                    relation = CharacterRelation(
                        project_id=project_id,
                        from_character_id=from_id,
                        to_character_id=to_id,
                        relation_type=rel.get("type", ""),
                        description=rel.get("description", ""),
                        strength=rel.get("strength", 5),
                        status=rel.get("status", "stable"),
                    )
                    db.add(relation)

        # ── Stage 3D: CharacterArc[] ──
        if results.get("stage_3d_arcs", {}).get("status") == "ok":
            arcs = results["stage_3d_arcs"]["data"].get("arcs", [])
            for arc in arcs:
                cid = char_map.get(arc.get("character_name"))
                if cid:
                    char_arc = CharacterArc(
                        project_id=project_id,
                        character_id=cid,
                        arc_type=arc.get("arc_type", "成长"),
                        start_state=arc.get("start_state", ""),
                        end_state=arc.get("end_state", ""),
                        current_state=arc.get("start_state", ""),
                        key_behavior=arc.get("key_behavior", ""),
                        is_stable=arc.get("is_stable", True),
                    )
                    db.add(char_arc)

        # ── Stage 4A: ProjectOutline ──
        if results.get("stage_4a_outline", {}).get("status") == "ok":
            data = results["stage_4a_outline"]["data"]
            outline = ProjectOutline(
                project_id=project_id,
                plot_lines=data.get("plot_lines", []),
                structure=data.get("structure", {}),
                pacing_notes=data.get("pacing_notes", ""),
                outline_text=data.get("outline_text", ""),
            )
            db.add(outline)

        # ── Stage 4B: Foreshadowing[] ──
        foreshadow_map = {}  # title → id（供 Stage 5 引用）
        if results.get("stage_4b_foreshadow", {}).get("status") == "ok":
            fores = results["stage_4b_foreshadow"]["data"].get("foreshadowings", [])
            for fs in fores:
                fore = Foreshadowing(
                    project_id=project_id,
                    title=fs.get("title", ""),
                    content=fs.get("content", ""),
                    plant_order=fs.get("suggested_plant_chapter", 0),
                    status="active",
                )
                db.add(fore)
                db.flush()
                if fs.get("title"):
                    foreshadow_map[fs["title"]] = fore.id

        # ── Stage 5: Chapter + ChapterOutline ──
        if results.get("stage_5_chapters", {}).get("status") == "ok":
            chapters = results["stage_5_chapters"]["data"].get("chapters", [])
            for ch in chapters:
                order = ch.get("order", 0)
                chapter = Chapter(
                    project_id=project_id,
                    title=ch.get("title", f"第{order}章"),
                    order=order,
                    content="",
                    word_count=0,
                )
                db.add(chapter)
                db.flush()
                # 解析 foreshadow_notes 中的伏笔标题 → id
                fs_ids = _resolve_foreshadow_ids(
                    ch.get("foreshadow_notes", ""),
                    foreshadow_map,
                )
                outline = ChapterOutline(
                    chapter_id=chapter.id,
                    chapter_position=ch.get("chapter_position", ""),
                    act_name=ch.get("act_name", ""),
                    key_content=ch.get("key_content", ""),
                    plot_advance=ch.get("plot_advance", ""),
                    foreshadow_ids=fs_ids,
                    foreshadow_notes=ch.get("foreshadow_notes", ""),
                    conflicts=ch.get("conflicts", []),
                    highlights=ch.get("highlights", []),
                    target_word_count=ch.get("target_word_count", 0),
                    min_word_count=ch.get("min_word_count", 0),
                    max_word_count=ch.get("max_word_count", 0),
                    pacing=ch.get("pacing", "平稳"),
                    character_ids=[],
                    status="planning",
                    notes=ch.get("notes", ""),
                )
                db.add(outline)

        run.status = "committed"
        db.commit()

        # 索引 RAG（失败不影响主流程）
        _index_to_rag(project_id, db)

        return {
            "status": "committed",
            "summary": {
                "themes": db.query(Theme).filter(Theme.project_id == project_id).count(),
                "world_entries": db.query(WorldEntry).filter(WorldEntry.project_id == project_id).count(),
                "characters": db.query(Character).filter(Character.project_id == project_id).count(),
                "relations": db.query(CharacterRelation).filter(CharacterRelation.project_id == project_id).count(),
                "arcs": db.query(CharacterArc).filter(CharacterArc.project_id == project_id).count(),
                "foreshadowings": db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id).count(),
                "chapters": db.query(Chapter).filter(Chapter.project_id == project_id).count(),
            },
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[Bootstrap commit] failed: {e}")
        return {"status": "failed", "error": str(e)}


def _stage_data(results: dict, stage_id: str) -> dict | str:
    """提取 stage 实际数据（user_filled 时可能是字符串）"""
    info = results.get(stage_id, {})
    if info.get("status") == "user_filled":
        return info.get("user_values", {})
    return info.get("data", {})


def _extract_characters(data: dict, stage_id: str, role_default: str) -> list[dict]:
    """从 stage 数据中提取角色列表"""
    if stage_id == "stage_3c_supporting":
        return data.get("supporting", [])
    # 主角 / 反派是单 character
    if data.get("name") or data.get("profile"):
        return [data]
    return []


def _resolve_foreshadow_ids(notes: str, foreshadow_map: dict) -> list[int]:
    """从 foreshadow_notes 文本中匹配伏笔标题 → id"""
    if not notes or not foreshadow_map:
        return []
    ids = []
    for title, fid in foreshadow_map.items():
        if title and title in notes:
            ids.append(fid)
    return ids


def _index_to_rag(project_id: int, db):
    """把所有生成的设定索引到 Chroma"""
    try:
        from rag.knowledge_base import KnowledgeBase
        from storage.models import Character, WorldEntry, Chapter

        kb = KnowledgeBase()

        for c in db.query(Character).filter(Character.project_id == project_id).all():
            try:
                kb.add_character(c)
            except Exception:
                pass

        for w in db.query(WorldEntry).filter(WorldEntry.project_id == project_id).all():
            try:
                kb.add_world_entry(w)
            except Exception:
                pass

        for ch in db.query(Chapter).filter(Chapter.project_id == project_id).all():
            try:
                kb.add_chapter(ch)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[RAG index] partial failure: {e}")


# ═══════════════════════════════════════════════════════════════
# 单 stage 重跑
# ═══════════════════════════════════════════════════════════════

def rerun_stage(run_id: int, stage_id: str, db) -> dict:
    """
    重新跑某个 stage（覆盖之前的结果）

    注意：必须满足依赖；返回 {status, stage_result}
    """
    from storage.models.workflow import WorkflowRun

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"status": "failed", "error": "Run not found"}

    if stage_id not in STAGE_DEFS:
        return {"status": "failed", "error": f"Unknown stage: {stage_id}"}

    stage_def = STAGE_DEFS[stage_id]
    stage_results = dict(run.stage_results or {})

    # 检查依赖
    for dep in stage_def["depends_on"]:
        if stage_results.get(dep, {}).get("status") not in ("ok", "user_filled", "skipped"):
            return {"status": "failed", "error": f"Dependency {dep} not ready"}

    # 提取 locked + user_filled（从 _meta 读取持久化的 user_input）
    project_id = run.project_id
    meta = stage_results.get("_meta", {})
    user_input = meta.get("user_input", {})
    if not user_input:
        return {"status": "failed", "error": "user_input not found in run._meta (run predates rerun support)"}

    locked = {
        "title": user_input.get("title", ""),
        "chapter_word_count": user_input.get("chapter_word_count", 0),
        "genre": user_input.get("genre", ""),
        "description": user_input.get("description", ""),
    }
    user_filled = {
        k: v for k, v in user_input.items()
        if k not in locked and v
    }

    prev_outputs = {
        sid: stage_results[sid].get("data", {})
        for sid in stage_def["depends_on"]
        if sid in stage_results and "data" in stage_results[sid]
    }

    try:
        result = _run_single_stage(
            stage_id=stage_id,
            locked=locked,
            user_filled=user_filled,
            prev_outputs=prev_outputs,
        )
        stage_results[stage_id] = {"status": "ok", "data": result}
        run.stage_results = stage_results
        db.commit()
        return {"status": "ok", "stage_result": stage_results[stage_id]}
    except Exception as e:
        stage_results[stage_id] = {"status": "failed", "error": str(e)}
        run.stage_results = stage_results
        db.commit()
        return {"status": "failed", "error": str(e)}

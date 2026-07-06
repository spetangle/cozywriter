"""创意问卷 API"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.creative_questionnaire import CreativeQuestionnaire, QUESTIONNAIRE_QUESTIONS, STEP_QUESTIONS, TOTAL_STEPS
from logger import logger


router = APIRouter(prefix="/api/questionnaires", tags=["创意问卷"])


# ─── Schemas ───

class QuestionnaireCreate(BaseModel):
    title: str = "未命名问卷"
    answers: dict = {}


class QuestionnaireUpdate(BaseModel):
    title: str | None = None
    answers: dict | None = None
    status: str | None = None
    created_project_id: str | None = None


class QuestionnaireResponse(BaseModel):
    id: int
    title: str
    novel_title: str | None = None
    answers: dict | None = None
    llm_suggestions: dict | None = None
    questionnaire_type: str | None = None
    status: str | None = None
    current_step: int | None = None
    created_project_id: str | None = None
    ai_completed_answers: dict | None = None
    created_at: object | None = None
    updated_at: object | None = None

    class Config:
        from_attributes = True


class StepAnswer(BaseModel):
    question_id: str
    answer: str
    is_custom: bool = False


class StepResponse(BaseModel):
    questionnaire_id: int
    current_step: int
    total_steps: int
    question: dict | None = None
    answers: dict = {}
    is_completed: bool = False
    can_skip_to_ai: bool = True


class AiCompleteRequest(BaseModel):
    questionnaire_id: int
    answers: dict


class AiCompleteResponse(BaseModel):
    status: str
    questionnaire_id: int
    ai_answers: dict
    message: str


class LlmOptionsResponse(BaseModel):
    status: str
    questionnaire_id: int
    step: int
    question_id: str
    llm_options: list = []
    suggestions: dict = {}


# ─── Routes ───

@router.get("/questions")
async def get_questions():
    """获取预设问卷题目（供前端渲染）"""
    return QUESTIONNAIRE_QUESTIONS


@router.get("/step-questions")
async def get_step_questions():
    """获取分步问卷题目列表"""
    return {"questions": STEP_QUESTIONS, "total_steps": TOTAL_STEPS}


@router.get("")
def list_questionnaires(db: Session = Depends(get_db)):
    """获取所有问卷"""
    qs = db.query(CreativeQuestionnaire).order_by(CreativeQuestionnaire.updated_at.desc()).all()
    result = []
    for q in qs:
        item = {
            "id": q.id,
            "title": q.title,
            "novel_title": q.novel_title,
            "answers": q.answers if q.answers else {},
            "llm_suggestions": q.llm_suggestions if q.llm_suggestions else {},
            "questionnaire_type": q.questionnaire_type,
            "status": q.status,
            "current_step": q.current_step,
            "created_project_id": q.created_project_id,
            "ai_completed_answers": q.ai_completed_answers if q.ai_completed_answers else {},
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        }
        result.append(item)
    return JSONResponse(content=result)


@router.post("", response_model=QuestionnaireResponse)
async def create_questionnaire(data: QuestionnaireCreate, db: Session = Depends(get_db)):
    """创建问卷（开始新问卷）"""
    logger.info(f"[问卷] 开始创建新问卷，标题: {data.title}, 初始答案: {data.answers}")
    q = CreativeQuestionnaire(
        title=data.title,
        answers=data.answers,
        llm_suggestions={},
        status="in_progress",
        current_step=0,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    logger.info(f"[问卷] 问卷创建成功，ID: {q.id}, 当前步骤: {q.current_step}, 状态: {q.status}")
    return q


@router.put("/{q_id}", response_model=QuestionnaireResponse)
async def update_questionnaire(q_id: int, data: QuestionnaireUpdate, db: Session = Depends(get_db)):
    """更新问卷答案"""
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    if data.title is not None:
        q.title = data.title
    if data.answers is not None:
        q.answers = data.answers
    if data.status is not None:
        q.status = data.status
    if data.created_project_id is not None:
        q.created_project_id = data.created_project_id
    db.commit()
    db.refresh(q)
    return q


@router.delete("/{q_id}")
async def delete_questionnaire(q_id: int, db: Session = Depends(get_db)):
    """删除问卷"""
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    db.delete(q)
    db.commit()
    return {"status": "ok"}


class BatchDeleteRequest(BaseModel):
    ids: list[int]


@router.post("/batch/delete")
async def batch_delete_questionnaires(data: BatchDeleteRequest, db: Session = Depends(get_db)):
    """批量删除问卷"""
    if not data.ids:
        return {"status": "ok", "deleted_count": 0}
    
    count = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id.in_(data.ids)).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok", "deleted_count": count}


# ─── 分步问卷流程 ───

@router.get("/{q_id}/current-step", response_model=StepResponse)
async def get_current_step(q_id: int, db: Session = Depends(get_db)):
    """获取当前步骤的题目"""
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if q.status == "completed" or q.status == "cancelled":
        return StepResponse(
            questionnaire_id=q.id,
            current_step=q.current_step,
            total_steps=TOTAL_STEPS,
            question=None,
            answers=q.answers,
            is_completed=True,
        )

    current_step = q.current_step
    if current_step >= TOTAL_STEPS:
        return StepResponse(
            questionnaire_id=q.id,
            current_step=current_step,
            total_steps=TOTAL_STEPS,
            question=None,
            answers=q.answers,
            is_completed=True,
        )

    question = next((q_item for q_item in STEP_QUESTIONS if q_item["step"] == current_step), None)
    
    if question and question.get("llm_enabled", False):
        llm_suggestions = q.llm_suggestions or {}
        if question["id"] in llm_suggestions:
            question = question.copy()
            question["options"] = llm_suggestions[question["id"]].get("options", question.get("options", []))
    
    return StepResponse(
        questionnaire_id=q.id,
        current_step=current_step,
        total_steps=TOTAL_STEPS,
        question=question,
        answers=q.answers,
        is_completed=False,
    )


@router.post("/{q_id}/prev-step", response_model=StepResponse)
async def prev_step(q_id: int, db: Session = Depends(get_db)):
    """后退到上一步"""
    logger.info(f"[问卷] 用户请求后退，问卷ID: {q_id}")
    
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        logger.error(f"[问卷] 后退失败：问卷不存在，ID: {q_id}")
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if q.current_step <= 0:
        logger.warning(f"[问卷] 已经是第一步，无法后退，问卷ID: {q_id}")
        return await get_current_step(q_id, db)

    q.current_step = q.current_step - 1
    db.commit()
    db.refresh(q)

    logger.info(f"[问卷] 后退成功，问卷ID: {q_id}, 当前步骤: {q.current_step}")
    return await get_current_step(q_id, db)


@router.post("/{q_id}/generate-llm-options", response_model=LlmOptionsResponse)
async def generate_llm_options(q_id: int, db: Session = Depends(get_db)):
    """使用LLM生成当前问题的选项（基于之前的答案上下文）"""
    logger.info(f"[问卷] 用户请求生成LLM选项，问卷ID: {q_id}")
    
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        logger.error(f"[问卷] 生成LLM选项失败：问卷不存在，ID: {q_id}")
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    current_step = q.current_step
    question = next((q_item for q_item in STEP_QUESTIONS if q_item["step"] == current_step), None)
    
    if not question:
        logger.error(f"[问卷] 生成LLM选项失败：问题不存在，步骤: {current_step}")
        raise HTTPException(status_code=404, detail="Question not found")

    if not question.get("llm_enabled", False):
        logger.warning(f"[问卷] 当前问题不支持LLM生成选项，问题ID: {question['id']}")
        return LlmOptionsResponse(
            status="ok",
            questionnaire_id=q.id,
            step=current_step,
            question_id=question["id"],
            llm_options=question.get("options", []),
            suggestions={},
        )

    answers = dict(q.answers or {})
    logger.info(f"[问卷] 当前已填写答案: {answers}")
    
    llm_options, suggestions = _generate_llm_options_for_question(question, answers, db)
    
    llm_suggestions = q.llm_suggestions or {}
    llm_suggestions[question["id"]] = {
        "options": llm_options,
        "suggestions": suggestions,
    }
    q.llm_suggestions = llm_suggestions
    db.commit()
    db.refresh(q)
    
    logger.info(f"[问卷] LLM选项生成完成，问卷ID: {q_id}, 问题ID: {question['id']}, 生成选项数: {len(llm_options)}")

    return LlmOptionsResponse(
        status="ok",
        questionnaire_id=q.id,
        step=current_step,
        question_id=question["id"],
        llm_options=llm_options,
        suggestions=suggestions,
    )


@router.post("/{q_id}/answer-step", response_model=StepResponse)
async def answer_step(q_id: int, data: StepAnswer, db: Session = Depends(get_db)):
    """回答当前步骤，进入下一步"""
    logger.info(f"[问卷] 开始回答步骤，问卷ID: {q_id}, 问题ID: {data.question_id}, 答案: {data.answer}, 是否自定义: {data.is_custom}")
    
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        logger.error(f"[问卷] 问卷不存在，ID: {q_id}")
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if q.status == "completed" or q.status == "cancelled":
        logger.warning(f"[问卷] 问卷状态不允许回答，ID: {q_id}, 当前状态: {q.status}")
        raise HTTPException(status_code=400, detail="Questionnaire is already completed or cancelled")

    answers = dict(q.answers or {})
    
    if data.question_id == "novel_title":
        q.novel_title = data.answer
    
    answers[data.question_id] = data.answer
    q.answers = answers

    current_step = q.current_step
    question = next((q_item for q_item in STEP_QUESTIONS if q_item["step"] == current_step), None)
    
    if question and question["next_step"] >= 0:
        q.current_step = question["next_step"]
    else:
        q.current_step = current_step + 1

    db.commit()
    db.refresh(q)

    if q.current_step >= TOTAL_STEPS:
        q.status = "completed"
        db.commit()
        db.refresh(q)
        logger.info(f"[问卷] 问卷已完成，ID: {q_id}, 总答案数: {len(q.answers)}, 状态: {q.status}")
        return StepResponse(
            questionnaire_id=q.id,
            current_step=q.current_step,
            total_steps=TOTAL_STEPS,
            question=None,
            answers=q.answers,
            is_completed=True,
        )

    next_question = next((q_item for q_item in STEP_QUESTIONS if q_item["step"] == q.current_step), None)
    
    if next_question and next_question.get("llm_enabled", False):
        llm_suggestions = q.llm_suggestions or {}
        if next_question["id"] in llm_suggestions:
            next_question = next_question.copy()
            next_question["options"] = llm_suggestions[next_question["id"]].get("options", next_question.get("options", []))
        else:
            logger.info(f"[问卷] 自动为下一问题生成LLM选项，问题ID: {next_question['id']}")
            llm_options, suggestions = _generate_llm_options_for_question(next_question, dict(q.answers or {}), db)
            llm_suggestions[next_question["id"]] = {
                "options": llm_options,
                "suggestions": suggestions,
            }
            q.llm_suggestions = llm_suggestions
            db.commit()
            db.refresh(q)
            next_question = next_question.copy()
            next_question["options"] = llm_options

    logger.info(f"[问卷] 步骤回答成功，问卷ID: {q_id}, 当前步骤: {q.current_step}, 下一问题: {next_question['id'] if next_question else '无'}")
    return StepResponse(
        questionnaire_id=q.id,
        current_step=q.current_step,
        total_steps=TOTAL_STEPS,
        question=next_question,
        answers=q.answers,
        is_completed=False,
    )


@router.post("/{q_id}/skip-to-ai", response_model=AiCompleteResponse)
async def skip_to_ai(q_id: int, db: Session = Depends(get_db)):
    """跳过问卷，使用LLM补全除小说名以外的所有缺失设定，然后跳转到书名选择"""
    logger.info(f"[问卷] 用户请求AI一键补全，问卷ID: {q_id}")
    
    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        logger.error(f"[问卷] AI补全失败：问卷不存在，ID: {q_id}")
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    answers = dict(q.answers or {})
    logger.info(f"[问卷] 当前已填写答案: {answers}")
    
    ai_answers = _complete_with_ai(answers, db, skip_novel_title=True)
    logger.info(f"[问卷] AI补全结果: {ai_answers}")

    answers.update(ai_answers)
    q.answers = answers
    q.ai_completed_answers = ai_answers
    
    novel_title_step = next((q_item for q_item in STEP_QUESTIONS if q_item["id"] == "novel_title"), None)
    if novel_title_step:
        q.current_step = novel_title_step["step"]
        q.status = "in_progress"
    else:
        q.status = "ai_completed"
    
    db.commit()
    db.refresh(q)
    
    logger.info(f"[问卷] AI补全完成，问卷ID: {q_id}, 补全字段数: {len(ai_answers)}, 当前步骤: {q.current_step}, 状态: {q.status}")

    return AiCompleteResponse(
        status="ok",
        questionnaire_id=q.id,
        ai_answers=ai_answers,
        message="AI 已补全所有缺失设定，请选择小说名称",
    )


@router.post("/{q_id}/build-project", response_model=dict)
async def build_project_from_questionnaire(q_id: int, db: Session = Depends(get_db)):
    """
    根据问卷答案创建小说项目，并自动启动设定生成工作流

    将问卷答案中的信息自动填入项目设置：
    - 小说名称 → Project.title
    - 类型/基调/风格 → Project.writing_style
    - 每章字数 × 总章节数 → 总字数目标
    - 核心主题 → Theme
    - 主角/反派设定 → Character
    - 世界观/社会结构 → WorldEntry
    - 核心看点 → Theme (core_hook)

    创建项目后自动启动 bootstrap 工作流，生成完整设定文档
    """
    logger.info(f"[问卷] 开始根据问卷创建项目，问卷ID: {q_id}")
    
    from storage.models import Project, Theme, Character, WorldEntry, WorkflowRun

    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        logger.error(f"[问卷] 创建项目失败：问卷不存在，ID: {q_id}")
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    a = q.answers or {}
    ai_a = q.ai_completed_answers or {}
    all_answers = {**a, **ai_a}
    
    logger.info(f"[问卷] 用户答案: {a}")
    logger.info(f"[问卷] AI补全答案: {ai_a}")
    logger.info(f"[问卷] 合并后答案: {all_answers}")

    chapter_word_count = int(all_answers.get("chapter_word_count", 3000))
    total_chapters = int(all_answers.get("total_chapters", 30))
    est_total = chapter_word_count * total_chapters
    logger.info(f"[问卷] 篇幅估算：每章{chapter_word_count}字 × {total_chapters}章 = 总字数{est_total}")

    style_map = {
        "优美": "优美", "平实": "平实", "诗意": "诗意",
        "幽默": "幽默", "冷峻": "冷峻",
    }

    project_title = all_answers.get("novel_title", "") or all_answers.get("theme", "未命名小说")
    
    project = Project(
        title=project_title,
        description=all_answers.get("summary", "") or all_answers.get("world_setting", "") or all_answers.get("premise", ""),
        writing_style=style_map.get(all_answers.get("style", ""), "平实"),
        target_word_count=chapter_word_count,
        word_count_min=int(chapter_word_count * 0.7),
        word_count_max=int(chapter_word_count * 1.3),
        total_chapters=total_chapters,
        genre=all_answers.get("genre", ""),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info(f"[问卷] 项目创建成功，ID: {project.id}, 标题: {project.title}, 题材: {project.genre}, 风格: {project.writing_style}")

    theme_text = all_answers.get("theme", "")
    if theme_text:
        t = Theme(
            project_id=project.id,
            theme_type="core_theme",
            title=theme_text,
            description=f"基调：{all_answers.get('tone', '')}",
        )
        db.add(t)
        logger.info(f"[问卷] 创建主题记录，项目ID: {project.id}, 主题: {theme_text}")

    core_hook_text = all_answers.get("core_hook", "")
    if core_hook_text:
        h = Theme(
            project_id=project.id,
            theme_type="core_hook",
            title="核心看点",
            description=core_hook_text,
        )
        db.add(h)
        logger.info(f"[问卷] 创建核心看点记录，项目ID: {project.id}, 核心看点: {core_hook_text[:50]}...")

    protagonist_text = all_answers.get("protagonist", "")
    if protagonist_text:
        c = Character(
            project_id=project.id,
            name="主角",
            role="主角",
            description=protagonist_text,
        )
        db.add(c)
        logger.info(f"[问卷] 创建主角记录，项目ID: {project.id}, 主角描述: {protagonist_text[:50]}...")

    antagonist_text = all_answers.get("antagonist", "")
    if antagonist_text:
        c = Character(
            project_id=project.id,
            name="反派",
            role="反派",
            description=antagonist_text,
        )
        db.add(c)
        logger.info(f"[问卷] 创建反派记录，项目ID: {project.id}, 反派描述: {antagonist_text[:50]}...")

    world_setting_text = all_answers.get("world_setting", "")
    if world_setting_text:
        w = WorldEntry(
            project_id=project.id,
            category="世界观",
            title="世界设定",
            content=world_setting_text,
        )
        db.add(w)
        logger.info(f"[问卷] 创建世界观记录，项目ID: {project.id}, 世界观: {world_setting_text[:50]}...")

    society_structure_text = all_answers.get("society_structure", "")
    if society_structure_text:
        s = WorldEntry(
            project_id=project.id,
            category="社会结构",
            title="社会结构设定",
            content=society_structure_text,
        )
        db.add(s)
        logger.info(f"[问卷] 创建社会结构记录，项目ID: {project.id}, 社会结构: {society_structure_text[:50]}...")

    q.status = "completed"
    q.created_project_id = project.id
    db.commit()
    
    logger.info(f"[问卷] 项目创建流程完成，问卷ID: {q_id}, 项目ID: {project.id}, 问卷状态: {q.status}")

    # ─── 自动启动 bootstrap 工作流 ───
    logger.info(f"[问卷] 开始启动 bootstrap 工作流，项目ID: {project.id}")
    
    genre_str = all_answers.get("genre", "")
    if genre_str:
        genre_str = genre_str.split("/")[0].strip()
    
    user_filled = {
        "tone": all_answers.get("tone", ""),
        "chapter_word_count": all_answers.get("chapter_word_count", ""),
        "total_chapters": all_answers.get("total_chapters", ""),
        "protagonist": all_answers.get("protagonist", ""),
        "antagonist": all_answers.get("antagonist", ""),
        "world_setting": all_answers.get("world_setting", ""),
        "society_structure": all_answers.get("society_structure", ""),
        "pacing": all_answers.get("pacing", ""),
        "style": all_answers.get("style", ""),
        "core_hook": all_answers.get("core_hook", ""),
        "theme": all_answers.get("theme", ""),
        "summary": all_answers.get("summary", "") or all_answers.get("world_setting", ""),
    }
    
    user_filled = {k: v for k, v in user_filled.items() if v}
    
    from llm.workflow import plan_bootstrap_stages
    stages = plan_bootstrap_stages(
        required={
            "title": project_title,
            "chapter_word_count": chapter_word_count,
            "genre": genre_str,
            "description": project.description,
        },
        user_filled=user_filled,
    )

    run = WorkflowRun(
        project_id=project.id,
        name="bootstrap",
        stages=stages,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(f"[问卷] 创建 WorkflowRun，ID: {run.id}")

    from api.tasks import submit_llm_task
    from api.routes.projects import _run_bootstrap_task
    
    user_input = {
        "title": project_title,
        "chapter_word_count": chapter_word_count,
        "genre": genre_str,
        "description": project.description,
        "_project_id": project.id,
        "auto_commit": True,
        **user_filled,
    }
    
    submit_llm_task(
        task_type="bootstrap",
        llm_call_fn=_run_bootstrap_task,
        project_id=project.id,
        description=f"项目引导补全 [{project_title}]",
        run_id=run.id,
        user_input=user_input,
    )
    
    logger.info(f"[问卷] bootstrap 工作流已提交执行，项目ID: {project.id}, run_id: {run.id}")

    return {
        "project_id": project.id,
        "project_title": project.title,
        "run_id": run.id,
        "message": "项目创建成功，正在自动生成设定文档...",
    }


# ─── Helpers ───

def _get_default_answers(missing_fields: list) -> dict:
    """当LLM不可用时，返回默认的补全答案"""
    defaults = {
        "genre": "玄幻",
        "theme": "成长与自我发现",
        "tone": "热血",
        "chapter_word_count": "3000",
        "total_chapters": "50",
        "protagonist": "一个平凡的少年，意外获得神秘力量，踏上冒险之旅，逐渐成长为英雄。他性格坚韧，重情重义，在面对困难时从不退缩。",
        "premise": "在一个充满魔法和奇幻生物的世界，古老的预言正在苏醒。不同种族之间的矛盾日益加剧，而主角的命运将决定整个世界的走向。",
        "style": "优美",
        "pacing": "中等节奏",
        "core_hook": "独特的世界观设定和引人入胜的剧情反转",
        "antagonist": "一个强大的反派，他的动机与主角形成鲜明对比，代表着故事中需要被克服的黑暗面。",
        "world_setting": "一个充满神秘和奇幻色彩的世界，有着独特的规则和历史。",
        "society_structure": "等级森严的社会结构，底层人民渴望改变现状。",
        "novel_title": "未命名小说",
    }
    return {k: defaults[k] for k in missing_fields if k in defaults}


def _generate_llm_options_for_question(question: dict, answers: dict, db) -> tuple:
    """使用LLM为特定问题生成选项"""
    logger.info(f"[问卷] 开始为问题生成LLM选项，问题ID: {question['id']}, 当前答案: {answers}")
    
    from llm.factory import LLMFactory

    try:
        llm = LLMFactory.create(db=db)
        logger.info(f"[问卷] LLM实例创建成功")
    except ValueError as e:
        logger.warning(f"[问卷] LLM创建失败，使用默认选项: {e}")
        return question.get("options", []), {}

    question_id = question["id"]
    question_text = question["question"]
    
    context_text = "\n".join([f"- {k}: {v}" for k, v in answers.items() if v])
    
    if question_id == "novel_title":
        prompt = f"""
你是一位专业的小说编辑和创意顾问。用户已经完成了小说创作问卷的大部分内容，现在需要为小说命名。

用户已填写的设定：
{context_text}

请根据以上设定，生成3个合适的小说名称选项。

要求：
1. 每个名称要贴合小说的题材、主题和核心看点
2. 名称要吸引人，有创意，适合作为小说标题
3. 名称要简洁，一般不超过8个字

请输出 JSON 格式，包含 options 数组。示例格式：
{{
  "options": [
    {{"value": "书名1", "label": "书名1", "description": "这个书名的含义和亮点"}},
    {{"value": "书名2", "label": "书名2", "description": "这个书名的含义和亮点"}},
    {{"value": "书名3", "label": "书名3", "description": "这个书名的含义和亮点"}}
  ],
  "suggestions": {{}}
}}
"""
    else:
        prompt = f"""
你是一位专业的小说编辑和创意顾问。用户正在填写一份小说创作问卷。
请根据用户已填写的答案，为当前问题生成3个具体的选项。

用户已填写的答案：
{context_text}

当前问题：{question_text}

问题ID：{question_id}

请为这个问题生成3个选项，每个选项包含：
- value: 选项值（简短标识）
- label: 选项标签（显示给用户的名称）
- description: 选项描述（详细说明这个选项的含义）

选项应该：
1. 基于用户已填写的答案，保持一致性
2. 提供多样化的选择，帮助用户进一步明确设定
3. 描述要具体，有创意

请输出 JSON 格式，包含 options 数组和 suggestions 对象（可选，提供额外建议）。
示例格式：
{{
  "options": [
    {{"value": "option1", "label": "选项1", "description": "选项1的详细描述"}},
    {{"value": "option2", "label": "选项2", "description": "选项2的详细描述"}},
    {{"value": "option3", "label": "选项3", "description": "选项3的详细描述"}}
  ],
  "suggestions": {{}}
}}
"""

    system_prompt = "你是一位专业的小说编辑和创意顾问，擅长根据已有信息生成有创意的小说设定选项。"

    try:
        logger.info(f"[问卷] 开始调用LLM生成选项，问题ID: {question_id}")
        response = llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.7,
            task_type="questionnaire_llm_options",
        )
        logger.info(f"[问卷] LLM调用完成，响应内容: {response[:200]}..." if len(response) > 200 else f"[问卷] LLM调用完成，响应内容: {response}")

        try:
            import json
            import re
            clean_response = response.strip()
            if clean_response.startswith('```'):
                clean_response = re.sub(r'^```json\s*', '', clean_response)
                clean_response = re.sub(r'\s*```$', '', clean_response)
            clean_response = clean_response.strip()
            clean_response = re.sub(r',\s*]', ']', clean_response)
            clean_response = re.sub(r',\s*}', '}', clean_response)
            result = json.loads(clean_response)
            options = result.get("options", question.get("options", []))
            suggestions = result.get("suggestions", {})
            logger.info(f"[问卷] LLM选项生成成功，选项数: {len(options)}")
            return options, suggestions
        except Exception as e:
            logger.error(f"[问卷] LLM选项JSON解析失败: {e}, 原始响应: {clean_response[:300]}...")
            return question.get("options", []), {}
    except Exception as e:
        logger.error(f"[问卷] LLM选项生成失败: {e}")
        return question.get("options", []), {}


def _complete_with_ai(answers: dict, db, skip_novel_title: bool = False) -> dict:
    """使用 LLM 补全缺失的设定"""
    logger.info(f"[问卷] 开始AI补全，已填写答案: {answers}, skip_novel_title: {skip_novel_title}")
    
    from llm.factory import LLMFactory
    from llm.roles import build_bootstrap_role

    missing_fields = []
    for q in STEP_QUESTIONS:
        if q["id"] not in answers or not answers[q["id"]]:
            missing_fields.append(q["id"])

    if skip_novel_title and "novel_title" in missing_fields:
        missing_fields.remove("novel_title")

    logger.info(f"[问卷] 需要补全的字段: {missing_fields}")
    
    if not missing_fields:
        logger.info(f"[问卷] 没有需要补全的字段，直接返回")
        return {}

    try:
        llm = LLMFactory.create(db=db)
        logger.info(f"[问卷] LLM实例创建成功")
    except ValueError as e:
        logger.warning(f"[问卷] LLM创建失败，使用默认答案补全: {e}")
        return _get_default_answers(missing_fields)

    if "novel_title" in missing_fields:
        other_fields = [f for f in missing_fields if f != "novel_title"]
        if other_fields:
            task_description = f"""
你是一位专业的小说编辑和创意顾问。用户正在填写一份小说创作问卷，但跳过了一些问题。
请根据用户已填写的答案，为缺失的问题生成合理的设定。

用户已填写的答案：
{answers}

需要补全的字段（除小说名外）：{other_fields}

请根据以下规则补全：
1. genre（题材）：从 玄幻/都市/科幻/武侠/仙侠/历史/悬疑/现实主义/奇幻 中选择，可多选，用逗号分隔（如：玄幻,仙侠）
2. core_hook（核心看点）：小说最吸引人的核心亮点
3. theme（主题）：一句话核心主题，如 救赎、成长、复仇等
4. tone（基调）：从 热血/深沉/轻松/黑暗/治愈/史诗/悬疑紧张/浪漫/幽默/冷峻 中选择
5. chapter_word_count（每章字数）：从 2000/3000/5000/8000/10000 中选择一个数字
6. total_chapters（总章节数）：从 30/50/100/150 中选择一个数字
7. protagonist（主角）：描述主角的性格、目标、背景（3-5句话）
8. antagonist（反派）：描述反派的动机、背景和与主角的矛盾（2-3句话）
9. world_setting（世界观）：描述故事发生的世界、时代、社会规则（3-5句话）
10. society_structure（社会结构）：描述社会的组织形式、权力结构、价值观（2-3句话）
11. style（风格）：从 优美/平实/诗意/幽默/冷峻 中选择
12. pacing（节奏）：从 快节奏/中等节奏/慢热型/起伏型 中选择

请输出 JSON 格式，只包含需要补全的字段，不要包含 novel_title。
"""

            system_prompt = "你是一位专业的小说编辑和创意顾问，擅长根据部分信息补全完整的小说设定。"

            try:
                logger.info(f"[问卷] 开始调用LLM生成补全内容（除小说名外）")
                response = llm.generate(
                    prompt=task_description,
                    system_prompt=system_prompt,
                    max_tokens=2048,
                    temperature=0.5,
                    task_type="questionnaire_ai_complete",
                )
                logger.info(f"[问卷] LLM调用完成，响应内容: {response[:200]}..." if len(response) > 200 else f"[问卷] LLM调用完成，响应内容: {response}")

                try:
                    import json
                    result = json.loads(response)
                    logger.info(f"[问卷] AI补全JSON解析成功，结果: {result}")
                except Exception as e:
                    logger.error(f"[问卷] AI补全JSON解析失败: {e}, 原始响应: {response}")
                    result = _get_default_answers(other_fields)
            except Exception as e:
                logger.error(f"[问卷] AI补全LLM调用失败: {e}")
                result = _get_default_answers(other_fields)

            combined_answers = {**answers, **result}
            context_text = "\n".join([f"- {k}: {v}" for k, v in combined_answers.items() if v])
            
            title_prompt = f"""
你是一位专业的小说编辑和创意顾问。用户已经完成了小说创作问卷的大部分内容，现在需要为小说命名。

用户已填写的设定：
{context_text}

请根据以上设定，生成一个合适的小说名称。

要求：
1. 名称要贴合小说的题材、主题和核心看点
2. 名称要吸引人，有创意，适合作为小说标题
3. 名称要简洁，一般不超过8个字

请直接输出小说名称，不要包含其他内容。
"""

            system_prompt = "你是一位专业的小说编辑，擅长为小说起吸引人的标题。"

            try:
                logger.info(f"[问卷] 开始调用LLM生成小说名称")
                title_response = llm.generate(
                    prompt=title_prompt,
                    system_prompt=system_prompt,
                    max_tokens=128,
                    temperature=0.7,
                    task_type="questionnaire_generate_title",
                )
                title = title_response.strip().strip('"').strip("'")
                logger.info(f"[问卷] 小说名称生成成功: {title}")
                result["novel_title"] = title
            except Exception as e:
                logger.error(f"[问卷] 小说名称生成失败: {e}")
                result["novel_title"] = "未命名小说"
            
            return result
        else:
            context_text = "\n".join([f"- {k}: {v}" for k, v in answers.items() if v])
            
            title_prompt = f"""
你是一位专业的小说编辑和创意顾问。用户已经完成了小说创作问卷的大部分内容，现在需要为小说命名。

用户已填写的设定：
{context_text}

请根据以上设定，生成一个合适的小说名称。

要求：
1. 名称要贴合小说的题材、主题和核心看点
2. 名称要吸引人，有创意，适合作为小说标题
3. 名称要简洁，一般不超过8个字

请直接输出小说名称，不要包含其他内容。
"""

            system_prompt = "你是一位专业的小说编辑，擅长为小说起吸引人的标题。"

            try:
                logger.info(f"[问卷] 开始调用LLM生成小说名称")
                title_response = llm.generate(
                    prompt=title_prompt,
                    system_prompt=system_prompt,
                    max_tokens=128,
                    temperature=0.7,
                    task_type="questionnaire_generate_title",
                )
                title = title_response.strip().strip('"').strip("'")
                logger.info(f"[问卷] 小说名称生成成功: {title}")
                return {"novel_title": title}
            except Exception as e:
                logger.error(f"[问卷] 小说名称生成失败: {e}")
                return {"novel_title": "未命名小说"}
    else:
        task_description = f"""
你是一位专业的小说编辑和创意顾问。用户正在填写一份小说创作问卷，但跳过了一些问题。
请根据用户已填写的答案，为缺失的问题生成合理的设定。

用户已填写的答案：
{answers}

需要补全的字段：{missing_fields}

请根据以下规则补全：
1. genre（题材）：从 玄幻/都市/科幻/武侠/仙侠/历史/悬疑/现实主义/奇幻 中选择，可多选，用逗号分隔（如：玄幻,仙侠）
2. core_hook（核心看点）：小说最吸引人的核心亮点
3. theme（主题）：一句话核心主题，如 救赎、成长、复仇等
4. tone（基调）：从 热血/深沉/轻松/黑暗/治愈/史诗/悬疑紧张/浪漫/幽默/冷峻 中选择
5. chapter_word_count（每章字数）：从 2000/3000/5000/8000/10000 中选择一个数字
6. total_chapters（总章节数）：从 30/50/100/150 中选择一个数字
7. protagonist（主角）：描述主角的性格、目标、背景（3-5句话）
8. antagonist（反派）：描述反派的动机、背景和与主角的矛盾（2-3句话）
9. world_setting（世界观）：描述故事发生的世界、时代、社会规则（3-5句话）
10. society_structure（社会结构）：描述社会的组织形式、权力结构、价值观（2-3句话）
11. style（风格）：从 优美/平实/诗意/幽默/冷峻 中选择
12. pacing（节奏）：从 快节奏/中等节奏/慢热型/起伏型 中选择

请输出 JSON 格式，只包含需要补全的字段。
"""

        system_prompt = "你是一位专业的小说编辑和创意顾问，擅长根据部分信息补全完整的小说设定。"

        try:
            logger.info(f"[问卷] 开始调用LLM生成补全内容")
            response = llm.generate(
                prompt=task_description,
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.5,
                task_type="questionnaire_ai_complete",
            )
            logger.info(f"[问卷] LLM调用完成，响应内容: {response[:200]}..." if len(response) > 200 else f"[问卷] LLM调用完成，响应内容: {response}")

            try:
                import json
                result = json.loads(response)
                logger.info(f"[问卷] AI补全JSON解析成功，结果: {result}")
                return result
            except Exception as e:
                logger.error(f"[问卷] AI补全JSON解析失败: {e}, 原始响应: {response}")
                return _get_default_answers(missing_fields)
        except Exception as e:
            logger.error(f"[问卷] AI补全LLM调用失败: {e}")
            return _get_default_answers(missing_fields)

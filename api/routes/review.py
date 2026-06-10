"""评审 API - 支持同步/异步双模式"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import ReviewSession, Chapter, Project
from llm.factory import LLMFactory
from llm.roles import get_role
from api.tasks import submit_llm_task, get_task
from logger import logger, log_llm_call
import time
import json


router = APIRouter(prefix="/api/reviews", tags=["评审"])


# ─── Schemas ───

class ReviewCreate(BaseModel):
    project_id: int
    chapter_id: int | None = None
    session_type: str = "chapter"
    content_reviewed: str = ""


class ReviewSubmitResponse(BaseModel):
    task_id: str | None = None
    status: str  # "submitted" / "completed" / "error"
    session_id: int | None = None
    error: str | None = None


# ─── 同步评审函数 ───

def _do_review(project_id: int, chapter_id: int | None, session_type: str, db: Session) -> dict:
    """执行同步评审"""
    start = time.time()

    # 获取内容
    if chapter_id:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise ValueError("Chapter not found")
        content = chapter.content
        title = chapter.title
    else:
        content = ""
        title = "独立文本"

    project = db.query(Project).filter(Project.id == project_id).first()

    # 字数合规评分
    wc = len(content.replace(" ", "").replace("\n", ""))
    wc_score = 10.0
    if project and project.target_word_count:
        diff = abs(wc - project.target_word_count) / project.target_word_count
        wc_score = max(0, round(10 - diff * 20, 1))

    # 构建 Role
    role = get_role("review")
    ctx = {
        "title": title,
        "content": content[:8000],
    }
    system_prompt = role.build_system(ctx)
    user_prompt = role.user_prompt_template.format(title=title, content=content[:8000])

    logger.info(f"[Review] starting review for project={project_id} chapter={chapter_id}")

    try:
        llm = LLMFactory.create(db=db)
        raw = llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=role.max_tokens,
            temperature=role.temperature,
            task_type=f"review_{session_type}",  # 入 log 时按 review 类型分类
        )
        duration_ms = (time.time() - start) * 1000
        log_llm_call(llm.provider_name, getattr(llm, "model", "unknown"), "review", duration_ms, True)

        # 解析 JSON
        import re
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            scores = result.get("scores", {})
            critique = result.get("critique", "")
            suggestions = result.get("suggestions", [])
        else:
            scores = {}
            critique = raw
            suggestions = []

    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_llm_call("unknown", "unknown", "review", duration_ms, False, str(e))
        raise

    overall = round(sum(scores.values()) / len(scores), 1) if scores else 0.0

    # 保存评审会话
    session = ReviewSession(
        project_id=project_id,
        chapter_id=chapter_id,
        session_type=session_type,
        content_reviewed=content[:2000],
        score_consistency=scores.get("consistency", 0.0),
        score_pacing=scores.get("pacing", 0.0),
        score_style=scores.get("style", 0.0),
        score_ai_removal=scores.get("ai_removal", 0.0),
        score_word_count=wc_score,
        score_foreshadowing=scores.get("foreshadowing", 0.0),
        score_character_arc=scores.get("character_arc", 0.0),
        score_thematic=scores.get("thematic", 0.0),
        overall_score=overall,
        critique=critique,
        suggestions=suggestions,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    logger.info(f"[Review] session={session.id} completed score={overall} in {duration_ms:.0f}ms")

    return {
        "session_id": session.id,
        "overall_score": overall,
        "scores": scores,
        "critique": critique,
        "suggestions": suggestions,
        "score_word_count": wc_score,
        "duration_ms": duration_ms,
    }


# ─── 异步任务函数 ───

def _async_review_task(task_id: str, project_id: int, chapter_id: int | None, session_type: str):
    from storage.database import SessionLocal
    db = SessionLocal()
    try:
        task = get_task(task_id)
        result = _do_review(project_id, chapter_id, session_type, db)
        task.result = result
        task.status = "completed"
        task.progress = 100
        task.completed_at = time.time()
        logger.info(f"[AsyncReview] task_id={task_id} session_id={result['session_id']}")
    except Exception as e:
        task = get_task(task_id)
        if task:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
        logger.error(f"[AsyncReview] task_id={task_id} failed: {e}")
    finally:
        db.close()


# ─── Routes ───

@router.post("", response_model=ReviewSubmitResponse)
async def create_review(
    data: ReviewCreate,
    background_tasks: BackgroundTasks,
):
    """提交评审任务（异步：立即返回 task_id，前端轮询 /api/tasks/{task_id}）"""
    task = submit_llm_task(
        task_type="review",
        llm_call_fn=_async_review_task,
        project_id=data.project_id,
        description=f"评审 chapter_id={data.chapter_id}",
        chapter_id=data.chapter_id,
        session_type=data.session_type,
    )
    return ReviewSubmitResponse(task_id=task.id, status="submitted")


@router.get("/{review_id}", response_model=dict)
async def get_review_result(review_id: int, project_id: int, db: Session = Depends(get_db)):
    """获取评审结果（带项目隔离）"""
    session = db.query(ReviewSession).filter(
        ReviewSession.id == review_id,
        ReviewSession.project_id == project_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "id": session.id,
        "project_id": session.project_id,
        "chapter_id": session.chapter_id,
        "score_consistency": session.score_consistency,
        "score_pacing": session.score_pacing,
        "score_style": session.score_style,
        "score_ai_removal": session.score_ai_removal,
        "score_word_count": session.score_word_count,
        "score_foreshadowing": session.score_foreshadowing,
        "score_character_arc": session.score_character_arc,
        "score_thematic": session.score_thematic,
        "overall_score": session.overall_score,
        "critique": session.critique,
        "suggestions": session.suggestions or [],
        "revised": session.revised,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.post("/{review_id}/revise", response_model=dict)
async def revise_review(review_id: int, project_id: int, db: Session = Depends(get_db)):
    """根据评审意见修订章节"""
    session = db.query(ReviewSession).filter(
        ReviewSession.id == review_id,
        ReviewSession.project_id == project_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Review not found")
    if not session.chapter_id:
        raise HTTPException(status_code=400, detail="仅有章节评审支持修订")
    chapter = db.query(Chapter).filter(
        Chapter.id == session.chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return {"status": "pending_revision", "review_id": review_id, "chapter_id": chapter.id}


@router.get("/project/{project_id}", response_model=list[dict])
async def list_reviews(project_id: int, chapter_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(ReviewSession).filter(ReviewSession.project_id == project_id)
    if chapter_id:
        query = query.filter(ReviewSession.chapter_id == chapter_id)
    sessions = query.order_by(ReviewSession.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "chapter_id": s.chapter_id,
            "overall_score": s.overall_score,
            "revised": s.revised,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]

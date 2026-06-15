"""批量章节生成 API"""
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project
from logger import logger


router = APIRouter(prefix="/api/chapters", tags=["批量生成"])


class BatchGenerateRequest(BaseModel):
    project_id: int
    start_chapter: int = Field(..., ge=0, description="从第几章之后开始（即 start_chapter 为已存在的最后一章序号，0表示从第1章开始）")
    count: int = Field(..., ge=1, le=100, description="要生成的章节数量")
    provider: str | None = None
    auto_revise: bool = True
    revision_threshold: float = 6.5
    guide: str = ""


class BatchGenerateResponse(BaseModel):
    status: str
    task_id: str | None = None
    chapters_to_generate: int = 0
    start_from: int = 0
    end_at: int = 0


@router.post("/batch-generate", response_model=BatchGenerateResponse)
async def batch_generate(req: BatchGenerateRequest, db: Session = Depends(get_db)):
    """
    批量生成章节：从 start_chapter 之后开始，连续生成 count 章。
    每章走完整的 9 步流水线，按顺序串行执行。
    """
    from api.tasks import submit_llm_task

    # 校验项目存在
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    # 计算要生成的章节范围（1-based 序号）
    start_order = req.start_chapter       # 0-based order
    end_order = req.start_chapter + req.count - 1

    task = submit_llm_task(
        task_type="batch_pipeline",
        llm_call_fn=_async_batch_pipeline_task,
        project_id=req.project_id,
        description=f"批量生成 {req.count} 章 (第{start_order + 1}~第{end_order + 1}章)",
        req=req,
        start_order=start_order,
        end_order=end_order,
    )

    return BatchGenerateResponse(
        status="submitted",
        task_id=task.id,
        chapters_to_generate=req.count,
        start_from=start_order + 1,
        end_at=end_order + 1,
    )


def _async_batch_pipeline_task(
    task_id: str, req: BatchGenerateRequest, start_order: int, end_order: int
):
    """
    批量生成异步任务：按顺序创建章节 → 串行运行 9 步流水线 → 后处理。
    每章完成后更新 task 进度，让前端能实时看到当前执行到第几章。
    """
    from storage.database import SessionLocal
    from storage.models import Chapter
    from llm.chapter_pipeline import run_chapter_generation_pipeline, PIPELINE_STAGES_META
    from api.tasks import get_task

    db = SessionLocal()
    try:
        task = get_task(task_id)
        total_chapters = end_order - start_order + 1

        # 初始化 task result：展示批量进度结构
        if task is not None:
            task.result = {
                "batch": True,
                "total_chapters": total_chapters,
                "completed_chapters": 0,
                "current_chapter_index": 0,
                "current_chapter_order": start_order + 1,
                "chapters_status": {},
                "current_pipeline_stages": {
                    m["id"]: {
                        "id": m["id"],
                        "label": m["label"],
                        "weight": m["weight"],
                        "status": "pending",
                        "duration_ms": None,
                    }
                    for m in PIPELINE_STAGES_META
                },
                "current_pipeline_progress_pct": 0,
            }
            task.progress = 1

        failed_chapters = []

        for idx, chapter_order in enumerate(range(start_order, end_order + 1)):
            chapter_num = chapter_order + 1  # 1-based 显示序号

            # 更新当前章节信息
            if task is not None:
                r = dict(task.result or {})
                r["current_chapter_index"] = idx
                r["current_chapter_order"] = chapter_num
                # 重置当前章节的流水线状态
                r["current_pipeline_stages"] = {
                    m["id"]: {
                        "id": m["id"],
                        "label": m["label"],
                        "weight": m["weight"],
                        "status": "pending",
                        "duration_ms": None,
                    }
                    for m in PIPELINE_STAGES_META
                }
                r["current_pipeline_progress_pct"] = 0
                task.result = r
                task.progress = max(task.progress or 0, int((idx / total_chapters) * 95))

            # 1) 创建章节（如果不存在）
            chapter = db.query(Chapter).filter(
                Chapter.project_id == req.project_id,
                Chapter.order == chapter_order,
            ).first()

            if not chapter:
                chapter = Chapter(
                    project_id=req.project_id,
                    title=f"第{chapter_num}章",
                    order=chapter_order,
                    content="",
                    word_count=0,
                )
                db.add(chapter)
                db.commit()
                db.refresh(chapter)
                logger.info(f"[BatchGen] Created chapter {chapter_num} (id={chapter.id})")

            # 标记章节开始
            if task is not None:
                r = dict(task.result or {})
                cs = dict(r.get("chapters_status") or {})
                cs[str(chapter_num)] = {
                    "chapter_id": chapter.id,
                    "status": "running",
                    "started_at": time.time(),
                }
                r["chapters_status"] = cs
                task.result = r

            # 2) 章节进度回调
            def _make_progress_cb(ch_order):
                def _on_progress(stage_id: str, status: str, info: dict):
                    t = get_task(task_id)
                    if t is None:
                        return
                    r = dict(t.result or {})
                    stages = dict(r.get("current_pipeline_stages") or {})
                    entry = dict(stages.get(stage_id) or {"id": stage_id})
                    entry["status"] = status
                    for k in ("duration_ms", "label", "error", "score"):
                        if k in info:
                            entry[k] = info[k]
                    stages[stage_id] = entry
                    r["current_pipeline_stages"] = stages
                    r["current_pipeline_progress_pct"] = info.get(
                        "progress_pct", r.get("current_pipeline_progress_pct", 0)
                    )
                    t.result = r
                return _on_progress

            # 3) 运行完整 9 步流水线
            try:
                pipeline_result = run_chapter_generation_pipeline(
                    db=db,
                    project_id=req.project_id,
                    chapter_id=chapter.id,
                    provider=req.provider,
                    auto_revise=req.auto_revise,
                    revision_threshold=req.revision_threshold,
                    progress_cb=_make_progress_cb(chapter_order),
                    guide=req.guide,
                )

                # 标记章节完成
                if task is not None:
                    r = dict(task.result or {})
                    cs = dict(r.get("chapters_status") or {})
                    ch_status = dict(cs.get(str(chapter_num), {}))
                    ch_status["status"] = "completed"
                    ch_status["completed_at"] = time.time()
                    ch_status["word_count"] = pipeline_result.get("final_word_count", 0)
                    cs[str(chapter_num)] = ch_status
                    r["chapters_status"] = cs
                    r["completed_chapters"] = idx + 1
                    task.result = r
                    task.progress = max(
                        task.progress or 0,
                        int(((idx + 1) / total_chapters) * 95),
                    )

                logger.info(
                    f"[BatchGen] Chapter {chapter_num} completed, "
                    f"words={pipeline_result.get('final_word_count', 0)}"
                )

            except Exception as e:
                logger.error(f"[BatchGen] Chapter {chapter_num} failed: {e}")
                failed_chapters.append(chapter_num)
                if task is not None:
                    r = dict(task.result or {})
                    cs = dict(r.get("chapters_status") or {})
                    ch_status = dict(cs.get(str(chapter_num), {}))
                    ch_status["status"] = "failed"
                    ch_status["error"] = str(e)
                    cs[str(chapter_num)] = ch_status
                    r["chapters_status"] = cs
                    r["completed_chapters"] = idx + 1
                    task.result = r
                # 失败后继续下一章，不中断整个批量任务

        # 批量任务完成
        if task is not None:
            r = dict(task.result or {})
            r["status"] = "completed" if not failed_chapters else "completed_with_errors"
            r["failed_chapters"] = failed_chapters
            task.result = r
            task.progress = 100
            task.status = "completed"
            task.completed_at = time.time()

        logger.info(
            f"[BatchGen] Batch done: {total_chapters - len(failed_chapters)}/{total_chapters} succeeded"
        )

    except Exception as e:
        logger.error(f"[BatchGen] Batch task failed: {e}")
        task = get_task(task_id)
        if task is not None:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
    finally:
        db.close()

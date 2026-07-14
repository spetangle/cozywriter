"""章节管理 API - 严格项目隔离"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Chapter, ChapterVersion, Project
import re
from logger import logger



router = APIRouter(prefix="/api", tags=["章节"])


# ─── Schemas ───

class ChapterCreate(BaseModel):
    # 修复：project_id 改为可选（从 URL 路径中取，避免 422）
    # 之前这里必填， 但前端只发 {title, order}，后端验证 project_id 缺失 → 422
    project_id: str | None = None
    title: str
    order: int = 0
    content: str = ""
    synopsis: str = ""


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    synopsis: str | None = None
    order: int | None = None


class ChapterResponse(BaseModel):
    id: int
    project_id: str
    title: str
    order: int
    content: str
    word_count: int
    synopsis: str
    fingerprint: dict = None
    created_at: object
    updated_at: object

    class Config:
        from_attributes = True
        json_encoders = {
            type(None): lambda v: None,
        }


class VersionResponse(BaseModel):
    id: int
    chapter_id: int
    content: str
    version_num: int
    created_at: object

    class Config:
        from_attributes = True


# ─── 隔离辅助 ───

def _verify_chapter(chapter_id: int, project_id: str, db: Session) -> Chapter:
    """验证章节属于指定项目，不属于则抛出 404"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


def _count_words(text: str) -> int:
    chinese = len(re.findall(r'[一-鿿]', text))
    english = len(re.findall(r'[a-zA-Z]+', text))
    return chinese + english


# ─── Routes ───

@router.get("/projects/{project_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(project_id: str, db: Session = Depends(get_db)):
    """获取项目下所有章节"""
    chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.order)
        .all()
    )
    return chapters


@router.post("/projects/{project_id}/chapters", response_model=ChapterResponse)
async def create_chapter(project_id: str, data: ChapterCreate, db: Session = Depends(get_db)):
    """创建章节

    如果 bootstrap 已生成过该项目大纲的 chapter_outlines，会按 order 自动取对应的细纲，
    写入 ChapterOutline 表（含标题、核心内容、剧情推进等）。标题也会用 LLM 生成的标题。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    word_count = _count_words(data.content)

    # 自动从 bootstrap 拉取匹配的章节细纲 + 标题
    bootstrap_title = None
    bootstrap_outline_fields = None
    try:
        from storage.models import WorkflowRun, ChapterOutline
        from llm.workflow import _commit_bootstrap_results  # noqa: F401  仅确保模块加载
        latest_run = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.project_id == project_id)
            .order_by(WorkflowRun.created_at.desc())
            .first()
        )
        if latest_run:
            outline_data = (latest_run.stage_results or {}).get("stage_4a_outline", {}).get("data", {})
            chap_list = outline_data.get("chapter_outlines", []) if isinstance(outline_data, dict) else []
            # 按 chapter_num == order+1 匹配
            target_chap = next(
                (c for c in chap_list if c.get("chapter_num") == data.order + 1),
                None,
            )
            if target_chap:
                t = (target_chap.get("title") or "").strip()
                if t and not re.match(r'^第\s*[0-9一二三四五六七八九十百千]+\s*章\s*$', t):
                    bootstrap_title = t
                bootstrap_outline_fields = {
                    "chapter_position": target_chap.get("chapter_position", ""),
                    "pacing": target_chap.get("pacing", "平稳"),
                    "key_content": target_chap.get("key_content", ""),
                    "plot_advance": target_chap.get("plot_advance", ""),
                    "highlights": target_chap.get("highlights", []),
                    "target_word_count": target_chap.get("target_word_count", project.target_word_count or 3000),
                }
    except Exception as e:
        logger.debug(f"[create_chapter] bootstrap outline lookup failed: {e}")

    # 如果 bootstrap 没生成标题，就用调用方传入的（前端默认「第 N 章」）
    final_title = bootstrap_title or data.title

    chapter = Chapter(
        project_id=project_id,
        title=final_title,
        order=data.order,
        content=data.content,
        synopsis=data.synopsis,
        word_count=word_count,
    )
    db.add(chapter)
    db.flush()  # 拿到 id，下面写细纲要用

    # 写入从 bootstrap 拉到的细纲（如果有）
    if bootstrap_outline_fields:
        try:
            outline_row = ChapterOutline(
                chapter_id=chapter.id,
                status="completed",
                **bootstrap_outline_fields,
            )
            db.add(outline_row)
            logger.info(
                f"[create_chapter] 自动从 bootstrap 写入章节 {chapter.id} 的细纲"
                f"（title={final_title}, key_content={len(bootstrap_outline_fields['key_content'])}字）"
            )
        except Exception as e:
            logger.warning(f"[create_chapter] 写入 bootstrap 细纲失败: {e}")

    db.commit()
    db.refresh(chapter)
    return chapter


# ─── 跨项目隔离：chapter_id 必须带 project_id 验证 ───

@router.get("/projects/{project_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节详情（带项目隔离验证）"""
    chapter = _verify_chapter(chapter_id, project_id, db)
    return chapter


@router.get("/projects/{project_id}/chapters/{chapter_id}/fingerprint")
async def get_chapter_fingerprint(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节指纹信息（单独端点，避免每次切换章节传输大量数据）"""
    chapter = _verify_chapter(chapter_id, project_id, db)
    return {"fingerprint": chapter.fingerprint or {}}


@router.put("/projects/{project_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(project_id: str, chapter_id: int, data: ChapterUpdate, db: Session = Depends(get_db)):
    """更新章节（自动创建版本快照）"""
    chapter = _verify_chapter(chapter_id, project_id, db)

    last_version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .first()
    )
    next_version_num = (last_version.version_num + 1) if last_version else 1
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        version_num=next_version_num,
    )
    db.add(version)

    content_changed = False
    if data.title is not None:
        chapter.title = data.title
    if data.synopsis is not None:
        chapter.synopsis = data.synopsis
    if data.order is not None:
        chapter.order = data.order
    if data.content is not None:
        chapter.content = data.content
        chapter.word_count = _count_words(data.content)
        content_changed = True

    db.commit()
    db.refresh(chapter)

    # 若正文变了 → 触发 RAG chapter_events 集合重新索引（失败仅 warning，不影响保存）
    if content_changed:
        try:
            from rag.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            kb.add_chapter_event(chapter)
            logger.info(f"[update_chapter] RAG chapter_events 已重新索引 (chapter {chapter_id})")
        except Exception as rag_err:
            logger.warning(f"[update_chapter] RAG 重新索引失败 (chapter {chapter_id}): {rag_err}")

    return chapter


@router.delete("/projects/{project_id}/chapters/{chapter_id}")
async def delete_chapter(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """删除单个章节

    同步清理:
      - ChapterVersion (章节版本快照)
      - ChapterOutline (细纲)
      - ReviewSession (评审记录)
      - ConsistencyRecord (一致性记录)
      - RAG chapter_events 索引
    """
    from storage.models import ChapterVersion, ChapterOutline, ReviewSession, ConsistencyRecord
    chapter = _verify_chapter(chapter_id, project_id, db)

    # 1. 删 ChapterVersion
    versions_count = db.query(ChapterVersion).filter(ChapterVersion.chapter_id == chapter_id).delete()
    # 2. 删 ChapterOutline
    outline_count = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).delete()
    # 3. 删 ReviewSession
    review_count = db.query(ReviewSession).filter(ReviewSession.chapter_id == chapter_id).delete()
    # 4. 删 ConsistencyRecord
    consistency_count = db.query(ConsistencyRecord).filter(
        ConsistencyRecord.chapter_id == chapter_id
    ).delete()
    # 5. 删 Chapter 本身(级联删 versions 等,但我们已经显式删了避免依赖)
    db.delete(chapter)
    db.commit()

    # 6. 同步从 RAG 清理
    rag_ok = True
    try:
        from rag.knowledge_base import KnowledgeBase
        KnowledgeBase().delete_chapter_event(chapter_id)
    except Exception as rag_err:
        logger.warning(f"[delete_chapter] RAG 清理失败: {rag_err}")
        rag_ok = False

    logger.info(
        f"[delete_chapter] chapter {chapter_id} deleted:"
        f"versions={versions_count}, outline={outline_count},"
        f"reviews={review_count}, consistency={consistency_count}, rag_ok={rag_ok}"
    )
    return {
        "status": "ok",
        "deleted": {
            "chapter_id": chapter_id,
            "versions": versions_count,
            "outline": outline_count,
            "reviews": review_count,
            "consistency_records": consistency_count,
            "rag_index": rag_ok,
        }
    }


class BatchDeleteRequest(BaseModel):
    chapter_ids: list[int]


@router.post("/projects/{project_id}/chapters/batch-delete")
async def batch_delete_chapters(
    project_id: str, req: BatchDeleteRequest, db: Session = Depends(get_db)
):
    """批量删除章节(完整清理章节相关所有数据)

    行为:
      - 验证所有 chapter_ids 属于该项目
      - 删除 ChapterVersion / ChapterOutline / ReviewSession / ConsistencyRecord
      - 删除 Chapter 本身
      - 同步清理 RAG chapter_events
      - 全部在 1 个事务里(失败则全回滚)
    """
    from storage.models import ChapterVersion, ChapterOutline, ReviewSession, ConsistencyRecord
    if not req.chapter_ids:
        return {"status": "failed", "error": "chapter_ids 不能为空"}

    # 验证所有 chapter 都属于该项目
    chapters = db.query(Chapter).filter(
        Chapter.id.in_(req.chapter_ids),
        Chapter.project_id == project_id,
    ).all()
    found_ids = {c.id for c in chapters}
    missing = set(req.chapter_ids) - found_ids
    if missing:
        return {
            "status": "failed",
            "error": f"以下 chapter_id 不属于该项目 {project_id} 或不存在: {sorted(missing)}"
        }

    chapter_ids = list(found_ids)
    try:
        # 1. 删 ChapterVersion
        versions_count = db.query(ChapterVersion).filter(
            ChapterVersion.chapter_id.in_(chapter_ids)
        ).delete(synchronize_session=False)
        # 2. 删 ChapterOutline
        outline_count = db.query(ChapterOutline).filter(
            ChapterOutline.chapter_id.in_(chapter_ids)
        ).delete(synchronize_session=False)
        # 3. 删 ReviewSession
        review_count = db.query(ReviewSession).filter(
            ReviewSession.chapter_id.in_(chapter_ids)
        ).delete(synchronize_session=False)
        # 4. 删 ConsistencyRecord
        consistency_count = db.query(ConsistencyRecord).filter(
            ConsistencyRecord.chapter_id.in_(chapter_ids)
        ).delete(synchronize_session=False)
        # 5. 删 Chapter(级联,所有 model 的 cascade 配置覆盖)
        chapter_count = db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[batch_delete_chapters] DB delete failed: {e}")
        return {"status": "failed", "error": str(e)}

    # 6. 同步从 RAG 清理
    rag_ok_count = 0
    rag_fail_count = 0
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        for cid in chapter_ids:
            try:
                kb.delete_chapter_event(cid)
                rag_ok_count += 1
            except Exception:
                rag_fail_count += 1
    except Exception as e:
        logger.warning(f"[batch_delete_chapters] RAG cleanup batch failed: {e}")
        rag_fail_count = len(chapter_ids)

    logger.info(
        f"[batch_delete_chapters] deleted {chapter_count} chapters from project {project_id}:"
        f"versions={versions_count}, outline={outline_count},"
        f"reviews={review_count}, consistency={consistency_count},"
        f"rag_ok={rag_ok_count}, rag_fail={rag_fail_count}"
    )
    return {
        "status": "ok",
        "deleted": {
            "chapter_count": chapter_count,
            "versions": versions_count,
            "outline": outline_count,
            "reviews": review_count,
            "consistency_records": consistency_count,
            "rag_ok": rag_ok_count,
            "rag_fail": rag_fail_count,
        }
    }


@router.post("/projects/{project_id}/chapters/reindex-rag")
async def reindex_project_rag_endpoint(project_id: str, with_signatures: bool = True, db: Session = Depends(get_db)):
    """全量 reindex 一个项目的 RAG 索引（含 chapter_events 集合）。

    用于：
    - 迁移后回填
    - 索引漂移修复
    - 给老章节补 event_signature

    Args:
        with_signatures: 是否对无 event_signature 的章节调 LLM 抽取（耗时）

    Returns:
        {"status": "ok", "counts": {"characters": N, "world_entries": N, "chapters": N, "chapter_events": N}}
    """
    from llm.chapter_pipeline import reindex_project_rag
    counts = reindex_project_rag(project_id, db, with_signatures=with_signatures)
    return {"status": "ok", "counts": counts}


@router.get("/projects/{project_id}/chapters/{chapter_id}/prep-info")
async def get_chapter_prep_info(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节的"已发生事件清单 + RAG 相似事件"（给前端展示）。

    复用 build_chapter_prep_info()，只取其中 RAG / 去重相关字段返回。
    """
    _verify_chapter(chapter_id, project_id, db)
    from llm.chapter_pipeline import build_chapter_prep_info
    prep = build_chapter_prep_info(db, project_id, chapter_id)
    return {
        "chapter_id": chapter_id,
        "previous_events": prep.get("previous_event_signatures", []),
        "previous_events_text": prep.get("previous_event_signatures_text", ""),
        "dedup_matches": prep.get("event_dedup_matches", []),
        "dedup_text": prep.get("event_dedup_text", ""),
        "max_dedup_similarity": prep.get("max_dedup_similarity", 0.0),
        "event_signature": (prep.get("chapter_outline") or {}).get("key_content", ""),  # 当前 key_content（不是已发生事件）
    }


@router.get("/projects/{project_id}/chapters/{chapter_id}/versions", response_model=list[VersionResponse])
async def list_versions(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节版本历史"""
    _verify_chapter(chapter_id, project_id, db)
    versions = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .all()
    )
    return versions


@router.post("/projects/{project_id}/chapters/{chapter_id}/rollback/{version_num}", response_model=ChapterResponse)
async def rollback_chapter(project_id: str, chapter_id: int, version_num: int, db: Session = Depends(get_db)):
    """回滚到指定版本"""
    chapter = _verify_chapter(chapter_id, project_id, db)

    version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id, ChapterVersion.version_num == version_num)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    last_version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .first()
    )
    backup = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        version_num=last_version.version_num + 1,
    )
    db.add(backup)

    chapter.content = version.content
    chapter.word_count = _count_words(version.content)
    db.commit()
    db.refresh(chapter)
    return chapter


# ═══════════════════════════════════════════════════════════════
# 章节生成流水线 API
# ═══════════════════════════════════════════════════════════════

class PipelineRequest(BaseModel):
    project_id: str
    chapter_id: int
    provider: str | None = None
    auto_revise: bool = True
    revision_threshold: float = 6.5
    guide: str = ""  # 内容引导，用于在LLM生成细纲时引导情节走向


class PipelineResponse(BaseModel):
    status: str
    task_id: str | None = None
    run_id: int | None = None
    project_id: str | None = None
    chapter_id: int | None = None
    final_word_count: int | None = None
    stages: dict = {}
    post_processing: dict = {}
    error: str | None = None
    total_duration_ms: float | None = None
    notifications: list = []


# 复用此路由的 generator 路径
pipeline_router = APIRouter(prefix="/api/chapters", tags=["章节生成"])


@pipeline_router.post("/generate-pipeline", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest, db: Session = Depends(get_db)):
    """
    一键章节生成（9 步流水线，异步：提交到线程池，立即返回 task_id）

    前端轮询 /api/tasks/{task_id} 获取结果。
    """
    from api.tasks import submit_llm_task
    task = submit_llm_task(
        task_type="chapter_pipeline",
        llm_call_fn=_async_pipeline_task,
        project_id=req.project_id,
        description=f"生成章节 [{req.chapter_id}]",
        req=req,
    )
    return PipelineResponse(
        status="submitted",
        task_id=task.id,
        project_id=req.project_id,
        chapter_id=req.chapter_id,
    )


def _async_pipeline_task(task_id: str, req: PipelineRequest):
    from storage.database import SessionLocal
    from llm.chapter_pipeline import run_chapter_generation_pipeline, PIPELINE_STAGES_META
    from api.tasks import get_task
    import time as _time

    db = SessionLocal()
    try:
        task = get_task(task_id)

        # 初始化 task.result.stages（让前端轮询时一开始就能看到 9 个 step 骨架）
        if task is not None:
            task.result = {
                "stages": {
                    m["id"]: {
                        "id": m["id"],
                        "label": m["label"],
                        "weight": m["weight"],
                        "status": "pending",  # pending / running / completed / failed
                        "duration_ms": None,
                    }
                    for m in PIPELINE_STAGES_META
                },
                "current_stage": None,
                "progress_pct": 0,
                "post_processing": {},
            }
            task.progress = 5  # 一启动就让任务管理面板活起来

        # 进度回调：每 stage 跑开始/完成时调用
        def _on_progress(stage_id: str, status: str, info: dict):
            t = get_task(task_id)
            if t is None:
                return
            r = dict(t.result or {})
            stages = dict(r.get("stages") or {})
            entry = dict(stages.get(stage_id) or {"id": stage_id})
            entry["status"] = status
            if "duration_ms" in info:
                entry["duration_ms"] = info["duration_ms"]
            if "label" in info:
                entry["label"] = info["label"]
            if "error" in info:
                entry["error"] = info["error"]
            if "score" in info:
                entry["score"] = info["score"]
            stages[stage_id] = entry
            r["stages"] = stages
            r["current_stage"] = stage_id if status == "running" else r.get("current_stage")
            r["progress_pct"] = info.get("progress_pct", r.get("progress_pct", 0))
            t.result = r
            t.progress = max(t.progress or 0, min(95, r["progress_pct"] + 5))
            logger.info(
                f"[PipelineTask {task_id}] stage {stage_id} → {status} "
                f"({entry.get('duration_ms') or 0:.0f}ms) progress={r['progress_pct']}%"
            )

        result = run_chapter_generation_pipeline(
            db, req.project_id, req.chapter_id, req.provider,
            auto_revise=req.auto_revise,
            revision_threshold=req.revision_threshold,
            progress_cb=_on_progress,
            guide=req.guide,
        )

        # 收尾：把完整 stages 列表 + 终态写进 task.result
        if task is not None:
            r = dict(task.result or {})
            r["status"] = result.get("status")
            r["final_word_count"] = result.get("final_word_count")
            r["post_processing"] = result.get("post_processing", {})
            r["total_duration_ms"] = result.get("total_duration_ms")
            r["error"] = result.get("error")
            r["progress_pct"] = 100
            task.result = r
            task.progress = 100
            task.completed_at = _time.time()
        return result
    finally:
        db.close()




# ═══════════════════════════════════════════════════════════════
# 章节修订 API（根据细纲和评审报告重新生成正文）
# ═══════════════════════════════════════════════════════════════

class ReviseRequest(BaseModel):
    project_id: str
    chapter_id: int
    provider: str | None = None


@pipeline_router.post("/revise", response_model=PipelineResponse)
async def revise_chapter(req: ReviseRequest, db: Session = Depends(get_db)):
    """
    章节修订：根据已生成的细纲和评审报告，由LLM重新生成正文。
    旧版正文标记为废稿，移入废纸篓。
    """
    from api.tasks import submit_llm_task

    # 验证章节存在且有正文
    chapter = db.query(Chapter).filter(Chapter.id == req.chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="章节没有正文内容，无法修订")

    task = submit_llm_task(
        task_type="chapter_revise",
        llm_call_fn=_async_revise_task,
        project_id=req.project_id,
        description=f"修订章节 [{req.chapter_id}]",
        req=req,
    )
    return PipelineResponse(
        status="submitted",
        task_id=task.id,
        project_id=req.project_id,
        chapter_id=req.chapter_id,
    )


def _async_revise_task(task_id: str, req: ReviseRequest):
    from storage.database import SessionLocal
    from llm.chapter_pipeline import run_chapter_revise

    db = SessionLocal()
    try:
        # 初始化 task.result.stages
        from api.tasks import get_task
        task = get_task(task_id)
        if task is not None:
            revise_stages = [
                "1_get_outline", "2_save_old", "3_get_review",
                "4_generate", "5_adjust", "6_review", "7_save", "8_post"
            ]
            task.result = {
                "stages": {
                    sid: {"id": sid, "label": sid, "status": "pending", "duration_ms": None}
                    for sid in revise_stages
                },
                "current_stage": None,
                "progress_pct": 0,
            }
            task.progress = 5

        # 进度回调
        def _on_progress(stage_id: str, status: str, info: dict):
            t = get_task(task_id)
            if t is None:
                return
            r = dict(t.result or {})
            stages = dict(r.get("stages") or {})
            entry = dict(stages.get(stage_id) or {"id": stage_id})
            entry["status"] = status
            if "duration_ms" in info:
                entry["duration_ms"] = info["duration_ms"]
            if "label" in info:
                entry["label"] = info["label"]
            if "error" in info:
                entry["error"] = info["error"]
            if "score" in info:
                entry["score"] = info["score"]
            stages[stage_id] = entry
            r["stages"] = stages
            r["current_stage"] = stage_id if status == "running" else r.get("current_stage")
            r["progress_pct"] = info.get("progress_pct", r.get("progress_pct", 0))
            t.result = r
            t.progress = max(t.progress or 0, min(95, r["progress_pct"] + 5))
            logger.info(
                f"[ReviseTask {task_id}] stage {stage_id} -> {status} "
                f"({entry.get('duration_ms') or 0:.0f}ms) progress={r['progress_pct']}%"
            )

        result = run_chapter_revise(
            db=db,
            project_id=req.project_id,
            chapter_id=req.chapter_id,
            provider=req.provider,
            task_id=task_id,
            progress_cb=_on_progress,
        )
        return result
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 字数调整 API（独立功能：缩写 or 扩写到目标字数区间）
# ═══════════════════════════════════════════════════════════════

class WordAdjustRequest(BaseModel):
    project_id: str
    chapter_id: int
    provider: str | None = None
    # 可选：手动覆盖项目默认的 min~max 区间
    # 不传时使用项目设置（target_word_count, word_count_min, word_count_max）
    target_words: int | None = None
    min_words: int | None = None
    max_words: int | None = None


@pipeline_router.post("/adjust-word-count", response_model=PipelineResponse)
async def adjust_word_count_endpoint(req: WordAdjustRequest, db: Session = Depends(get_db)):
    """字数调整：基于目标字数区间（min~max），自动判定缩写还是扩写。

    - 不在区间内 → 调用 LLM 调整
    - 已在区间内 → 直接返回 success，不调 LLM
    - 完成后保存到 chapter.content（创建 ChapterVersion 快照）
    """
    from api.tasks import submit_llm_task
    chapter = db.query(Chapter).filter(Chapter.id == req.chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="章节没有正文内容，无法调整")

    task = submit_llm_task(
        task_type="word_adjust",
        llm_call_fn=_async_word_adjust_task,
        project_id=req.project_id,
        description=f"字数调整 [{req.chapter_id}]",
        req=req,
    )
    return PipelineResponse(
        status="submitted",
        task_id=task.id,
        project_id=req.project_id,
        chapter_id=req.chapter_id,
    )


def _async_word_adjust_task(task_id: str, req: WordAdjustRequest):
    """异步执行字数调整：先取现状，调 adjust_word_count，保存并打版本快照。"""
    from storage.database import SessionLocal
    from storage.models import Chapter, ChapterVersion, Project
    from llm.chapter_pipeline import adjust_word_count, _count_chinese_chars
    from api.tasks import get_task
    import time as _time

    db = SessionLocal()
    # 在 try 之前声明 task 变量，避免 except 块里"未关联的值"错误
    task = None
    try:
        task = get_task(task_id)
        if task is not None:
            task.result = {
                "stages": {
                    "1_check": {"id": "1_check", "label": "检查字数", "status": "pending", "duration_ms": None},
                    "2_adjust": {"id": "2_adjust", "label": "LLM 调整", "status": "pending", "duration_ms": None},
                    "3_save": {"id": "3_save", "label": "保存入库", "status": "pending", "duration_ms": None},
                },
                "current_stage": None,
                "progress_pct": 0,
            }
            task.progress = 5

        def _on_progress(stage_id: str, status: str, info: dict):
            t = get_task(task_id)
            if t is None:
                return
            r = dict(t.result or {})
            stages = dict(r.get("stages") or {})
            entry = dict(stages.get(stage_id) or {"id": stage_id})
            entry["status"] = status
            if "duration_ms" in info:
                entry["duration_ms"] = info["duration_ms"]
            if "label" in info:
                entry["label"] = info["label"]
            if "error" in info:
                entry["error"] = info["error"]
            stages[stage_id] = entry
            r["stages"] = stages
            r["current_stage"] = stage_id if status == "running" else r.get("current_stage")
            r["progress_pct"] = info.get("progress_pct", r.get("progress_pct", 0))
            t.result = r
            t.progress = max(t.progress or 0, min(95, r["progress_pct"] + 5))

        import time as _time
        t0 = _time.time()

        # ── Stage 1: 检查字数 ──
        _on_progress("1_check", "running", {"label": "检查字数", "progress_pct": 10})
        project = db.query(Project).filter(Project.id == req.project_id).first()
        if not project:
            raise ValueError(f"Project {req.project_id} not found")
        chapter = db.query(Chapter).filter(Chapter.id == req.chapter_id).first()
        if not chapter or not chapter.content:
            raise ValueError("章节不存在或无正文")

        # 优先用请求里手动传的 min/max/target，否则用项目默认设置
        target = req.target_words if req.target_words is not None else (project.target_word_count or 3000)
        min_w = req.min_words if req.min_words is not None else (project.word_count_min or 2000)
        max_w = req.max_words if req.max_words is not None else (project.word_count_max or 5000)
        # 兜底：min 不能大于 max
        if min_w > max_w:
            min_w, max_w = max_w, min_w
        # 兜底：target 必须在区间内
        if target < min_w or target > max_w:
            target = (min_w + max_w) // 2

        current_chars = _count_chinese_chars(chapter.content)
        in_range = min_w <= current_chars <= max_w
        is_custom = (req.target_words is not None) or (req.min_words is not None) or (req.max_words is not None)

        _on_progress("1_check", "completed", {
            "label": "检查字数",
            "duration_ms": (_time.time() - t0) * 1000,
            "progress_pct": 20,
        })

        # 已在区间内，无需调整
        if in_range:
            logger.info(
                f"[WordAdjust standalone] ch={req.chapter_id} 当前 {current_chars}字 "
                f"已在区间 {min_w}~{max_w} 内（{'自定义' if is_custom else '项目默认'}）"
            )
            if task is not None:
                r = dict(task.result or {})
                r["status"] = "completed"
                r["skipped"] = True
                r["current_chars"] = current_chars
                r["target_chars"] = target
                r["min_chars"] = min_w
                r["max_chars"] = max_w
                r["is_custom_range"] = is_custom
                r["final_word_count"] = current_chars
                r["progress_pct"] = 100
                task.result = r
                task.progress = 100
                task.completed_at = _time.time()
            return {
                "status": "completed",
                "skipped": True,
                "current_chars": current_chars,
                "target_chars": target,
                "min_chars": min_w,
                "max_chars": max_w,
                "is_custom_range": is_custom,
            }

        # ── Stage 2: LLM 调整 ──
        t1 = _time.time()
        _on_progress("2_adjust", "running", {"label": "LLM 调整中…", "progress_pct": 30})
        # 从 chapter_outline 取细纲（如果有）作为压缩/扩写的参考
        from storage.models import ChapterOutline
        outline_row = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == req.chapter_id).first()
        outline_for_llm = {}
        if outline_row:
            outline_for_llm = {
                "chapter_position": outline_row.chapter_position or "",
                "pacing": outline_row.pacing or "平稳",
                "key_content": outline_row.key_content or "",
                "plot_advance": outline_row.plot_advance or "",
            }
        adjusted = adjust_word_count(
            chapter.content, target, min_w, max_w, outline_for_llm, req.provider,
        )
        new_chars = _count_chinese_chars(adjusted)
        _on_progress("2_adjust", "completed", {
            "label": "LLM 调整完成",
            "duration_ms": (_time.time() - t1) * 1000,
            "progress_pct": 80,
        })

        # ── Stage 3: 保存入库 + 版本快照 ──
        t2 = _time.time()
        _on_progress("3_save", "running", {"label": "保存入库", "progress_pct": 90})
        # 备份旧版本（在替换 content 之前）
        last_ver = (
            db.query(ChapterVersion)
            .filter(ChapterVersion.chapter_id == req.chapter_id)
            .order_by(ChapterVersion.version_num.desc())
            .first()
        )
        next_ver_num = (last_ver.version_num + 1) if last_ver else 1
        old_version = ChapterVersion(
            chapter_id=req.chapter_id,
            content=chapter.content,  # 旧内容（即将被覆盖）
            version_num=next_ver_num,
        )
        db.add(old_version)
        # 替换为新内容
        chapter.content = adjusted
        chapter.word_count = new_chars
        db.commit()
        _on_progress("3_save", "completed", {
            "label": "保存入库",
            "duration_ms": (_time.time() - t2) * 1000,
            "progress_pct": 100,
        })

        if task is not None:
            r = dict(task.result or {})
            r["status"] = "completed"
            r["skipped"] = False
            r["current_chars"] = current_chars
            r["new_chars"] = new_chars
            r["target_chars"] = target
            r["min_chars"] = min_w
            r["max_chars"] = max_w
            r["is_custom_range"] = is_custom
            r["delta"] = new_chars - current_chars
            r["version_num"] = next_ver_num
            r["final_word_count"] = new_chars
            r["progress_pct"] = 100
            task.result = r
            task.progress = 100
            task.completed_at = _time.time()

        return {
            "status": "completed",
            "skipped": False,
            "current_chars": current_chars,
            "new_chars": new_chars,
            "target_chars": target,
            "min_chars": min_w,
            "max_chars": max_w,
            "is_custom_range": is_custom,
            "delta": new_chars - current_chars,
            "version_num": next_ver_num,
        }
    except Exception as e:
        logger.error(f"[WordAdjust standalone] failed: {e}", exc_info=True)
        if task is not None:
            r = dict(task.result or {})
            r["status"] = "failed"
            r["error"] = str(e)
            r["progress_pct"] = 100
            task.result = r
            task.progress = 100
            task.error = str(e)
        raise
    finally:
        db.close()

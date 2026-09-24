"""剧本场景 CRUD + 生成 API"""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project, Character
from storage.models.screenplay import Screenplay, Storyboard
from api.routes.storyboards import StoryboardResponse
from logger import logger


router = APIRouter(prefix="/api/projects/{project_id}/screenplays", tags=["剧本场景"])


# ─── Schemas ───

class ScreenplayCreate(BaseModel):
    title: str
    scene_number: int = 0
    act: str = "第一幕"
    scene_type: str = "对话场景"
    location: str = ""
    time_of_day: str = "白天"
    characters_present: list = []
    synopsis: str = ""


class ScreenplayUpdate(BaseModel):
    title: str | None = None
    scene_number: int | None = None
    act: str | None = None
    scene_type: str | None = None
    location: str | None = None
    time_of_day: str | None = None
    characters_present: list | None = None
    content: str | None = None
    synopsis: str | None = None


# StoryboardResponse 定义在 api/routes/storyboards.py，此处 import 复用


# ─── Routes ───

@router.get("")
async def list_screenplays(project_id: str, db: Session = Depends(get_db)):
    """获取场景列表"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    screenplays = (
        db.query(Screenplay)
        .filter(Screenplay.project_id == project_id)
        .order_by(Screenplay.scene_number)
        .all()
    )
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "title": s.title,
            "scene_number": s.scene_number,
            "act": s.act,
            "scene_type": s.scene_type,
            "location": s.location,
            "time_of_day": s.time_of_day,
            "characters_present": s.characters_present,
            "content": s.content,
            "word_count": s.word_count,
            "synopsis": s.synopsis,
            "fingerprint": s.fingerprint,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in screenplays
    ]


@router.post("")
async def create_screenplay(project_id: str, data: dict, db: Session = Depends(get_db)):
    """创建场景"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    screenplay = Screenplay(
        project_id=project_id,
        title=data.get("title", "未命名场景"),
        scene_number=data.get("scene_number", 0),
        act=data.get("act", "第一幕"),
        scene_type=data.get("scene_type", "对话场景"),
        location=data.get("location", ""),
        time_of_day=data.get("time_of_day", "白天"),
        characters_present=data.get("characters_present", []),
        synopsis=data.get("synopsis", ""),
    )
    db.add(screenplay)
    db.commit()
    db.refresh(screenplay)
    return {
        "id": screenplay.id,
        "project_id": screenplay.project_id,
        "title": screenplay.title,
        "scene_number": screenplay.scene_number,
        "act": screenplay.act,
        "scene_type": screenplay.scene_type,
        "location": screenplay.location,
        "time_of_day": screenplay.time_of_day,
        "characters_present": screenplay.characters_present,
        "synopsis": screenplay.synopsis,
    }


@router.get("/{screenplay_id}")
async def get_screenplay(project_id: str, screenplay_id: int, db: Session = Depends(get_db)):
    """获取单个场景"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")
    return {
        "id": screenplay.id,
        "project_id": screenplay.project_id,
        "title": screenplay.title,
        "scene_number": screenplay.scene_number,
        "act": screenplay.act,
        "scene_type": screenplay.scene_type,
        "location": screenplay.location,
        "time_of_day": screenplay.time_of_day,
        "characters_present": screenplay.characters_present,
        "content": screenplay.content,
        "word_count": screenplay.word_count,
        "synopsis": screenplay.synopsis,
        "fingerprint": screenplay.fingerprint,
        "created_at": screenplay.created_at.isoformat() if screenplay.created_at else None,
        "updated_at": screenplay.updated_at.isoformat() if screenplay.updated_at else None,
    }


@router.put("/{screenplay_id}")
async def update_screenplay(project_id: str, screenplay_id: int, data: dict, db: Session = Depends(get_db)):
    """更新场景"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    updatable_fields = [
        "title", "scene_number", "act", "scene_type", "location",
        "time_of_day", "characters_present", "content", "synopsis",
    ]
    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(screenplay, field, data[field])

    # 自动更新字数
    if "content" in data and data["content"] is not None:
        screenplay.word_count = len(data["content"])

    db.commit()
    db.refresh(screenplay)
    return {
        "id": screenplay.id,
        "project_id": screenplay.project_id,
        "title": screenplay.title,
        "scene_number": screenplay.scene_number,
        "word_count": screenplay.word_count,
    }


@router.delete("/{screenplay_id}")
async def delete_screenplay(project_id: str, screenplay_id: int, db: Session = Depends(get_db)):
    """删除场景"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    db.delete(screenplay)
    db.commit()
    return {"detail": "Deleted"}


@router.post("/{screenplay_id}/generate")
async def generate_screenplay(project_id: str, screenplay_id: int, data: dict, db: Session = Depends(get_db)):
    """生成场景剧本（触发 Pipeline，异步执行）"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    provider = data.get("provider")

    # 异步提交到线程池
    from api.tasks import submit_llm_task

    def _async_screenplay_task(task_id: str, _project_id: str, _screenplay_id: int, _provider: str | None):
        from storage.database import SessionLocal
        from llm.script_pipeline import run_script_generation_pipeline
        _db = SessionLocal()
        try:
            from api.tasks import get_task
            task = get_task(task_id)
            if not task:
                return
            result = run_script_generation_pipeline(
                db=_db,
                project_id=_project_id,
                screenplay_id=_screenplay_id,
                provider=_provider,
                task_id=task_id,
            )
            # 只存储可序列化的简化结果（pipeline 的 stages 中可能含 SQLAlchemy 对象）
            task.result = {
                "status": result.get("status"),
                "duration_ms": result.get("duration_ms"),
                "error": result.get("error"),
                "screenplay_content_len": len(result.get("screenplay_content", "") or ""),
                "storyboard_count": len(result.get("storyboards", []) or []),
                "stages_summary": {
                    name: {"status": s.get("status"), "duration_ms": s.get("duration_ms")}
                    for name, s in (result.get("stages") or {}).items()
                },
            }
            task.status = "completed" if result.get("status") == "completed" else "failed"
            task.progress = 100
            task.completed_at = time.time()
        except Exception as e:
            from api.tasks import get_task
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = time.time()
            logger.error(f"[ScreenplayTask] task_id={task_id} failed: {e}")
        finally:
            _db.close()

    task = submit_llm_task(
        task_type="screenplay_generate",
        llm_call_fn=_async_screenplay_task,
        project_id=project_id,
        description=f"生成场景剧本「{screenplay.title}」",
        _project_id=project_id,
        _screenplay_id=screenplay_id,
        _provider=provider,
    )

    return {
        "task_id": task.id,
        "status": "submitted",
    }


@router.post("/{screenplay_id}/storyboards/generate")
async def generate_storyboards(project_id: str, screenplay_id: int, data: dict, db: Session = Depends(get_db)):
    """生成分镜稿（已有正文时单独触发）"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    if not screenplay.content:
        raise HTTPException(status_code=400, detail="场景正文为空，请先生成剧本正文")

    provider = data.get("provider")
    density = data.get("density")

    from api.tasks import submit_llm_task

    def _async_storyboard_task(task_id: str, _project_id: str, _screenplay_id: int, _provider: str | None, _density: str | None = None):
        from storage.database import SessionLocal
        from llm.script_pipeline import _call_llm, _parse_storyboard_flexible, storyboard_density_prompt
        from llm.script_roles import get_script_role
        from storage.models.screenplay import Screenplay, Storyboard
        from storage.models import Project, Character

        _db = SessionLocal()
        try:
            from api.tasks import get_task
            task = get_task(task_id)
            if not task:
                return

            sp = _db.query(Screenplay).filter(Screenplay.id == _screenplay_id).first()
            project = _db.query(Project).filter(Project.id == _project_id).first()
            if not sp or not project:
                task.status = "failed"
                task.error = "Screenplay or Project not found"
                return

            # 获取角色外貌
            char_names = sp.characters_present or []
            if char_names:
                chars = _db.query(Character).filter(
                    Character.project_id == _project_id,
                    Character.name.in_(char_names),
                ).all()
            else:
                chars = []
            characters_with_appearance = "\n\n".join(
                [f"- {c.name}：{c.appearance_text or (c.description or '')[:200]}" for c in chars]
            ) or "（暂无外貌信息）"

            ctx = {
                "script_format": project.script_format or "movie",
                "scene_number": sp.scene_number or 0,
                "scene_title": sp.title or "",
                "location": sp.location or "",
                "time_of_day": sp.time_of_day or "白天",
                "characters_with_appearance": characters_with_appearance,
                "scene_content": sp.content,
                "density": storyboard_density_prompt(_density),
            }
            user_msg = f"请为场景 {sp.scene_number}「{sp.title}」制作分镜稿。"
            raw = _call_llm(
                "script_storyboard_gen", ctx, user_msg,
                provider=_provider, db=_db, project_id=_project_id, task_id=task_id,
            )
            storyboard_data = _parse_storyboard_flexible(raw)

            # 删除旧分镜
            _db.query(Storyboard).filter(Storyboard.screenplay_id == _screenplay_id).delete()

            # 保存新分镜
            for shot_data in storyboard_data:
                sb = Storyboard(
                    screenplay_id=_screenplay_id,
                    project_id=_project_id,
                    shot_number=shot_data.get("shot_number", 1),
                    shot_type=shot_data.get("shot_type", "中景"),
                    camera_angle=shot_data.get("camera_angle", "平视"),
                    camera_movement=shot_data.get("camera_movement", "固定"),
                    duration_estimate=shot_data.get("duration_estimate", "3-5秒"),
                    location=sp.location or "",
                    characters=sp.characters_present or [],
                    visual_description=shot_data.get("visual_description", ""),
                    dialogue=shot_data.get("dialogue", ""),
                    sound_effects=shot_data.get("sound_effects", ""),
                    notes=shot_data.get("notes", ""),
                )
                _db.add(sb)
            _db.commit()

            task.result = {"storyboards": storyboard_data}
            task.status = "completed"
            task.progress = 100
            task.completed_at = time.time()
        except Exception as e:
            from api.tasks import get_task
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = time.time()
            logger.error(f"[StoryboardTask] task_id={task_id} failed: {e}")
        finally:
            _db.close()

    task = submit_llm_task(
        task_type="storyboard_generate",
        llm_call_fn=_async_storyboard_task,
        project_id=project_id,
        description=f"生成分镜稿「{screenplay.title}」",
        _project_id=project_id,
        _screenplay_id=screenplay_id,
        _provider=provider,
        _density=density,
    )

    return {
        "task_id": task.id,
        "status": "submitted",
    }


@router.get("/{screenplay_id}/storyboards", response_model=list[StoryboardResponse])
async def list_storyboards(project_id: str, screenplay_id: int, db: Session = Depends(get_db)):
    """获取分镜稿列表"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    storyboards = (
        db.query(Storyboard)
        .filter(Storyboard.screenplay_id == screenplay_id)
        .order_by(Storyboard.shot_number)
        .all()
    )
    return storyboards

"""灵感管理 API - 主界面级特性

全局灵感池 + 项目内灵感混合管理：
- GET    /api/inspirations                       全局/项目灵感列表（含搜索/标签筛选）
- POST   /api/inspirations                       创建灵感（可选 project_id）
- GET    /api/inspirations/{id}                  单条
- PUT    /api/inspirations/{id}                  更新
- DELETE /api/inspirations/{id}                  删除
- GET    /api/inspirations/tags                  全局标签云
- POST   /api/inspirations/{id}/create-project   以此灵感为种子创建新项目
- POST   /api/inspirations/{id}/fuse              将灵感融合进现有项目的指定章节/大纲
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import datetime
from typing import Optional

from storage.database import get_db
from storage.models import Inspiration, Project, Chapter, ProjectOutline
from logger import logger


router = APIRouter(prefix="/api/inspirations", tags=["灵感"])


# ─── Schemas ───

class InspirationCreate(BaseModel):
    content: str
    title: str = ""
    project_id: int | None = None  # 可选：null=全局灵感池
    tags: list[str] = []
    source: str = ""  # 脑洞/阅读/梦境/生活/...
    related_characters: list[dict] = []  # [{"project_id":1,"character_id":2}]
    related_chapters: list[dict] = []    # [{"project_id":1,"chapter_id":5}]


class InspirationUpdate(BaseModel):
    content: str | None = None
    title: str | None = None
    project_id: int | None = None  # 允许改绑到项目（或 null 退回全局）
    tags: list[str] | None = None
    source: str | None = None
    related_characters: list[dict] | None = None
    related_chapters: list[dict] | None = None


class InspirationResponse(BaseModel):
    id: int
    project_id: int | None
    title: str
    content: str
    tags: list
    source: str
    related_characters: list
    related_chapters: list
    is_consumed: int
    consumed_at: object | None
    consumed_into: str
    created_at: object
    updated_at: object

    class Config:
        from_attributes = True


class CreateProjectFromInspirationRequest(BaseModel):
    """以灵感为种子创建项目"""
    title: str | None = None  # 默认用灵感标题
    chapter_word_count: int = 3
    genre: str = "其他"  # 兼容多选前的旧版
    description: str | None = None  # 默认用灵感内容前 200 字
    # 也可显式覆盖 4 必填
    extra_user_input: dict = Field(default_factory=dict)


class CreateProjectFromInspirationResponse(BaseModel):
    project_id: int
    run_id: int | None = None
    status: str
    message: str = ""


class FuseInspirationRequest(BaseModel):
    """将灵感融合进现有项目"""
    project_id: int  # 目标项目
    target: str  # "chapter:N" | "outline" | "world" | "character"
    # 比如 "chapter:5" 表示融合到第 5 章；"outline" 表示融入项目大纲
    note: str = ""  # 额外说明（如何融合）


class FuseInspirationResponse(BaseModel):
    status: str
    target: str
    project_id: int
    message: str
    fused_content: str | None = None  # 若融合到 chapter/outline，返回融合后片段


# ─── Routes ───

@router.get("", response_model=list[InspirationResponse])
async def list_inspirations(
    project_id: int | None = Query(None, description="按项目筛选；None=全局灵感池"),
    tag: str | None = Query(None),
    q: str | None = Query(None, description="搜索关键字（标题/内容）"),
    source: str | None = Query(None),
    include_consumed: bool = Query(False),
    db: Session = Depends(get_db),
):
    """列出灵感

    - 不带 project_id：返回全局灵感（project_id IS NULL）
    - 带 project_id：返回该项目下的灵感（仅 project_id 匹配）
    - 若想"全局 + 某项目"混合：传 project_id=-1 表示混合
    """
    query = db.query(Inspiration)
    if project_id is None:
        query = query.filter(Inspiration.project_id.is_(None))
    elif project_id == -1:
        # 混合模式：全局 + 项目；project_id 必须显式传
        pass  # 不加 filter
    else:
        query = query.filter(Inspiration.project_id == project_id)

    if tag:
        query = query.filter(Inspiration.tags.contains([tag]))
    if source:
        query = query.filter(Inspiration.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Inspiration.title.like(like), Inspiration.content.like(like))
        )
    if not include_consumed:
        query = query.filter(Inspiration.is_consumed == 0)

    return query.order_by(Inspiration.updated_at.desc()).all()


@router.post("", response_model=InspirationResponse)
async def create_inspiration(data: InspirationCreate, db: Session = Depends(get_db)):
    """创建灵感（全局或绑定项目）"""
    if data.project_id is not None:
        proj = db.query(Project).filter(Project.id == data.project_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

    insp = Inspiration(
        project_id=data.project_id,
        title=data.title.strip() or data.content[:30].strip(),
        content=data.content,
        tags=data.tags,
        source=data.source,
        related_characters=data.related_characters,
        related_chapters=data.related_chapters,
    )
    db.add(insp)
    db.commit()
    db.refresh(insp)
    return insp


@router.get("/tags")
async def list_all_tags(
    project_id: int | None = Query(None, description="None=全局标签云"),
    db: Session = Depends(get_db),
):
    """获取标签云（去重 + 计数）"""
    query = db.query(Inspiration)
    if project_id is None:
        query = query.filter(Inspiration.project_id.is_(None))
    else:
        query = query.filter(Inspiration.project_id == project_id)

    tag_counts: dict[str, int] = {}
    for insp in query.all():
        for t in (insp.tags or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    # 按使用频次降序
    return [
        {"name": name, "count": count}
        for name, count in sorted(tag_counts.items(), key=lambda x: -x[1])
    ]


@router.get("/sources")
async def list_sources(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """获取所有 source 字段（去重）"""
    query = db.query(Inspiration.source).distinct()
    if project_id is None:
        query = query.filter(Inspiration.project_id.is_(None))
    else:
        query = query.filter(Inspiration.project_id == project_id)
    return [s[0] for s in query.all() if s[0]]


@router.get("/{insp_id}", response_model=InspirationResponse)
async def get_inspiration(insp_id: int, db: Session = Depends(get_db)):
    insp = db.query(Inspiration).filter(Inspiration.id == insp_id).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")
    return insp


@router.put("/{insp_id}", response_model=InspirationResponse)
async def update_inspiration(insp_id: int, data: InspirationUpdate, db: Session = Depends(get_db)):
    insp = db.query(Inspiration).filter(Inspiration.id == insp_id).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(insp, field, value)
    db.commit()
    db.refresh(insp)
    return insp


@router.delete("/{insp_id}")
async def delete_inspiration(insp_id: int, db: Session = Depends(get_db)):
    insp = db.query(Inspiration).filter(Inspiration.id == insp_id).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")
    db.delete(insp)
    db.commit()
    return {"status": "ok"}


# ─── 以灵感为种子创建新项目 ───

@router.post("/{insp_id}/create-project", response_model=CreateProjectFromInspirationResponse)
async def create_project_from_inspiration(
    insp_id: int,
    data: CreateProjectFromInspirationRequest,
    db: Session = Depends(get_db),
):
    """以灵感为种子创建新项目：
    1. 用灵感内容填充 4 必填（书名默认灵感标题，创意=灵感内容前 200 字）
    2. 自动把灵感标记为 '已融合'
    3. 触发 bootstrap workflow（与常规创建项目一致）
    """
    from api.routes.projects import create_project
    from llm.workflow import plan_bootstrap_stages
    from storage.models.workflow import WorkflowRun
    from api.tasks import submit_llm_task

    insp = db.query(Inspiration).filter(Inspiration.id == insp_id).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")

    title = (data.title or insp.title or f"灵感 #{insp_id}").strip()
    description = (data.description or insp.content[:200]).strip()

    # 构造与 create_project 一致的 payload
    user_input = {
        "title": title,
        "chapter_word_count": data.chapter_word_count,
        "genre": data.genre,
        "description": description,
        "auto_commit": True,
    }
    # 加上灵感全文作为 8 选填 hint
    user_input["premise"] = insp.content  # 灵感全文 → premise 字段
    if insp.tags:
        user_input["theme"] = " / ".join(insp.tags[:5])
    if insp.source:
        user_input["notes"] = f"灵感来源：{insp.source}"

    # 1) 创建项目（直接调用 db 操作，不走 HTTP）
    project = Project(
        title=title,
        description=description,
        target_word_count=data.chapter_word_count * 1000,
        word_count_min=int(data.chapter_word_count * 1000 * 0.7),
        word_count_max=int(data.chapter_word_count * 1000 * 1.3),
        writing_style="平实",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 2) 标记灵感已融合
    insp.is_consumed = 1
    insp.consumed_at = datetime.utcnow()
    insp.consumed_into = f"project:{project.id}"
    db.commit()

    # 3) 触发 bootstrap workflow
    user_filled = {
        f: getattr(data, f) if hasattr(data, f) else None
        for f in ["premise", "theme", "notes"]
    }
    user_filled = {k: v for k, v in user_filled.items() if v}

    stages = plan_bootstrap_stages(
        required={
            "title": title,
            "chapter_word_count": data.chapter_word_count,
            "genre": data.genre,
            "description": description,
        },
        user_filled=user_filled,
    )

    run = WorkflowRun(
        project_id=project.id,
        name="bootstrap_from_inspiration",
        stages=stages,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 4) 异步执行
    submit_llm_task(
        task_type="bootstrap",
        llm_call_fn=_run_bootstrap_task,
        project_id=project.id,
        description=f"项目引导补全（灵感 #{insp_id}）",
        run_id=run.id,
        user_input=user_input,
    )

    return CreateProjectFromInspirationResponse(
        project_id=project.id,
        run_id=run.id,
        status="submitted",
        message=f"已用灵感《{insp.title or '(无标题)'}》创建项目《{title}》",
    )


# ─── 灵感融合进现有项目 ───

@router.post("/{insp_id}/fuse", response_model=FuseInspirationResponse)
async def fuse_inspiration_to_project(
    insp_id: int,
    data: FuseInspirationRequest,
    db: Session = Depends(get_db),
):
    """将灵感融合到现有项目的指定位置：
    - target='outline'         → 追加到 ProjectOutline
    - target='world'           → 追加为 WorldEntry
    - target='character'       → 追加为 Character
    - target='chapter:N'       → 在第 N 章细纲里追加灵感摘要
    - target='chapter_content:N' → 在第 N 章内容里追加灵感段落
    """
    insp = db.query(Inspiration).filter(Inspiration.id == insp_id).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")

    proj = db.query(Project).filter(Project.id == data.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    target = data.target
    fused_text = f"\n\n[灵感 #{insp_id} - {insp.title or '未命名'}]\n{insp.content}"

    if target == "outline":
        outline = db.query(ProjectOutline).filter(
            ProjectOutline.project_id == data.project_id
        ).first()
        if not outline:
            outline = ProjectOutline(project_id=data.project_id, outline_text="")
            db.add(outline)
        outline.outline_text = (outline.outline_text or "") + fused_text
        msg = "已追加到项目大纲"
    elif target == "world":
        from storage.models import WorldEntry
        we = WorldEntry(
            project_id=data.project_id,
            category="灵感补充",
            title=insp.title or f"灵感 #{insp_id}",
            content=insp.content,
            tags=insp.tags or [],
        )
        db.add(we)
        msg = "已添加为世界观条目"
    elif target == "character":
        from storage.models import Character
        ch = Character(
            project_id=data.project_id,
            name=insp.title or f"灵感角色 #{insp_id}",
            role="配角",
            description=insp.content,
        )
        db.add(ch)
        msg = "已添加为角色"
    elif target.startswith("chapter:"):
        # 融合到细纲
        try:
            order = int(target.split(":", 1)[1])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="target 格式: chapter:N")
        from storage.models import Chapter, ChapterOutline
        ch = db.query(Chapter).filter(
            Chapter.project_id == data.project_id, Chapter.order == order
        ).first()
        if not ch:
            raise HTTPException(status_code=404, detail=f"未找到第 {order+1} 章")
        outline = db.query(ChapterOutline).filter(
            ChapterOutline.chapter_id == ch.id
        ).first()
        if outline:
            outline.notes = (outline.notes or "") + f"\n{fused_text}"
        else:
            outline = ChapterOutline(
                chapter_id=ch.id, notes=fused_text
            )
            db.add(outline)
        msg = f"已追加到第 {order+1} 章细纲"
    elif target.startswith("chapter_content:"):
        try:
            order = int(target.split(":", 1)[1])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="target 格式: chapter_content:N")
        from storage.models import Chapter
        ch = db.query(Chapter).filter(
            Chapter.project_id == data.project_id, Chapter.order == order
        ).first()
        if not ch:
            raise HTTPException(status_code=404, detail=f"未找到第 {order+1} 章")
        ch.content = (ch.content or "") + fused_text
        msg = f"已追加到第 {order+1} 章正文"
    else:
        raise HTTPException(
            status_code=400,
            detail="target 必须是: outline | world | character | chapter:N | chapter_content:N",
        )

    # 标记灵感已融合
    insp.is_consumed = 1
    insp.consumed_at = datetime.utcnow()
    insp.consumed_into = f"project:{data.project_id}:{target}"
    db.commit()

    return FuseInspirationResponse(
        status="fused",
        target=target,
        project_id=data.project_id,
        message=msg,
        fused_content=fused_text if "chapter" in target else None,
    )


def _run_bootstrap_task(task_id: str, run_id: int, user_input: dict):
    """以灵感为种子创建项目后的 bootstrap workflow 异步任务"""
    from storage.database import SessionLocal
    from llm.workflow import run_bootstrap_sync
    from api.tasks import get_task

    db = SessionLocal()
    try:
        task = get_task(task_id)
        result = run_bootstrap_sync(run_id, user_input, db=db)
        if task:
            task.status = "completed" if "fail" not in result["status"] else "failed"
            task.result = {"run_id": run_id, "workflow_status": result["status"]}
        return result
    finally:
        db.close()

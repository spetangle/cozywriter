"""项目管理 API - 增强版：4 必填校验 + LLM 补全触发"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project
from storage.models.workflow import WorkflowRun
from datetime import datetime


router = APIRouter(prefix="/api/projects", tags=["项目"])


# ─── 常量：必填/选填字段定义 ───

REQUIRED_FIELDS = ["title", "chapter_word_count", "genre", "description"]
OPTIONAL_FIELDS = [
    "theme", "tone", "style", "pacing", "premise",
    "protagonist", "antagonist", "supporting", "notes",
]
ALL_USER_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

# 各字段可选项（用于前端渲染 + 后端校验）
GENRE_OPTIONS = ["玄幻", "都市", "科幻", "武侠", "仙侠", "历史", "悬疑", "现实主义", "奇幻", "其他"]
TONE_OPTIONS = ["热血", "治愈", "黑暗", "轻松", "史诗", "悬疑紧张", "浪漫", "幽默", "冷峻"]
STYLE_OPTIONS = ["优美", "平实", "诗意", "幽默", "冷峻"]
PACING_OPTIONS = ["快节奏", "中等节奏", "慢热型", "起伏型"]
CHAPTER_WORD_OPTIONS = [2, 3, 4, 5]  # 千字

# 缺失必填字段时的问卷题目模板
MISSING_QUESTIONNAIRE = {
    "title": {
        "id": "title",
        "question": "请输入书名",
        "type": "text",
        "required": True,
    },
    "chapter_word_count": {
        "id": "chapter_word_count",
        "question": "每章目标字数（千字）？",
        "type": "select",
        "options": CHAPTER_WORD_OPTIONS,
        "required": True,
    },
    "genre": {
        "id": "genre",
        "question": "小说题材？",
        "type": "select",
        "options": GENRE_OPTIONS,
        "required": True,
    },
    "description": {
        "id": "description",
        "question": "用一句话描述你的故事（可长可短）",
        "type": "textarea",
        "placeholder": "例如：一个少年寻找失踪的妹妹的玄幻冒险故事...",
        "required": True,
    },
}


# ─── Pydantic Schemas ───

class ProjectCreate(BaseModel):
    """创建项目 - 4 必填 + 8 选填（未填则 LLM 补全）"""
    # 4 必填
    title: str = ""
    chapter_word_count: int = Field(default=0, description="章节字数（千字单位）", ge=1, le=20)
    # genre 支持多选：list[str] 或 str（逗号分隔），写入时存为逗号分隔字符串
    genre: str | list[str] = ""
    description: str = ""
    # 扩展字段
    total_chapters: int = Field(default=100, description="预计总章节数", ge=1, le=10000)
    # 8 选填
    theme: str | None = None
    tone: str | None = None
    style: str | None = None
    pacing: str | None = None
    premise: str | None = None
    protagonist: str | None = None
    antagonist: str | None = None
    supporting: str | None = None
    notes: str | None = None
    # 行为开关
    auto_commit: bool = Field(default=True, description="stage 全过后是否自动入库")


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    writing_style: str | None = None
    ai味去除程度: int | None = None
    target_word_count: int | None = None
    word_count_min: int | None = None
    word_count_max: int | None = None
    total_chapters: int | None = None


class ProjectResponse(BaseModel):
    id: str
    title: str
    description: str
    genre: str = ""
    word_count: int
    writing_style: str
    ai味去除程度: int
    target_word_count: int
    word_count_min: int
    word_count_max: int
    total_chapters: int
    chapter_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BootstrapStageInfo(BaseModel):
    id: str
    name: str
    description: str
    needs_llm: bool
    depends_on: list[str]
    status: str = "pending"  # pending / running / ok / user_filled / skipped / failed
    outputs: list[str] = []


class BootstrapResponse(BaseModel):
    """创建项目响应 - 包含 bootstrap workflow 信息"""
    project_id: str
    run_id: int | None = None
    status: str  # missing_required / submitted / running / completed / awaiting_confirm / committed / failed
    missing: list[str] = []
    questionnaire: list[dict] = []
    stages: list[BootstrapStageInfo] = []
    filled_required: list[str] = []
    filled_optional: list[str] = []
    llm_filled_count: int = 0
    auto_committed: bool = False
    error: str | None = None


# ─── Routes ───

@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: Session = Depends(get_db)):
    """获取项目列表"""
    from storage.models import Chapter
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    result = []
    for p in projects:
        ch_count = db.query(Chapter).filter(Chapter.project_id == p.id).count()
        row = {c.name: getattr(p, c.name) for c in Project.__table__.columns}
        row['chapter_count'] = ch_count
        result.append(row)
    return result


@router.post("", response_model=BootstrapResponse)
async def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """
    创建项目（统一入口）

    流程：
    1. 校验 4 必填
    2. 缺必填 → 400 返回缺失字段清单 + 问卷模板
    3. 必填齐 → 创建项目骨架 + 启动 LLM 补全 workflow

    auto_commit=true：workflow 完成后自动 commit
    auto_commit=false：workflow 完成后等待前端 /bootstrap/commit
    """
    # 1) 校验 4 必填
    missing = _check_required(data)
    if missing:
        return BootstrapResponse(
            project_id="",
            status="missing_required",
            missing=missing,
            questionnaire=[MISSING_QUESTIONNAIRE[f] for f in missing],
            filled_required=[f for f in REQUIRED_FIELDS if f not in missing],
            filled_optional=[f for f in OPTIONAL_FIELDS if getattr(data, f, None)],
        )

    # 2) 归一化 genre：list[str] → "玄幻, 都市" 字符串
    if isinstance(data.genre, list):
        genre_str = ", ".join([g.strip() for g in data.genre if g and g.strip()])
    else:
        genre_str = (data.genre or "").strip()

    # 3) 创建项目骨架（仅 4 必填 + 用户填的选填）
    project = Project(
        title=data.title.strip(),
        description=data.description.strip(),
        genre=genre_str,
        target_word_count=data.chapter_word_count * 1000,  # 千字 → 字
        word_count_min=int(data.chapter_word_count * 1000 * 0.9),
        word_count_max=int(data.chapter_word_count * 1000 * 1.1),
        total_chapters=data.total_chapters,
        writing_style=data.style or "平实",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 4) 收集用户已填选填
    user_filled = {
        f: getattr(data, f) for f in OPTIONAL_FIELDS
        if getattr(data, f, None)
    }

    # 5) 规划 workflow stages
    from llm.workflow import plan_bootstrap_stages
    stages = plan_bootstrap_stages(
        required={
            "title": data.title,
            "chapter_word_count": data.chapter_word_count,
            "genre": genre_str,
            "description": data.description,
        },
        user_filled=user_filled,
    )

    # 5) 创建 WorkflowRun
    run = WorkflowRun(
        project_id=project.id,
        name="bootstrap",
        stages=stages,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 6) 提交执行（异步：提交到线程池，立即返回 run_id）
    user_input = data.model_dump()
    from api.tasks import submit_llm_task
    submit_llm_task(
        task_type="bootstrap",
        llm_call_fn=_run_bootstrap_task,
        project_id=project.id,
        description=f"项目引导补全 [{data.title}]",
        run_id=run.id,
        user_input=user_input,
    )
    return BootstrapResponse(
        project_id=project.id,
        run_id=run.id,
        status="submitted",
        stages=[BootstrapStageInfo(**s) for s in stages],
        filled_required=REQUIRED_FIELDS,
        filled_optional=list(user_filled.keys()),
        llm_filled_count=sum(1 for s in stages if s["needs_llm"]),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field in [
        "title", "description", "writing_style", "ai味去除程度",
        "target_word_count", "word_count_min", "word_count_max", "total_chapters",
    ]:
        value = getattr(data, field)
        if value is not None:
            setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # 先清理 RAG 残留,避免新项目复用 id 时误命中旧向量数据
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        rag_cleanup = kb.delete_project_data(project_id)
    except Exception as e:
        rag_cleanup = {"error": str(e)}
    db.delete(project)
    db.commit()
    return {"status": "ok", "rag_cleanup": rag_cleanup}


@router.post("/rag/sweep-orphans")
async def sweep_rag_orphans(db: Session = Depends(get_db)):
    """清理 RAG 里的孤儿记录(指向已删除的 chapter/character/world)。

    用于：以前项目被删除但 RAG 没清,导致新项目误命中。
    """
    try:
        from rag.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        deleted = kb.sweep_orphan_records()
        total = sum(deleted.values())
        return {"status": "ok", "deleted": deleted, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/bootstrap-status")
async def get_bootstrap_status(project_id: str, db: Session = Depends(get_db)):
    """获取项目引导补全 workflow 的当前状态"""
    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.project_id == project_id, WorkflowRun.name == "bootstrap")
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No bootstrap run found for this project")
    return {
        "run_id": run.id,
        "status": run.status,
        "stages": _hydrate_stages(run.stages or [], run.stage_results or {}),
        "stage_results": run.stage_results or {},
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@router.post("/{project_id}/regenerate-settings")
async def regenerate_settings(project_id: str, db: Session = Depends(get_db)):
    """重新生成全部设定文档，逻辑与问卷创建后生成设定一致"""
    logger.info(f"[项目设置] 开始重新生成全部设定，项目ID: {project_id}")
    
    from storage.models import Project, Theme, Character, WorldEntry
    from llm.workflow import plan_bootstrap_stages
    from api.tasks import submit_llm_task

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        logger.error(f"[项目设置] 重新生成失败：项目不存在，ID: {project_id}")
        raise HTTPException(status_code=404, detail="Project not found")

    user_filled = {}

    themes = db.query(Theme).filter(Theme.project_id == project_id).all()
    for t in themes:
        if t.theme_type == "core_theme":
            user_filled["theme"] = t.title
        elif t.theme_type == "core_hook":
            user_filled["core_hook"] = t.description
        elif t.theme_type == "tone":
            user_filled["tone"] = t.description

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    for c in characters:
        if c.role == "主角":
            user_filled["protagonist"] = c.description
        elif c.role == "反派":
            user_filled["antagonist"] = c.description

    world_entries = db.query(WorldEntry).filter(WorldEntry.project_id == project_id).all()
    for w in world_entries:
        if w.category == "世界观":
            user_filled["world_setting"] = w.content
        elif w.category == "社会结构":
            user_filled["society_structure"] = w.content

    user_filled = {k: v for k, v in user_filled.items() if v}
    
    logger.info(f"[项目设置] 用户已填写的信息: {user_filled}")

    genre_str = project.genre
    if genre_str:
        genre_str = genre_str.split("/")[0].strip()

    stages = plan_bootstrap_stages(
        required={
            "title": project.title,
            "chapter_word_count": project.target_word_count,
            "genre": genre_str,
            "description": project.description or "",
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
    logger.info(f"[项目设置] 创建 WorkflowRun，ID: {run.id}")

    user_input = {
        "title": project.title,
        "chapter_word_count": project.target_word_count,
        "genre": genre_str,
        "description": project.description or "",
        "_project_id": project.id,
        "auto_commit": True,
        **user_filled,
    }
    
    submit_llm_task(
        task_type="bootstrap",
        llm_call_fn=_run_bootstrap_task,
        project_id=project.id,
        description=f"重新生成设定 [{project.title}]",
        run_id=run.id,
        user_input=user_input,
    )
    
    logger.info(f"[项目设置] bootstrap 工作流已提交执行，项目ID: {project.id}, run_id: {run.id}")

    return {
        "status": "ok",
        "project_id": project.id,
        "run_id": run.id,
        "message": "重新生成设定已启动，将在后台执行",
    }


# ─── Helpers ───

def _check_required(data: ProjectCreate) -> list[str]:
    missing = []
    if not (data.title or "").strip():
        missing.append("title")
    if not (data.chapter_word_count and data.chapter_word_count > 0):
        missing.append("chapter_word_count")
    # genre 支持 str 或 list[str]（多选题材）
    if isinstance(data.genre, list):
        genre_str = " / ".join(str(g) for g in data.genre)
    else:
        genre_str = str(data.genre or "")
    if not genre_str.strip():
        missing.append("genre")
    if not (data.description or "").strip():
        missing.append("description")
    return missing


def _merge_stage_status(stage: dict, results: dict) -> dict:
    """把 stage_results 中的状态合并到 stage 字典"""
    r = results.get(stage["id"], {})
    out = dict(stage)
    out["status"] = r.get("status", "pending")
    return out


def _hydrate_stages(stages: list[dict], results: dict) -> list[dict]:
    return [_merge_stage_status(s, results) for s in stages]


def _run_bootstrap_task(task_id: str, run_id: int, user_input: dict):
    """异步任务入口（被线程池调用）"""
    from storage.database import SessionLocal
    from llm.workflow import run_bootstrap_sync, commit_bootstrap
    from api.tasks import get_task

    db = SessionLocal()
    try:
        task = get_task(task_id)
        result = run_bootstrap_sync(run_id, user_input, db=db)
        if result["status"] == "completed" and user_input.get("auto_commit", True):
            commit_bootstrap(user_input.get("_project_id", 0), run_id, db)
        if task:
            task.status = "completed" if "fail" not in result["status"] else "failed"
            task.result = {"run_id": run_id, "workflow_status": result["status"]}
            task.progress = 100
        return result
    except Exception as e:
        task = get_task(task_id)
        if task:
            task.status = "failed"
            task.error = str(e)
        raise
    finally:
        db.close()

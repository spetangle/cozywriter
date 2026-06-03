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
    genre: str = ""
    description: str = ""
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
    async_mode: bool = Field(default=True, description="是否异步执行 workflow")


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
    id: int
    title: str
    description: str
    word_count: int
    writing_style: str
    ai味去除程度: int
    target_word_count: int
    word_count_min: int
    word_count_max: int
    total_chapters: int
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
    project_id: int
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
    return db.query(Project).order_by(Project.updated_at.desc()).all()


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
            project_id=0,
            status="missing_required",
            missing=missing,
            questionnaire=[MISSING_QUESTIONNAIRE[f] for f in missing],
            filled_required=[f for f in REQUIRED_FIELDS if f not in missing],
            filled_optional=[f for f in OPTIONAL_FIELDS if getattr(data, f, None)],
        )

    # 2) 创建项目骨架（仅 4 必填 + 用户填的选填）
    project = Project(
        title=data.title.strip(),
        description=data.description.strip(),
        target_word_count=data.chapter_word_count * 1000,  # 千字 → 字
        word_count_min=int(data.chapter_word_count * 1000 * 0.7),
        word_count_max=int(data.chapter_word_count * 1000 * 1.3),
        writing_style=data.style or "平实",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 3) 收集用户已填选填
    user_filled = {
        f: getattr(data, f) for f in OPTIONAL_FIELDS
        if getattr(data, f, None)
    }

    # 4) 规划 workflow stages
    from llm.workflow import plan_bootstrap_stages
    stages = plan_bootstrap_stages(
        required={
            "title": data.title,
            "chapter_word_count": data.chapter_word_count,
            "genre": data.genre,
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

    # 6) 提交执行
    user_input = data.model_dump()
    if data.async_mode:
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
    else:
        # 同步模式
        from llm.workflow import run_bootstrap_sync
        result = run_bootstrap_sync(run.id, user_input, db=db)
        committed = False
        if result["status"] == "completed" and data.auto_commit:
            from llm.workflow import commit_bootstrap
            commit_result = commit_bootstrap(project.id, run.id, db)
            committed = commit_result["status"] == "committed"
        return BootstrapResponse(
            project_id=project.id,
            run_id=run.id,
            status="committed" if committed else ("completed" if result["status"] == "completed" else result["status"]),
            stages=[BootstrapStageInfo(**_merge_stage_status(s, run.stage_results or {})) for s in stages],
            filled_required=REQUIRED_FIELDS,
            filled_optional=list(user_filled.keys()),
            llm_filled_count=sum(1 for s in stages if s["needs_llm"]),
            auto_committed=committed,
            error=result.get("error") if result["status"] == "failed" else None,
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
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
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "ok"}


@router.get("/{project_id}/bootstrap-status")
async def get_bootstrap_status(project_id: int, db: Session = Depends(get_db)):
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


# ─── Helpers ───

def _check_required(data: ProjectCreate) -> list[str]:
    missing = []
    if not (data.title or "").strip():
        missing.append("title")
    if not (data.chapter_word_count and data.chapter_word_count > 0):
        missing.append("chapter_word_count")
    if not (data.genre or "").strip():
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

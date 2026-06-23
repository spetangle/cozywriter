"""创意问卷 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.creative_questionnaire import CreativeQuestionnaire, QUESTIONNAIRE_QUESTIONS


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
    answers: dict
    questionnaire_type: str
    status: str
    created_project_id: str | None
    created_at: object
    updated_at: object

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("/questions")
async def get_questions():
    """获取预设问卷题目（供前端渲染）"""
    return QUESTIONNAIRE_QUESTIONS


@router.get("", response_model=list[QuestionnaireResponse])
async def list_questionnaires(db: Session = Depends(get_db)):
    """获取所有问卷"""
    qs = db.query(CreativeQuestionnaire).order_by(CreativeQuestionnaire.updated_at.desc()).all()
    return qs


@router.post("", response_model=QuestionnaireResponse)
async def create_questionnaire(data: QuestionnaireCreate, db: Session = Depends(get_db)):
    """创建问卷（开始新问卷）"""
    q = CreativeQuestionnaire(
        title=data.title,
        answers=data.answers,
        status="draft",
    )
    db.add(q)
    db.commit()
    db.refresh(q)
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


@router.post("/{q_id}/build-project", response_model=dict)
async def build_project_from_questionnaire(q_id: int, db: Session = Depends(get_db)):
    """
    根据问卷答案创建小说项目

    将问卷答案中的信息自动填入项目设置：
    - 类型/基调/风格 → Project.writing_style
    - 总字数目标根据 target_length 估算
    - 核心主题 → Theme
    - 主角/反派设定 → Character
    - 世界观 → WorldEntry
    """
    from storage.models import Project, Theme, Character, WorldEntry

    q = db.query(CreativeQuestionnaire).filter(CreativeQuestionnaire.id == q_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    a = q.answers or {}

    # 估算总字数
    length_map = {
        "短篇（3-10万字）": 50000,
        "中篇（10-30万字）": 200000,
        "长篇（30-100万字）": 600000,
        "超长篇（100万字以上）": 1200000,
    }
    est_total = length_map.get(a.get("target_length", ""), 300000)
    est_chapter = est_total // 30  # 假设30章

    # 风格映射
    style_map = {
        "优美": "优美", "平实": "平实", "诗意": "诗意",
        "幽默": "幽默", "冷峻": "冷峻",
    }

    # 创建项目
    project = Project(
        title=a.get("theme", "未命名小说") or "未命名小说",
        description=a.get("summary", ""),
        writing_style=style_map.get(a.get("style", ""), "平实"),
        target_word_count=est_chapter,
        word_count_min=int(est_chapter * 0.7),
        word_count_max=int(est_chapter * 1.3),
        total_chapters=30,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 创建核心主题
    theme_text = a.get("theme", "")
    if theme_text:
        t = Theme(
            project_id=project.id,
            theme_type="core_theme",
            title=theme_text,
            description=f"基调：{a.get('tone', '')}",
        )
        db.add(t)

    # 创建主角
    protagonist_text = a.get("protagonist", "")
    if protagonist_text:
        c = Character(
            project_id=project.id,
            name="主角",  # 名字待定
            role="主角",
            description=protagonist_text,
        )
        db.add(c)

    # 创建世界观
    premise_text = a.get("premise", "")
    if premise_text:
        w = WorldEntry(
            project_id=project.id,
            category="背景设定",
            title="世界观背景",
            content=premise_text,
        )
        db.add(w)

    # 标记问卷状态
    q.status = "completed"
    q.created_project_id = project.id
    db.commit()

    return {
        "project_id": project.id,
        "project_title": project.title,
        "message": "项目创建成功",
    }

"""全文评审 API - 支持分批评审超长文本"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import FullReviewSession, Chapter, Project, Character, Theme
from llm.factory import LLMFactory
from logger import logger
import time
import json
import re

router = APIRouter(prefix="/api/full-reviews", tags=["全文评审"])

# 每批最大字符数（根据模型上下文窗口调整，DeepSeek 约 64K，保守取 20000）
BATCH_MAX_CHARS = 20000


# ─── Schemas ───

class FullReviewCreate(BaseModel):
    project_id: str


class FullReviewResponse(BaseModel):
    id: int
    project_id: str
    score_story: float
    score_character: float
    score_prose: float
    score_theme: float
    score_market: float
    rationale_story: str
    rationale_character: str
    rationale_prose: str
    rationale_theme: str
    rationale_market: str
    overall_score: float
    overall_critique: str
    improvement_suggestions: list
    total_chapters: int
    total_words: int
    batch_count: int
    created_at: str | None = None


class FullReviewListResponse(BaseModel):
    id: int
    project_id: str
    overall_score: float
    total_chapters: int
    total_words: int
    created_at: str | None = None


# ─── 评审 Prompt ───

FULL_REVIEW_SYSTEM = """你是一位资深的网络文学评审专家，擅长从网文读者的角度分析作品的优缺点。

请对以下小说内容进行专业评审，从五个维度进行评分（每项0-10分）并给出详细的评审依据。

【评审维度说明】
1. 故事与情节（Story & Plot）
   - 核心冲突与悬念：是否有明确的主线冲突？悬念设置是否合理？
   - 情节节奏：起承转合是否自然？节奏是否拖沓或仓促？
   - 逻辑自洽性：故事内部是否有明显的逻辑漏洞？
   - 结构完整性：开篇是否抓人，中段是否充实，结尾是否圆满？

2. 人物塑造（Characterization）
   - 立体度与辨识度：角色是否有鲜明的性格标签？是否避免脸谱化？
   - 人物弧光：主角是否有成长或转变？是否有情节支撑？
   - 人物关系网：角色互动是否真实、有张力？
   - 代入感与共情力：读者能否理解并共情角色？

3. 文笔与语言（Prose & Language）
   - 语言风格适配：文风是否与题材契合？
   - 画面感与细节描写：是否善用"展示"而非"讲述"？
   - 对话质量：对话是否推动剧情或揭示人物内心？
   - 阅读流畅度：语句是否通顺？是否有语病或错别字？

4. 主题与立意（Theme & Depth）
   - 核心主旨的清晰度：作品是否有明确的表达内核？
   - 思想深度与独特性：立意是否落入俗套？
   - 价值观导向：作品传递的价值观是否健康？
   - 情感共鸣：主题是否能触动读者内心？

5. 创新与市场潜力（Innovation & Marketability）
   - 题材创新：是否有新颖的设定或叙事手法？
   - 类型元素运用：是否掌握了该类型的核心爽点？
   - 目标受众匹配度：是否精准击中目标读者需求？
   - IP改编潜力：是否具备影视、动漫等衍生开发潜质？

【小说信息】
标题：{title}
题材：{genre}
总字数：{total_words}
章节数：{total_chapters}

【角色概览】
{character_summary}

【主题概览】
{theme_summary}

【正文内容】
{content}

请返回JSON格式：
{
  "score_story": 8.5,
  "rationale_story": "评分依据...",
  "score_character": 7.5,
  "rationale_character": "评分依据...",
  "score_prose": 8.0,
  "rationale_prose": "评分依据...",
  "score_theme": 7.0,
  "rationale_theme": "评分依据...",
  "score_market": 8.0,
  "rationale_market": "评分依据...",
  "overall_critique": "总体评价...",
  "improvement_suggestions": ["改进建议1", "改进建议2"]
}
"""

SUMMARY_SYSTEM = """你是一位资深的网络文学评审专家。

以下是小说全文分批评审的结果，请汇总生成最终的评审报告。

【分批评审结果】
{batch_results}

请返回JSON格式：
{
  "score_story": 8.5,
  "rationale_story": "综合评分依据...",
  "score_character": 7.5,
  "rationale_character": "综合评分依据...",
  "score_prose": 8.0,
  "rationale_prose": "综合评分依据...",
  "score_theme": 7.0,
  "rationale_theme": "综合评分依据...",
  "score_market": 8.0,
  "rationale_market": "综合评分依据...",
  "overall_critique": "总体评价...",
  "improvement_suggestions": ["改进建议1", "改进建议2"]
}
"""


# ─── 辅助函数 ───

def _get_full_content(db: Session, project_id: str) -> tuple[str, int, int]:
    """获取项目全文内容，返回 (内容, 章节数, 总字数)"""
    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.content != "",
        Chapter.content.isnot(None)
    ).order_by(Chapter.order).all()
    
    if not chapters:
        return "", 0, 0
    
    parts = []
    for ch in chapters:
        parts.append(f"\n\n【第{ch.order + 1}章 {ch.title}】\n{ch.content}")
    
    full_content = "".join(parts)
    total_words = sum(ch.word_count or len(ch.content) for ch in chapters)
    
    return full_content, len(chapters), total_words


def _get_character_summary(db: Session, project_id: str) -> str:
    """获取角色概览"""
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).limit(10).all()
    
    if not characters:
        return "（无角色信息）"
    
    lines = []
    for ch in characters:
        role = ch.role or "未知"
        name = ch.name or "未命名"
        desc = (ch.profile_text or "")[:100]
        lines.append(f"- {name}（{role}）：{desc}")
    
    return "\n".join(lines)


def _get_theme_summary(db: Session, project_id: str) -> str:
    """获取主题概览"""
    themes = db.query(Theme).filter(
        Theme.project_id == project_id
    ).limit(5).all()
    
    if not themes:
        return "（无主题信息）"
    
    lines = []
    for t in themes:
        lines.append(f"- {t.name or '未命名'}：{t.description or ''}")
    
    return "\n".join(lines)


def _split_content(content: str, max_chars: int = BATCH_MAX_CHARS) -> list[str]:
    """将内容按章节切分成批次，尽量保持章节完整性"""
    chapters = re.split(r'\n\n【第\d+章', content)
    batches = []
    current_batch = ""
    
    # 重新组合章节标题
    chapter_titles = re.findall(r'\n\n【第\d+章[^】]*】', content)
    
    for i, chapter in enumerate(chapters[1:], 0):  # 跳过第一个空元素
        full_chapter = chapter_titles[i] + chapter if i < len(chapter_titles) else chapter
        
        if len(current_batch) + len(full_chapter) > max_chars:
            if current_batch:
                batches.append(current_batch)
            current_batch = full_chapter
        else:
            current_batch += full_chapter
    
    if current_batch:
        batches.append(current_batch)
    
    return batches


def _parse_review_json(raw: str) -> dict:
    """解析LLM返回的JSON"""
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    return {}


def _calculate_overall_score(scores: dict) -> float:
    """计算综合评分（加权平均）"""
    weights = {
        "score_story": 0.25,
        "score_character": 0.20,
        "score_prose": 0.20,
        "score_theme": 0.15,
        "score_market": 0.20,
    }
    
    total = 0.0
    for key, weight in weights.items():
        total += scores.get(key, 0) * weight
    
    return round(total, 1)


# ─── 异步评审任务 ───

def _async_full_review_task(task_id: str, project_id: str):
    """异步执行全文评审"""
    from storage.database import SessionLocal
    from api.tasks import get_task
    
    db = SessionLocal()
    try:
        task = get_task(task_id)
        task.progress = 10
        task.status = "processing"
        
        # 获取项目信息
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("Project not found")
        
        # 获取全文内容
        full_content, total_chapters, total_words = _get_full_content(db, project_id)
        if not full_content:
            raise ValueError("No chapter content found")
        
        task.progress = 20
        
        # 获取角色和主题概览
        character_summary = _get_character_summary(db, project_id)
        theme_summary = _get_theme_summary(db, project_id)
        
        # 分批评审
        batches = _split_content(full_content)
        batch_results = []
        
        llm = LLMFactory.create(db=db)
        
        for i, batch in enumerate(batches):
            task.progress = 20 + (i / len(batches)) * 50
            logger.info(f"[FullReview] 批次 {i+1}/{len(batches)}, 字数: {len(batch)}")
            
            system_prompt = FULL_REVIEW_SYSTEM.format(
                title=project.title,
                genre=project.genre or "未知",
                total_words=total_words,
                total_chapters=total_chapters,
                character_summary=character_summary,
                theme_summary=theme_summary,
                content=batch[:BATCH_MAX_CHARS]
            )
            
            raw = llm.generate(
                prompt="请根据上述内容进行评审，返回JSON格式的评审结果。",
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.3,
                task_type="full_review_batch"
            )
            
            result = _parse_review_json(raw)
            if result:
                batch_results.append(result)
        
        task.progress = 80
        
        # 汇总评审结果
        if len(batch_results) > 1:
            summary_prompt = SUMMARY_SYSTEM.format(
                batch_results=json.dumps(batch_results, ensure_ascii=False, indent=2)
            )
            raw = llm.generate(
                prompt="请汇总上述分批评审结果，生成最终评审报告。",
                system_prompt=summary_prompt,
                max_tokens=2048,
                temperature=0.3,
                task_type="full_review_summary"
            )
            final_result = _parse_review_json(raw)
        elif batch_results:
            final_result = batch_results[0]
        else:
            final_result = {}
        
        # 计算综合评分
        overall_score = _calculate_overall_score(final_result)
        
        # 保存评审结果
        session = FullReviewSession(
            project_id=project_id,
            score_story=final_result.get("score_story", 0),
            score_character=final_result.get("score_character", 0),
            score_prose=final_result.get("score_prose", 0),
            score_theme=final_result.get("score_theme", 0),
            score_market=final_result.get("score_market", 0),
            rationale_story=final_result.get("rationale_story", ""),
            rationale_character=final_result.get("rationale_character", ""),
            rationale_prose=final_result.get("rationale_prose", ""),
            rationale_theme=final_result.get("rationale_theme", ""),
            rationale_market=final_result.get("rationale_market", ""),
            overall_score=overall_score,
            overall_critique=final_result.get("overall_critique", ""),
            improvement_suggestions=final_result.get("improvement_suggestions", []),
            total_chapters=total_chapters,
            total_words=total_words,
            batch_count=len(batches),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
        task.result = {
            "id": session.id,
            "project_id": project_id,
            "overall_score": overall_score,
            "total_chapters": total_chapters,
            "total_words": total_words,
        }
        task.status = "completed"
        task.progress = 100
        task.completed_at = time.time()
        
        logger.info(f"[FullReview] 评审完成 session={session.id} score={overall_score}")
        
    except Exception as e:
        task = get_task(task_id)
        if task:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
        logger.error(f"[FullReview] 评审失败: {e}")
    finally:
        db.close()


# ─── Routes ───

@router.post("", response_model=dict)
async def create_full_review(
    data: FullReviewCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """提交全文评审任务（异步）"""
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 检查是否有章节内容
    chapters = db.query(Chapter).filter(
        Chapter.project_id == data.project_id,
        Chapter.content != "",
        Chapter.content.isnot(None)
    ).count()
    
    if chapters == 0:
        raise HTTPException(status_code=400, detail="No chapter content to review")
    
    # 提交异步任务
    from api.tasks import submit_llm_task
    task = submit_llm_task(
        task_type="full_review",
        llm_call_fn=_async_full_review_task,
        project_id=data.project_id,
        description=f"全文评审 {project.title}",
    )
    
    return {
        "task_id": task.id,
        "status": "submitted",
        "total_chapters": chapters,
    }


@router.get("/{review_id}", response_model=FullReviewResponse)
async def get_full_review(
    review_id: int,
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取全文评审结果"""
    session = db.query(FullReviewSession).filter(
        FullReviewSession.id == review_id,
        FullReviewSession.project_id == project_id,
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Full review not found")
    
    return FullReviewResponse(
        id=session.id,
        project_id=session.project_id,
        score_story=session.score_story,
        score_character=session.score_character,
        score_prose=session.score_prose,
        score_theme=session.score_theme,
        score_market=session.score_market,
        rationale_story=session.rationale_story,
        rationale_character=session.rationale_character,
        rationale_prose=session.rationale_prose,
        rationale_theme=session.rationale_theme,
        rationale_market=session.rationale_market,
        overall_score=session.overall_score,
        overall_critique=session.overall_critique,
        improvement_suggestions=session.improvement_suggestions or [],
        total_chapters=session.total_chapters,
        total_words=session.total_words,
        batch_count=session.batch_count,
        created_at=session.created_at.isoformat() if session.created_at else None,
    )


@router.get("/project/{project_id}", response_model=list[FullReviewListResponse])
async def list_full_reviews(
    project_id: str,
    db: Session = Depends(get_db),
):
    """列出项目下所有全文评审"""
    sessions = db.query(FullReviewSession).filter(
        FullReviewSession.project_id == project_id
    ).order_by(FullReviewSession.created_at.desc()).all()
    
    return [
        FullReviewListResponse(
            id=s.id,
            project_id=s.project_id,
            overall_score=s.overall_score,
            total_chapters=s.total_chapters,
            total_words=s.total_words,
            created_at=s.created_at.isoformat() if s.created_at else None,
        )
        for s in sessions
    ]
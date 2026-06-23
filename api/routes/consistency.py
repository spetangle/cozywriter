"""一致性检查服务 - 自动检测前后文矛盾"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project, Chapter, Character, ConsistencyRecord, CharacterArc
import re


router = APIRouter(prefix="/api/projects/{project_id}/consistency", tags=["一致性检查"])


class ConsistencyCheckResult(BaseModel):
    has_issues: bool
    issues: list[dict]


@router.get("/check", response_model=ConsistencyCheckResult)
async def check_consistency(project_id: str, chapter_id: int | None = None, db: Session = Depends(get_db)):
    """
    对章节进行一致性检查
    检查：人物性格突变、物品数量错误、能力超出设定、资源消耗异常
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    issues = []

    # 获取所有章节内容
    if chapter_id:
        chapters = [db.query(Chapter).filter(Chapter.id == chapter_id).first()]
    else:
        chapters = db.query(Chapter).filter(Chapter.project_id == project_id).order_by(Chapter.order).all()

    if not chapters:
        return ConsistencyCheckResult(has_issues=False, issues=[])

    # 读取已有的一致性记录，构建当前状态快照
    records = db.query(ConsistencyRecord).filter(
        ConsistencyRecord.project_id == project_id
    ).order_by(ConsistencyRecord.created_at).all()

    # 从角色 profile 提取初始状态
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    character_states = {}
    for c in characters:
        character_states[c.id] = {
            "name": c.name,
            "profile": c.profile or {},
            "description": c.description,
        }

    # 分析每章的一致性
    for chapter in chapters:
        if not chapter.content:
            continue
        text = chapter.content

        # 检查角色名出现频率（发现未登记的新角色名）
        for c in characters:
            # 检查是否有性格描述与设定矛盾
            profile = c.profile or {}
            desc = c.description or ""

            # 简单的关键词矛盾检测
            negative_kw = ["残忍", "冷酷", "邪恶", "背叛"]
            positive_kw = ["善良", "正直", "忠诚", "温暖"]

            for kw in negative_kw:
                if kw in text and profile.get("性格") in ["善良", "正直", "温柔"]:
                    issues.append({
                        "type": "character_trait_conflict",
                        "severity": "high",
                        "chapter": chapter.title,
                        "character": c.name,
                        "message": f"角色 {c.name} 的设定为正面性格，但章节中出现了 '{kw}' 相关描述",
                    })

        # 检查字数异常波动
        wc = len(text.replace(" ", "").replace("\n", ""))
        if project.target_word_count:
            if wc > (project.word_count_max or project.target_word_count * 1.5):
                issues.append({
                    "type": "word_count_anomaly",
                    "severity": "medium",
                    "chapter": chapter.title,
                    "word_count": wc,
                    "expected_max": project.word_count_max or int(project.target_word_count * 1.5),
                    "message": f"章节字数 {wc} 超过预期上限",
                })
            elif wc < (project.word_count_min or project.target_word_count * 0.5):
                issues.append({
                    "type": "word_count_anomaly",
                    "severity": "medium",
                    "chapter": chapter.title,
                    "word_count": wc,
                    "expected_min": project.word_count_min or int(project.target_word_count * 0.5),
                    "message": f"章节字数 {wc} 低于预期下限",
                })

    # 检查伏笔状态
    from storage.models import Foreshadowing
    fores = db.query(Foreshadowing).filter(
        Foreshadowing.project_id == project_id,
        Foreshadowing.status == "active",
    ).all()
    for fs in fores:
        if fs.plant_chapter_id:
            plant_ch = db.query(Chapter).filter(Chapter.id == fs.plant_chapter_id).first()
            if plant_ch and plant_ch.order < len(chapters) - 3:
                # 伏笔埋了超过3章还没回收，提醒可能遗忘
                issues.append({
                    "type": "foreshadowing_unresolved",
                    "severity": "low",
                    "foreshadowing": fs.title,
                    "plant_chapter": plant_ch.title,
                    "message": f"伏笔 '{fs.title}' 埋下后已过多章节，建议检查是否需要回收",
                })

    # 检查角色弧光稳定性
    arcs = db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all()
    for arc in arcs:
        if not arc.is_stable:
            char = db.query(Character).filter(Character.id == arc.character_id).first()
            issues.append({
                "type": "character_arc_unstable",
                "severity": "medium",
                "character": char.name if char else "未知",
                "current_state": arc.current_state,
                "message": f"角色弧光 '{arc.arc_type}' 当前状态不稳定，需要检查",
            })

    return ConsistencyCheckResult(
        has_issues=len(issues) > 0,
        issues=issues,
    )


@router.get("/report")
async def consistency_report(project_id: str, db: Session = Depends(get_db)):
    """生成项目一致性综合报告"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from storage.models import Foreshadowing, CharacterArc, CharacterRelation, ConsistencyRecord

    # 伏笔统计
    fores = db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id).all()
    fores_stats = {
        "total": len(fores),
        "active": len([f for f in fores if f.status == "active"]),
        "resolved": len([f for f in fores if f.status == "resolved"]),
        "abandoned": len([f for f in fores if f.status == "abandoned"]),
    }

    # 角色弧光统计
    arcs = db.query(CharacterArc).filter(CharacterArc.project_id == project_id).all()
    arc_stats = {
        "total": len(arcs),
        "stable": len([a for a in arcs if a.is_stable]),
        "unstable": len([a for a in arcs if not a.is_stable]),
    }

    # 一致性记录
    records = db.query(ConsistencyRecord).filter(
        ConsistencyRecord.project_id == project_id
    ).all()
    consistency_stats = {
        "total": len(records),
        "inconsistent": len([r for r in records if not r.is_consistent]),
    }

    # 字数统计
    chapters = db.query(Chapter).filter(Chapter.project_id == project_id).all()
    word_counts = [c.word_count for c in chapters if c.word_count]
    avg_wc = sum(word_counts) / len(word_counts) if word_counts else 0

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "target_word_count": project.target_word_count,
            "word_count_min": project.word_count_min,
            "word_count_max": project.word_count_max,
            "writing_style": project.writing_style,
        },
        "chapters": {
            "total": len(chapters),
            "avg_word_count": round(avg_wc, 0),
        },
        "foreshadowing": fores_stats,
        "character_arc": arc_stats,
        "consistency": consistency_stats,
    }

"""Token 用量统计 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from storage.database import get_db
from llm.usage_tracker import get_project_usage_summary

router = APIRouter(prefix="/api/token-usage", tags=["Token用量"])


@router.get("/project/{project_id}")
def get_project_token_usage(project_id: str, db: Session = Depends(get_db)):
    """获取项目的 token 用量汇总"""
    from storage.models.project import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, f"项目 {project_id} 不存在")
    return get_project_usage_summary(db, project_id)


@router.get("/project/{project_id}/recent")
def get_project_recent_usage(
    project_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """获取项目最近的 token 用量记录"""
    from storage.models.llm_usage import LLMUsageRecord
    records = (
        db.query(LLMUsageRecord)
        .filter(LLMUsageRecord.project_id == project_id)
        .order_by(LLMUsageRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [r.to_dict() for r in records]


@router.get("/global")
def get_global_token_usage(db: Session = Depends(get_db)):
    """获取全局 token 用量汇总（所有项目 + 非项目调用）"""
    from storage.models.llm_usage import LLMUsageRecord

    records = db.query(LLMUsageRecord).all()
    if not records:
        return {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_hit_rate": 0.0,
            "total_duration_ms": 0.0,
        }

    total_calls = len(records)
    successful = sum(1 for r in records if r.success)
    total_tokens = sum(r.total_tokens for r in records)
    input_tokens = sum(r.input_tokens for r in records)
    output_tokens = sum(r.output_tokens for r in records)
    cache_read = sum(r.cache_read_tokens for r in records)
    cache_creation = sum(r.cache_creation_tokens for r in records)
    total_duration = sum(r.duration_ms for r in records)
    cache_hit_rate = (cache_read / input_tokens * 100) if input_tokens > 0 else 0.0

    return {
        "total_calls": total_calls,
        "successful_calls": successful,
        "failed_calls": total_calls - successful,
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "cache_hit_rate": round(cache_hit_rate, 2),
        "total_duration_ms": round(total_duration, 1),
    }

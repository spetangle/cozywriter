"""LLM Token 用量采集 & 汇总查询

设计要点：
- record_llm_usage() 用独立 DB session 写入，不影响调用方事务
- 任何异常都被吞掉（不能让统计逻辑导致主业务失败）
- 各 provider 在 generate() 成功/失败后调用
- llm_call_id = {task_id}#{seq}，实现主任务ID+子ID的层级追踪
"""
import threading
import uuid
from logger import logger

# 每个 task_id 对应的自增计数器，用于生成 llm_call_id
_task_call_counters: dict[str, int] = {}
_counter_lock = threading.Lock()


def generate_llm_call_id(task_id: str | None = None) -> str:
    """为一次 LLM 调用生成唯一 ID

    格式：
    - 有 task_id:  "{task_id}#{seq:03d}"  例: d14ae9ab#001
    - 无 task_id:  "standalone_{uuid8}"  例: standalone_a3f2c1d4
    """
    if task_id:
        with _counter_lock:
            seq = _task_call_counters.get(task_id, 0) + 1
            _task_call_counters[task_id] = seq
        return f"{task_id}#{seq:03d}"
    else:
        return f"standalone_{uuid.uuid4().hex[:8]}"


def record_llm_usage(
    provider: str,
    model: str,
    task_type: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    duration_ms: float = 0.0,
    success: bool = True,
    error: str = "",
    project_id: str | None = None,
    task_id: str | None = None,
    llm_call_id: str | None = None,
):
    """记录一次 LLM 调用的 token 用量到数据库

    所有异常被吞掉，仅写 log，不影响主业务流程。
    """
    try:
        from storage.database import SessionLocal
        from storage.models.llm_usage import LLMUsageRecord

        if not total_tokens:
            total_tokens = input_tokens + output_tokens

        db = SessionLocal()
        try:
            record = LLMUsageRecord(
                project_id=project_id,
                task_id=task_id,
                llm_call_id=llm_call_id,
                provider=provider,
                model=model,
                task_type=task_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
                duration_ms=duration_ms,
                success=1 if success else 0,
                error=(error or "")[:512],
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[usage_tracker] 记录 token 用量失败（不影响主流程）: {e}")


def extract_usage_from_anthropic_response(response) -> dict:
    """从 Anthropic SDK 响应中提取 token 用量

    Anthropic / MiniMax / MiMo / DeepSeek(Anthropic兼容) 都用这个。
    usage 字段：input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def extract_usage_from_openai_response(response) -> dict:
    """从 OpenAI SDK 响应中提取 token 用量

    OpenAI / DeepSeek(OpenAI兼容) 都用这个。
    usage 字段：prompt_tokens, completion_tokens, total_tokens
    DeepSeek 额外：prompt_cache_hit_tokens, prompt_cache_miss_tokens
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    result = {
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }

    # DeepSeek 特有的缓存字段
    cache_hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
    cache_miss = getattr(usage, "prompt_cache_miss_tokens", 0) or 0
    if cache_hit or cache_miss:
        result["cache_read_tokens"] = cache_hit
        result["cache_creation_tokens"] = cache_miss

    return result


# ─── 汇总查询 ───

def get_project_usage_summary(db, project_id: str) -> dict:
    """获取项目的 token 用量汇总"""
    from storage.models.llm_usage import LLMUsageRecord
    from sqlalchemy import func

    records = db.query(LLMUsageRecord).filter(
        LLMUsageRecord.project_id == project_id
    ).all()

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
            "by_provider": {},
            "by_task_type": {},
            "by_model": {},
        }

    total_calls = len(records)
    successful = sum(1 for r in records if r.success)
    total_tokens = sum(r.total_tokens for r in records)
    input_tokens = sum(r.input_tokens for r in records)
    output_tokens = sum(r.output_tokens for r in records)
    cache_read = sum(r.cache_read_tokens for r in records)
    cache_creation = sum(r.cache_creation_tokens for r in records)
    total_duration = sum(r.duration_ms for r in records)

    # 缓存命中率 = cache_read_tokens / input_tokens
    cache_hit_rate = (cache_read / input_tokens * 100) if input_tokens > 0 else 0.0

    # 按 provider 分组
    by_provider: dict[str, dict] = {}
    for r in records:
        key = r.provider
        if key not in by_provider:
            by_provider[key] = {"calls": 0, "total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        by_provider[key]["calls"] += 1
        by_provider[key]["total_tokens"] += r.total_tokens
        by_provider[key]["input_tokens"] += r.input_tokens
        by_provider[key]["output_tokens"] += r.output_tokens

    # 按 task_type 分组
    by_task_type: dict[str, dict] = {}
    for r in records:
        key = r.task_type
        if key not in by_task_type:
            by_task_type[key] = {"calls": 0, "total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        by_task_type[key]["calls"] += 1
        by_task_type[key]["total_tokens"] += r.total_tokens
        by_task_type[key]["input_tokens"] += r.input_tokens
        by_task_type[key]["output_tokens"] += r.output_tokens

    # 按 model 分组
    by_model: dict[str, dict] = {}
    for r in records:
        key = r.model
        if key not in by_model:
            by_model[key] = {"calls": 0, "total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        by_model[key]["calls"] += 1
        by_model[key]["total_tokens"] += r.total_tokens
        by_model[key]["input_tokens"] += r.input_tokens
        by_model[key]["output_tokens"] += r.output_tokens

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
        "by_provider": by_provider,
        "by_task_type": by_task_type,
        "by_model": by_model,
    }

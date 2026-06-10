"""日志模块 - 统一配置全系统日志（输出到 console + 按天滚动文件）

设计原则：
- console：INFO 级，简短格式，运营日常查看
- file：DEBUG 级，完整格式（含文件名+行号），含 LLM 完整 prompt/response
- LLM payload 是否入 file 受环境变量 LOG_LLM_PAYLOAD 控制（默认 1）
  未来想降低 log 体量时，把 LOG_LLM_PAYLOAD=0 即可，调用方代码不动
"""
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
import json as _json


LOG_DIR = Path("./data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ─── 配置常量 ───
# 是否把 LLM 的完整 prompt / response 入 log 文件
# 默认 1（开）；改成 0 时，4 个 provider 调用的 log_llm_payload() 会变成 no-op
LOG_LLM_PAYLOAD = os.getenv("LOG_LLM_PAYLOAD", "1").lower() in ("1", "true", "yes")


# 用模块级缓存避免重复 handler
_configured_loggers: set[int] = set()


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建并返回一个配置好的 logger（idempotent：同一 logger 不会重复添加 handler）"""
    logger = logging.getLogger(name)
    # 关键修复：logger 级别设 DEBUG，DEBUG 消息才会被生成并分发到 handler
    # （之前 setLevel(level=INFO) 导致 logger.debug() 在源头就被过滤，
    #   LLM-PAYLOAD 块永远到不了 file handler，问题排查时看不到完整 prompt/response）
    # console handler 仍按 level（默认 INFO）过滤，所以终端不会刷屏 DEBUG
    logger.setLevel(logging.DEBUG)

    # 已配置过 → 直接返回
    if id(logger) in _configured_loggers:
        return logger

    # 控制台 handler（彩色 / 简化格式）
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    # 文件 handler（按天滚动，DEBUG 级全量记录）
    log_file = LOG_DIR / f"cozywriter_{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # 防止日志冒泡到 root logger（避免重复输出）
    logger.propagate = False

    _configured_loggers.add(id(logger))
    return logger


# 全局 logger 实例
logger = setup_logger("cozywriter")


def log_llm_call(provider: str, model: str, task_type: str, duration_ms: float, success: bool, error: str = ""):
    """专门记录 LLM 调用日志"""
    status = "OK" if success else f"FAIL: {error}"
    logger.info(f"[LLM] provider={provider} model={model} task={task_type} duration={duration_ms:.0f}ms status={status}")


def log_llm_request(task_type: str, prompt_preview: str, system_prompt_preview: str):
    """记录 LLM 请求详情（脱敏）"""
    prompt_short = prompt_preview[:200] + "..." if len(prompt_preview) > 200 else prompt_preview
    system_short = system_prompt_preview[:100] + "..." if len(system_prompt_preview) > 100 else system_prompt_preview
    logger.info(f"[LLM-REQ] task={task_type} prompt={prompt_short}")
    logger.debug(f"[LLM-REQ] task={task_type} system={system_short}")


def log_api_request(endpoint: str, method: str, duration_ms: float, status_code: int):
    """记录 API 请求"""
    logger.info(f"[API] {method} {endpoint} duration={duration_ms:.0f}ms status={status_code}")


def log_task_start(task_id: str, task_type: str, description: str):
    """记录异步任务启动"""
    logger.info(f"[TASK] id={task_id} type={task_type} start={description}")


def log_task_done(task_id: str, task_type: str, duration_s: float):
    """记录异步任务完成"""
    logger.info(f"[TASK] id={task_id} type={task_type} done duration={duration_s:.1f}s")


# ─── LLM payload 完整记录 ───
# 用途：把 LLM 调用的 prompt / response / metadata 完整入 log 文件
# 等级：用 DEBUG，console 默认不显示，但 file handler 是 DEBUG 全量
# 关闭：环境变量 LOG_LLM_PAYLOAD=0 → 整个函数变 no-op，4 个 provider 调用点无需改

def log_llm_payload(
    provider: str,
    model: str,
    task_type: str,
    system_prompt: str,
    user_prompt: str,
    response_text: str,
    duration_ms: float = 0.0,
    success: bool = True,
    error: str = "",
    extra: dict | None = None,
):
    """
    完整记录一次 LLM 调用（prompt + response + metadata）。

    输出原则：
    1. **File** （详细）: 以多行 JSON 块写入文件，含完整 system_prompt / user_prompt / response_text。
       便于事后排查问题。每个块首尾有明确分隔符，grep / less 可快速定位。
    2. **Console** （摘要）: INFO 级一行简短提示 + path，告知完整 payload 位置。
       不刷屏 console（避免长 prompt/response 占据终端）。

    Args:
        provider:        anthropic / openai / ollama / minimax
        model:           模型名
        task_type:       generate / review / stage_1_base / ...
        system_prompt:   完整 system prompt（可能很长）
        user_prompt:     完整 user prompt
        response_text:   LLM 原始返回（含 thinking / 包装等）
        duration_ms:     调用耗时
        success:         True=成功 / False=失败
        error:           失败原因
        extra:           额外字段（如 retry_count、stop_reason、usage 等）
    """
    if not LOG_LLM_PAYLOAD:
        return  # 全局开关关闭 → no-op，调用点无需改

    payload = {
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "duration_ms": round(duration_ms, 1),
        "success": success,
        "error": error,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response_text": response_text,
        "extra": extra or {},
        # 统计：方便排查超长 prompt
        "prompt_chars": len(system_prompt) + len(user_prompt),
        "response_chars": len(response_text),
    }

    # ── 1) 完整 payload 写文件（DEBUG 级，多行格式） ──
    try:
        payload_str = _json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        # 极端情况：prompt/response 不是 JSON-serializable（基本不可能，str 一定 OK）
        payload_str = f"<json-failed: {e}> payload={payload!r}"

    # 块首尾加明显分隔符，方便 grep / less 定位
    sep = "=" * 80
    block = (
        f"\n{sep}\n"
        f"  [LLM-PAYLOAD] provider={provider} model={model} task={task_type} "
        f"success={success} duration={duration_ms:.0f}ms\n"
        f"{sep}\n"
        f"{payload_str}\n"
        f"{sep}\n"
    )
    logger.debug(block)

    # ── 2) Console 摘要（INFO 级，一行 + 路径提示） ──
    # 不在 console 上贴长 prompt/response（会刷屏），只提示：
    # - 调用的关键信息（provider/model/task/success）
    # - 完整 payload 写到哪个文件
    status_mark = "✓" if success else "✗"
    log_path = LOG_DIR / f"cozywriter_{datetime.now():%Y%m%d}.log"
    logger.info(
        f"[LLM-PAYLOAD] {status_mark} {provider}/{model} task={task_type} "
        f"success={success} "
        f"prompt={payload['prompt_chars']}ch response={payload['response_chars']}ch "
        f"→ 完整内容已写入 log: {log_path}"
    )

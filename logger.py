"""日志模块 - 统一配置全系统日志"""
import logging
import sys
from pathlib import Path
from datetime import datetime


LOG_DIR = Path("./data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建并返回一个配置好的 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台 handler（彩色）
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    # 文件 handler（按天滚动）
    log_file = LOG_DIR / f"cozywriter_{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

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

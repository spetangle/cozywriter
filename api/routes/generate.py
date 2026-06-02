"""文本生成 API - 同步/异步双模式"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project, Chapter
from llm.factory import LLMFactory
from llm.roles import get_role, build_ai_removal_instruction, ROLES
from rag.retrieval import RetrievalService
from api.tasks import submit_llm_task, get_task, Task
from logger import logger, log_llm_call, log_llm_request
import time


router = APIRouter(prefix="/api/generate", tags=["生成"])


# ─── Schemas ───

class GenerateRequest(BaseModel):
    project_id: int
    chapter_id: int | None = None
    prompt: str
    mode: str = "continue"  # continue / polish / expand
    provider: str | None = None
    async_mode: bool = False  # ⭐ 异步模式开关


class GenerateResponse(BaseModel):
    task_id: str | None = None  # 异步模式下返回 task_id
    status: str | None = None  # "submitted" / "completed" / "error"
    generated_text: str | None = None
    provider: str | None = None
    duration_ms: float | None = None
    context_used: dict | None = None
    error: str | None = None


# ─── Prompt Templates ───

MODE_USER_PROMPTS = {
    "continue": "请根据上下文继续撰写下一段小说内容：\n\n当前写作内容：\n{prompt}\n\n直接输出续写内容，不要解释。",
    "polish": "请对以下小说内容进行润色和改进：\n\n待润色内容：\n{prompt}\n\n直接输出润色后的正文，不要说明修改了什么。",
    "expand": "请对以下情节进行扩展和深化：\n\n待扩展情节：\n{prompt}\n\n直接输出扩展后的正文，不要解释。",
}


# ─── 核心生成函数（同步） ───

def _do_generate(
    project_id: int,
    chapter_id: int | None,
    prompt: str,
    mode: str,
    provider: str | None,
    db: Session,
) -> dict:
    """执行同步 LLM 生成"""
    start = time.time()

    # 获取项目信息
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    # 构建 RAG 上下文
    try:
        retrieval = RetrievalService()
        context = retrieval.build_context(
            project_id=project_id,
            current_chapter_id=chapter_id,
            query=prompt,
            db=db,
        )
    except Exception as e:
        logger.warning(f"[RAG] context build failed: {e}")
        context = {"system_prompt": "你是一位专业的小说写作助手。", "characters_context": "", "world_context": "", "chapters_context": ""}

    # 获取 Role
    role_name = "writing" if mode == "continue" else "polish"
    if mode == "expand":
        role_name = "writing"
    role = get_role(role_name)

    # 构建 AI 味去除指令
    ai_instruction = build_ai_removal_instruction(project.ai味去除程度)

    # 构建 context 变量
    ctx = {
        "writing_style": project.writing_style or "平实",
        "ai_removal_instruction": ai_instruction,
        "themes": context.get("themes_context", ""),
        "characters": context.get("characters_context", ""),
        "character_arcs": context.get("character_arcs_context", ""),
        "world": context.get("world_context", ""),
        "foreshadowings": context.get("foreshadowings_context", ""),
        "chapters": context.get("chapters_context", ""),
        "target_word_count": project.target_word_count or 3000,
        "word_count_range": f"{project.word_count_min or 2000}～{project.word_count_max or 5000}",
    }

    system_prompt = role.build_system(ctx)
    user_prompt = MODE_USER_PROMPTS.get(mode, MODE_USER_PROMPTS["continue"]).format(prompt=prompt)

    # 日志记录请求
    log_llm_request(f"generate_{mode}", prompt, system_prompt)

    # 调用 LLM
    try:
        llm = LLMFactory.create(provider=provider)
        duration_ms = (time.time() - start) * 1000
        generated = llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=role.max_tokens,
            temperature=role.temperature,
        )
        duration_ms = (time.time() - start) * 1000
        log_llm_call(llm.provider_name, llm.model, f"generate_{mode}", duration_ms, True)
        logger.info(f"[Generate] completed in {duration_ms:.0f}ms")

    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_llm_call(provider or "unknown", "unknown", f"generate_{mode}", duration_ms, False, str(e))
        logger.error(f"[Generate] failed: {e}")
        raise

    return {
        "generated_text": generated,
        "provider": llm.provider_name,
        "duration_ms": duration_ms,
        "context_used": {
            "characters_context": context.get("characters_context", ""),
            "world_context": context.get("world_context", ""),
            "chapters_context": context.get("chapters_context", ""),
        },
    }


# ─── 异步任务函数 ───

def _async_generate_task(task_id: str, project_id: int, chapter_id: int | None, prompt: str, mode: str, provider: str | None):
    """异步生成任务（在线程池中执行）"""
    from storage.database import SessionLocal
    db = SessionLocal()
    try:
        task = get_task(task_id)
        if not task:
            return

        result = _do_generate(project_id, chapter_id, prompt, mode, provider, db)
        task.result = result
        task.status = "completed"
        task.progress = 100
        task.completed_at = time.time()
        logger.info(f"[AsyncTask] task_id={task_id} completed")
    except Exception as e:
        task = get_task(task_id)
        if task:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
        logger.error(f"[AsyncTask] task_id={task_id} failed: {e}")
    finally:
        db.close()


# ─── Routes ───

@router.post("", response_model=GenerateResponse)
async def generate_text(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    生成小说文本

    - async_mode=False（默认）：同步等待，立即返回结果
    - async_mode=True：异步提交，返回 task_id，前端轮询 /api/tasks/{task_id}
    """
    if not req.async_mode:
        # 同步模式
        try:
            result = _do_generate(
                project_id=req.project_id,
                chapter_id=req.chapter_id,
                prompt=req.prompt,
                mode=req.mode,
                provider=req.provider,
                db=db,
            )
            return GenerateResponse(
                status="completed",
                generated_text=result["generated_text"],
                provider=result["provider"],
                duration_ms=result["duration_ms"],
                context_used=result["context_used"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

    else:
        # 异步模式：提交任务，立即返回 task_id
        task = submit_llm_task(
            task_type="generate",
            llm_call_fn=_async_generate_task,
            project_id=req.project_id,
            description=f"生成 [{req.mode}] {req.prompt[:50]}...",
            chapter_id=req.chapter_id,
            prompt=req.prompt,
            mode=req.mode,
            provider=req.provider,
        )

        return GenerateResponse(
            task_id=task.id,
            status="submitted",
        )

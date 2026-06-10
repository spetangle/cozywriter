"""CozyWriter - 小说编写系统 FastAPI 入口"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import os

# 初始化数据库
from storage.database import init_db
from api.routes import (
    init, config, models, projects, chapters, characters,
    worldbuilding, outline, generate, theme, review,
    consistency, outline_detail, tasks, inspirations,
    creative_questionnaire, workflow, genres,
)
from api.routes.chapters import pipeline_router
from logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 / 关闭钩子"""
    # ── Startup ──
    init_db()

    # ── 配置健康检查 ──
    # 只在用户显式配置了 DEFAULT_LLM_PROVIDER 时做提示（缺 API key 时大声告诉他）；
    # 没配置就不再警告（系统允许用户在 web UI 里临时选 provider）。
    try:
        from config import settings
        provider = (settings.default_llm_provider or "").strip().lower()
        if provider:
            missing = []
            if provider == "anthropic" and not settings.anthropic_api_key:
                missing.append("ANTHROPIC_API_KEY")
            elif provider == "openai" and not settings.openai_api_key:
                missing.append("OPENAI_API_KEY")
            elif provider == "minimax" and not settings.minimax_api_key:
                missing.append("MINIMAX_API_KEY（去 https://platform.minimaxi.com/user-center/basic-information/interface-key 申请）")
            elif provider == "ollama":
                # ollama 不需要 API key，但需要本地服务
                pass
            else:
                logger.warning(
                    f"[Startup] ⚠️ DEFAULT_LLM_PROVIDER='{provider}' 不是已知 provider（可选: anthropic/openai/minimax/ollama）"
                )
            if missing:
                logger.warning(
                    f"[Startup] ⚠️ DEFAULT_LLM_PROVIDER={provider}，但 API key 未配置：{', '.join(missing)}\n"
                    f"           启动仍会成功，但调用 {provider} 会失败。请编辑 .env 设置对应字段后重启。"
                )
            else:
                logger.info(f"[Startup] ✓ LLM provider={provider} 配置正常")
    except Exception as e:
        logger.error(f"[Startup] config check failed: {e}")

    # 清理上次进程崩溃/异常退出留下的"假活"任务
    try:
        from api.tasks import reap_all_orphans
        result = reap_all_orphans()
        mem = result.get("memory_tasks", {})
        db = result.get("workflow_runs", {})
        if mem.get("reaped", 0) > 0 or db.get("reaped", 0) > 0:
            logger.warning(
                f"[Startup] Reaped orphans: "
                f"memory_tasks={mem.get('reaped', 0)}, "
                f"workflow_runs={db.get('reaped', 0)} (ids={db.get('ids', [])})"
            )
    except Exception as e:
        logger.error(f"[Startup] orphan reap failed: {e}")

    yield

    # ── Shutdown ──
    # 服务关闭时也清理一次（避免下次启动时还看到假活）
    try:
        from api.tasks import reap_all_orphans
        result = reap_all_orphans()
        mem = result.get("memory_tasks", {})
        db = result.get("workflow_runs", {})
        if mem.get("reaped", 0) > 0 or db.get("reaped", 0) > 0:
            logger.info(
                f"[Shutdown] Reaped orphans: "
                f"memory_tasks={mem.get('reaped', 0)}, "
                f"workflow_runs={db.get('reaped', 0)}"
            )
    except Exception as e:
        logger.error(f"[Shutdown] orphan reap failed: {e}")


app = FastAPI(
    title="CozyWriter",
    description="小说编写辅助系统 - LLM 生成 + RAG 知识管理 + 一致性检查 + 智能评审 + 大纲细纲 + 灵感收集 + 创意问卷",
    version="0.5.0",
    lifespan=lifespan,
)


# ─── HTTP 请求日志中间件 ───
# 记录每个请求：方法、路径、状态码、耗时，方便排查错误
@app.middleware("http")
async def log_requests(request, call_next):
    import time as _time
    t0 = _time.time()
    response = None
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        logger.error(f"[API] EXC {request.method} {request.url.path}: {e}", exc_info=True)
        raise
    finally:
        duration_ms = (_time.time() - t0) * 1000
        # 静态文件 / 健康检查不刷屏
        path = request.url.path
        if not path.startswith("/static"):
            logger.info(
                f"[API] {request.method} {path} → {status_code} ({duration_ms:.0f}ms)"
            )
    return response


# 注册路由
app.include_router(init.router)
app.include_router(config.router)
app.include_router(models.router)
app.include_router(projects.router)
app.include_router(chapters.router)
app.include_router(characters.router)
app.include_router(worldbuilding.router)
app.include_router(outline.router)
app.include_router(generate.router)
app.include_router(theme.router)             # 主题/伏笔/角色弧光/关系矩阵
app.include_router(review.router)             # 评审打分 + 修订
app.include_router(consistency.router)         # 一致性检查
app.include_router(outline_detail.router)       # 大纲 / 细纲
app.include_router(tasks.router)               # 异步任务状态轮询
app.include_router(inspirations.router)         # 灵感收集（新版：/api/inspirations 全局+项目）
app.include_router(genres.router)                 # 题材（系统 + 用户自定义）
app.include_router(creative_questionnaire.router) # 创意问卷
app.include_router(workflow.router)             # 工作流管理（重跑/提交）
app.include_router(pipeline_router)            # 章节生成 9 步流水线

# 旧版灵感 API 兼容路由：/api/projects/{pid}/inspirations → 转发到 /api/inspirations
# （保留项目内旧版右侧面板可用）
# 注意：底层函数（list_inspirations 等）把 project_id 声明为 Query，
# 而旧路由 prefix 把 project_id 放在路径里，必须用 Path 接，不能直接 add_api_route 复用。
from fastapi import APIRouter as _APIRouter, Path as _PathParam, Query, Depends
from sqlalchemy.orm import Session
from storage.database import get_db
from api.routes.inspirations import (
    list_inspirations as _list_insp,
    create_inspiration as _create_insp,
    update_inspiration as _upd_insp,
    delete_inspiration as _del_insp,
    InspirationCreate, InspirationUpdate,
)

legacy_insp = _APIRouter(prefix="/api/projects/{project_id}/inspirations", tags=["灵感-兼容"])


@legacy_insp.get("", summary="[兼容] 项目灵感列表")
async def _legacy_list_inspirations(
    project_id: int = _PathParam(..., description="项目 ID"),
    tag: str | None = Query(None),
    q: str | None = Query(None, description="搜索关键字（标题/内容）"),
    source: str | None = Query(None),
    include_consumed: bool = Query(False),
    db: Session = Depends(get_db),
):
    return await _list_insp(
        project_id=project_id,
        tag=tag,
        q=q,
        source=source,
        include_consumed=include_consumed,
        db=db,
    )


@legacy_insp.post("", summary="[兼容] 项目下创建灵感")
async def _legacy_create_inspiration(
    project_id: int = _PathParam(..., description="项目 ID"),
    data: InspirationCreate = ...,
    db: Session = Depends(get_db),
):
    # 路径里的 project_id 优先于 body 里的 project_id（如果 body 没传就用路径值）
    if data.project_id is None:
        data.project_id = project_id
    return await _create_insp(data=data, db=db)


@legacy_insp.put("/{insp_id}", summary="[兼容] 更新项目灵感")
async def _legacy_update_inspiration(
    project_id: int = _PathParam(..., description="项目 ID"),
    insp_id: int = _PathParam(..., description="灵感 ID"),
    data: InspirationUpdate = ...,
    db: Session = Depends(get_db),
):
    return await _upd_insp(insp_id=insp_id, data=data, db=db)


@legacy_insp.delete("/{insp_id}", summary="[兼容] 删除项目灵感")
async def _legacy_delete_inspiration(
    project_id: int = _PathParam(..., description="项目 ID"),
    insp_id: int = _PathParam(..., description="灵感 ID"),
    db: Session = Depends(get_db),
):
    return await _del_insp(insp_id=insp_id, db=db)


app.include_router(legacy_insp)


# 确保 data 目录存在
data_dir = Path("./data")
data_dir.mkdir(exist_ok=True)


@app.get("/")
async def root():
    """返回前端入口"""
    return FileResponse("web/index.html")


# 挂载静态文件
web_static = Path("web/static")
if web_static.exists():
    app.mount("/static", StaticFiles(directory="web/static"), name="static")


if __name__ == "__main__":
    import uvicorn
    # access_log=False 关闭 uvicorn 默认 access log（HTTP 请求走 main.py 里的 middleware，
    # 写到 console + 文件，避免重复）
    uvicorn.run("main:app", host="0.0.0.0", port=13567, reload=True, access_log=False)

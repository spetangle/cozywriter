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
from fastapi import APIRouter as _APIRouter
from api.routes.inspirations import (
    list_inspirations as _list_insp, create_inspiration as _create_insp,
    update_inspiration as _upd_insp, delete_inspiration as _del_insp,
)
legacy_insp = _APIRouter(prefix="/api/projects/{project_id}/inspirations", tags=["灵感-兼容"])
legacy_insp.add_api_route("", _list_insp, methods=["GET"])
legacy_insp.add_api_route("", _create_insp, methods=["POST"])
legacy_insp.add_api_route("/{insp_id}", _upd_insp, methods=["PUT"])
legacy_insp.add_api_route("/{insp_id}", _del_insp, methods=["DELETE"])
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
    uvicorn.run("main:app", host="0.0.0.0", port=13567, reload=True)

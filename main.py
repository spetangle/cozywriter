"""CozyWriter - 小说编写系统 FastAPI 入口"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

# 初始化数据库
from storage.database import init_db
from api.routes import (
    init, config, models, projects, chapters, characters,
    worldbuilding, outline, generate, theme, review,
    consistency, outline_detail, tasks, inspirations,
    creative_questionnaire,
)

app = FastAPI(
    title="CozyWriter",
    description="小说编写辅助系统 - LLM 生成 + RAG 知识管理 + 一致性检查 + 智能评审 + 大纲细纲 + 灵感收集 + 创意问卷",
    version="0.5.0",
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
app.include_router(inspirations.router)         # 灵感收集
app.include_router(creative_questionnaire.router) # 创意问卷


# 确保 data 目录存在
data_dir = Path("./data")
data_dir.mkdir(exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    init_db()


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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# AGENTS.md

CozyWriter：本地 FastAPI + 同步 SQLAlchemy(SQLite) + Alpine.js 无构建 SPA + ChromaDB RAG 的 AI 小说 / 剧本写作系统。

`README.md` 与 `ARCHITECTURE.md` 部分内容已过时（前端已重构成多页面 SPA、新增剧本子系统与 deepseek/mimo provider、项目 ID 改为 hex 字符串）。以代码为准，文档仅作背景。

## 常用命令

```bash
# 首次或依赖变更：建 .venv + 装依赖 + 启动
./run.sh

# 依赖已装时只启动（uvicorn reload=True，端口 13567）
.venv/bin/python main.py          # http://localhost:13567
```

Windows 用 `run.bat` / `run.ps1`，Python 为 `.venv\Scripts\python.exe`。

没有 pytest / lint / formatter / CI 配置。测试是独立脚本，只能整脚本运行，直接跑：

```bash
.venv/bin/python tests/test_frontend_routes.py     # 前端 /api 调用 ↔ 后端路由一致性
.venv/bin/python tests/test_script_api.py          # 剧本 API 集成
.venv/bin/python tests/test_script_post_process.py # 剧本后处理回归
.venv/bin/python tests/test_script_bootstrap.py    # 剧本 planner / locked / commit / JSON 兜底
.venv/bin/python tests/test_migrate_project_ids.py # int→hex 项目 ID 迁移（保留列/外键）
node tests/test_spa_components.js                  # SPA 模板 / 组件装配
```

测试用临时 SQLite（在 import config 前设置 `DATABASE_URL`），不碰 `data/cozywriter.db`；涉及角色写接口的测试会 stub 掉 RAG，避免加载 embedding 模型（慢）。

数据库 schema 变更后运行 `python migrate.py`（对比 ORM 给旧表补列 / 建新表）。服务启动时 `init_db()` 也会自动跑 `storage/migrations/` 下的 id 迁移等。

## 架构要点

- 入口 `main.py`：注册全部 router，端口 13567。新增路由必须在这里 `include_router`（`api/routes/__init__.py` 只导出部分模块，其余直接 import 子模块）。
- 两套子系统，由 `Project.project_type` 区分：`novel` 走 `llm/chapter_pipeline.py` + `Chapter`/`ChapterOutline`；`script` 走 `llm/script_pipeline.py` + `Screenplay`/`Storyboard`/`Property`。剧本 prompt 在 `llm/script_roles.py`。
- LLM：`llm/factory.py` 选择 provider（anthropic / openai / minimax / mimo / deepseek / ollama）。优先级：参数 > DB `Provider.is_default` > `SystemSetting` > `config.py`。Prompt role 在 `llm/roles.py`。
- RAG：ChromaDB + `moka-ai/m3e-base`，模型下载到 `data/models/`（~400MB，首次需联网）。用户数据全部在 `data/`（gitignore）。
- 前端无构建：`web/index.html` 只是外壳，`web/static/js/app.js` 是 hash 路由调度器，`pages/*.js` + `components/*.js` 各自注册 `Alpine.data` 与 `window.registerPageTemplate`。页面模板用 `<!--@component:name-->` 占位符，挂载时惰性展开。每个页面组件都必须有 `init()`。

## 易踩的坑

- **Project ID 是 8 位 hex 字符串（`String(32)` 主键），不是 int**（`storage/models/base.py:generate_project_id`）。别信旧文档里的 `project_id: int`。
- 数据库全程同步 SQLAlchemy Session（SQLite，`check_same_thread=False`），无 async ORM。
- 改前端 JS 后必须把 `web/index.html` 里对应脚本的 `?v=N` 版本号 +1，否则浏览器缓存不刷新。
- LLM 完整 prompt/response 默认写日志（`LOG_LLM_PAYLOAD=1` → `data/logs/cozywriter_YYYYMMDD.log`）。排查 LLM 问题直接 grep 该文件；勿让密钥落日志。
- 改动 ORM 列时，除 model 外还要考虑 `migrate.py` / `storage/migrations/`，否则老库会缺列。
- 项目文件为 UTF-8 无 BOM；PowerShell 写文件用 `UTF8Encoding($false)`。Windows 控制台默认 GBK，读中文接口先设 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。
- 样式集中在 `web/static/css/style.css`（~5900 行）；新增 UI 前先 grep 复用已有类名，别另造一套。

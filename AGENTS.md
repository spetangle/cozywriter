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

启动脚本会把依赖安装到项目内 `.venv`（设置 `PIP_USER=0`/`PYTHONNOUSERSITE=1`/`PIP_REQUIRE_VIRTUALENV=1`，并校验 `sys.prefix` 在项目目录内），并检测跨平台 venv；支持 `--rag` / `--rag-cpu` 追加 RAG 依赖。依赖源默认清华镜像（避免 pypi.org 超时），可用 `--official` / `--mirror aliyun` / `--index-url URL` 或 `COZYWRITER_PIP_INDEX` 覆盖；失败会自动回退清华镜像。

没有 pytest / lint / formatter / CI 配置。测试是独立脚本，只能整脚本运行，直接跑：

```bash
.venv/bin/python tests/test_frontend_routes.py     # 前端 /api 调用 ↔ 后端路由一致性
.venv/bin/python tests/test_script_api.py          # 剧本 API 集成
.venv/bin/python tests/test_script_post_process.py # 剧本后处理回归
.venv/bin/python tests/test_script_bootstrap.py    # 剧本 planner / locked / commit / JSON 兜底
.venv/bin/python tests/test_migrate_project_ids.py # int→hex 项目 ID 迁移（保留列/外键）
.venv/bin/python tests/test_system_smoke.py        # 系统级 API 冒烟（项目/章节/剧本/导出等）
.venv/bin/python tests/test_word_adjust.py          # 字数收敛 / opencode provider
.venv/bin/python tests/test_deepseek_json_fallback.py # DeepSeek JSON 空响应降级 / JSON 开关
.venv/bin/python tests/test_task_timeout.py        # LLM 任务软超时（完成不误判 failed）
.venv/bin/python tests/test_growth_foreshadow_api.py # 角色成长 / 本章伏笔 / 关系 / 相似小说接口
# RAG 启用说明见 docs/rag_setup.md；后处理结果见项目页「🔄 状态变化」页签
.venv/bin/python tests/test_outline_normalize.py    # 大纲章节号字段归一化
.venv/bin/python tests/test_clear_project_data.py   # 旧库项目数据清理（保留系统配置）
.venv/bin/python tests/test_requirements_split.py   # 核心依赖 / RAG 依赖拆分
.venv/bin/python tests/test_rag_cpu.py             # RAG 强制 CPU / 缺库提示
.venv/bin/python tests/test_rag_online.py          # RAG 本地/在线切换
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
- DeepSeek 某些模型 JSON 模式会返回空响应：provider 已内置降级重试，仍不稳定时在「全局设置 → 服务商」把该服务商的「JSON 输出模式」设为强制关闭。详见 `docs/deepseek_json_mode.md`。
- 清理旧库项目数据（保留 providers/system_settings/超参/自定义题材）：`python tools/clear_project_data.py --dry-run` 预览，`--yes` 执行（自动备份到 `data/backups/`，可选 `--clear-rag`）。
- RAG 依赖是可选的：`requirements.txt` 不含 `sentence-transformers`（会连带安装 torch / nvidia-*）；推荐用 CPU 版一键脚本 `tools/install_rag_cpu.sh`（Windows：`tools/install_rag_cpu.ps1` / `.bat`），应用加载模型时强制 `device="cpu"`。RAG 支持本地/在线切换：`GET/PUT /api/config/rag`、`POST /api/config/rag/test`、`POST /api/config/rag/reset`；前端在「全局设置 → RAG 向量」。详见 `docs/rag_setup.md`。
- 改动 ORM 列时，除 model 外还要考虑 `migrate.py` / `storage/migrations/`，否则老库会缺列。
- 项目文件为 UTF-8 无 BOM；PowerShell 写文件用 `UTF8Encoding($false)`。Windows 控制台默认 GBK，读中文接口先设 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。
- 样式集中在 `web/static/css/style.css`（~5900 行）；新增 UI 前先 grep 复用已有类名，别另造一套。

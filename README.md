# CozyWriter · AI 小说 / 剧本编写助手

> 本地化 · 一键启动 · 长篇连载级一致性
> FastAPI + 同步 SQLAlchemy(SQLite) + Alpine.js 无构建 SPA + ChromaDB RAG

一个面向长篇小说与剧本创作的本地写作系统：LLM 生成 + 设定管理 + RAG 知识库 + 评审/一致性检查 + 大纲细纲 + 创意问卷 + 灵感池 + 剧本场景/分镜。

> 开发与接口细节请以代码和 `AGENTS.md` 为准；`ARCHITECTURE.md` 为较早期文档，部分内容已过时。

---

## ✨ 核心特性

### 🤖 小说 9 步章节生成流水线
细纲生成 → 细纲评审 → 正文写作 → 字数校验/调整 → 正文评审 → 修订决策 → 保存 → 后处理（弧光/关系/伏笔）→ 事件签名。

- 支持单章（`/api/chapters/generate-pipeline`）与批量（`/api/chapters/batch-generate`）
- 字数动态 `max_tokens` + 收敛调整（目标区间 + 过冲淘汰）
- 空正文保护：失败时保留旧正文，不写入空章节

### 🎬 剧本子系统
- 场景（Screenplay）→ 分镜（Storyboard）→ 道具（Property）全链路
- 场景生成流水线：准备 → 细纲 → 评审 → 正文 → 修订 → 分镜 → 后处理
- 角色外貌（appearance）随剧情自动更新并带变化记录

### 🚀 项目引导补全（Bootstrap Workflow）
创建项目后自动补全：基础外推 → 主旨/风格 → 世界观 → 角色 → 关系 → 弧光 → 大纲 → 章节细纲 → 伏笔。

- 单次最多生成 100 章细纲，超出自动分批续写直到覆盖目标章数
- 支持重跑单个 stage、缺失项重跑、失败 run 不误删旧数据

### 🎨 Provider 与领域增强
- 支持 Anthropic / OpenAI / MiniMax / MiMo / DeepSeek / OpenCode Go / Ollama
- Provider 配置以数据库为准（全局设置 → 服务商），`.env` 仅作回退
- 每个 Provider 可单独配置模型名、Base URL、API Key，以及「JSON 输出模式」开关

### 📚 RAG 知识库（可选）
- ChromaDB + `moka-ai/m3e-base`，用于事件去重、相似章节检索、评审上下文
- **未安装也能正常写作**；未启用时项目页显示「⚠️ RAG 未启用」。详见 `docs/rag_setup.md`

### 🧩 其他
- 创意问卷建项目（分步问答 / AI 补全）
- 灵感池（全局 + 项目）、剧情追踪、角色关系图谱
- 导出正文（TXT / Markdown / 重新分章 / 独立打包 ZIP）
- 章节「🔄 状态变化」页签：展示本章弧光 / 关系 / 伏笔 / 新角色变化
- 任务管理：轮询进度、取消、终止全部

---

## 🚀 快速开始

### 环境要求
- Python **3.10+**
- Node.js 仅用于前端模板测试（运行系统本身不需要）
- 联网（调用 LLM API；RAG 模型可选）

### 一键启动

**Windows (PowerShell)**
```powershell
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
.\run.ps1
```

**Windows (CMD)**
```bat
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
run.bat
```

**macOS / Linux**
```bash
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
chmod +x run.sh
./run.sh
```

启动脚本会：检查 Python 版本 → 创建/复用**项目内 `.venv`** → 升级 pip → 安装依赖 → 启动服务。

- 所有依赖都装进项目目录的 `.venv`（设置 `PIP_USER=0` / `PYTHONNOUSERSITE=1`，不会写入全局或用户 site-packages）
- 检测并拒绝跨平台 venv（如 Windows 下用 `run.sh` 建的 `.venv`）
- 可选参数：
  ```bash
  ./run.sh --rag          # 额外安装 RAG 依赖（可能带 nvidia-* CUDA 包）
  ./run.sh --rag-cpu      # 额外安装 CPU 版 RAG（不装 nvidia-*）
  ```
  Windows：`run.bat --rag-cpu` / `.\run.ps1 --rag-cpu`

依赖已安装时可只启动：
```bash
.venv/bin/python main.py        # Linux/macOS
.venv\Scripts\python main.py    # Windows
```

打开 **http://localhost:13567**

### 首次配置 Provider

1. 打开「全局设置 → 服务商」
2. 选择服务商，填 API Key / 模型名，点击「测试连接」
3. 「设为默认」切换默认 Provider

> 配置保存在数据库 `providers` 表；`.env` 仅作为无数据库记录时的回退。
> OpenCode Go 需要填入 API Key 后才可启用。

### 创建第一个项目

两种方式：
- **直接创建**：填写书名 / 章节字数 / 题材（可多选）/ 创意信息，系统自动跑 Bootstrap。
- **创意问卷**：分步问答（可选 AI 一键补全）后 `build-project`，自动生成项目与设定。

---

## 🤖 支持的 LLM Provider

| Provider | 协议 | 默认 Base URL | 默认模型 |
|---|---|---|---|
| anthropic | Anthropic Messages | https://api.anthropic.com | `claude-sonnet-4-20250514` |
| openai | OpenAI Chat Completions | https://api.openai.com/v1 | `gpt-4o` |
| minimax | Anthropic 兼容 | https://api.minimaxi.com/anthropic | `MiniMax-M2.7` |
| mimo | Anthropic 兼容 | https://token-plan-cn.xiaomimimo.com/anthropic | `mimo-v2.5-pro` |
| deepseek | OpenAI / Anthropic 兼容 | https://api.deepseek.com/v1 | `deepseek-chat-v4-flash` |
| opencode | OpenAI 兼容（OpenCode Go） | https://opencode.ai/zen/go/v1 | `deepseek-v4.1-flash` |
| ollama | Ollama native | http://localhost:11434 | 本地模型 |

> 部分模型（如推理模型）在 JSON 模式下可能返回空响应；provider 已内置降级重试，仍不稳定时可在「服务商」里把「JSON 输出模式」设为强制关闭。详见 `docs/deepseek_json_mode.md`。

### `.env` 配置（可选回退）

```bash
# 至少配置一个（也可全部在网页「服务商」里配置）
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
MINIMAX_API_KEY=eyJxxx
MIMO_API_KEY=xxx
DEEPSEEK_API_KEY=sk-xxx

# OpenCode Go（可选，默认关闭）
OPENCODE_ENABLED=false
OPENCODE_API_KEY=oc_sk_xxx
OPENCODE_MODEL=deepseek-v4.1-flash
OPENCODE_BASE_URL=https://opencode.ai/zen/go/v1

# Embedding / 存储
EMBEDDING_MODEL=moka-ai/m3e-base
HF_ENDPOINT=https://hf-mirror.com
DATA_DIR=./data
CHROMA_PERSIST_DIR=./data/chroma
DATABASE_URL=sqlite:///./data/cozywriter.db
```

---

## 📦 Embedding 模型 / RAG（可选）

RAG 依赖本地模型 `moka-ai/m3e-base`（约 400MB），并且需要额外安装 `sentence-transformers`。
**核心依赖 `requirements.txt` 不包含它**，所以：

- 不装：主流程写作完全正常，只是事件去重与相似度检索会跳过，项目页显示「⚠️ RAG 未启用」；
- 本地 CPU：运行一键脚本（避免 `nvidia-*` CUDA 包）
  ```bash
  ./tools/install_rag_cpu.sh          # Linux / macOS
  .\tools\install_rag_cpu.ps1         # Windows PowerShell
  tools\install_rag_cpu.bat           # Windows CMD
  ```
- 在线 embedding：在「全局设置 → RAG 向量」里把模式切到“在线 Embedding API”，填 OpenAI 兼容的
  Base URL / 模型名 / API Key（如 `https://api.openai.com/v1` + `text-embedding-3-small`）。

> 应用加载本地模型时已强制 `device="cpu"`。
> 切换本地/在线或更换模型后向量维度会变化，需要点「♻️ 重置向量库」重建。

启用方式与离线安装见 **`docs/rag_setup.md`**。模型目录：

```
data/models/moka-ai/m3e-base/
```

启用后项目页顶栏的「⚠️ RAG 未启用」提示会消失。

---

## 📂 项目结构

```
cozywriter/
├── main.py                       # FastAPI 入口（端口 13567）
├── config.py                     # pydantic-settings 配置
├── migrate.py                    # ORM 对比迁移（给旧表补列）
├── requirements.txt / .env.example
├── run.sh / run.bat / run.ps1    # 跨平台启动脚本
│
├── llm/                          # LLM 抽象层与流水线
│   ├── factory.py                # Provider 工厂（DB 优先）
│   ├── roles.py                  # 小说 Role / prompt 模板
│   ├── workflow.py               # Bootstrap 工作流
│   ├── chapter_pipeline.py       # 小说 9 步流水线
│   ├── script_pipeline.py        # 剧本生成流水线
│   ├── script_roles.py           # 剧本 prompt
│   └── *_provider.py             # anthropic/openai/minimax/mimo/deepseek/opencode/ollama
│
├── rag/                          # RAG（ChromaDB）
│   ├── model_manager.py / embedder.py / vector_store.py
│   └── knowledge_base.py / retrieval.py
│
├── storage/                      # 数据层
│   ├── database.py               # SQLite（同步）
│   ├── models/                   # SQLAlchemy ORM
│   └── migrations/               # 项目 ID / schema 专项迁移
│
├── api/routes/                   # FastAPI 路由
│
├── tools/
│   └── clear_project_data.py     # 清理项目数据（保留系统配置）
│
├── tests/                        # 独立测试脚本（无 pytest）
├── docs/                         # 测试报告 / 修复计划 / 专题文档
│
├── data/                         # 用户数据（不入 git）
│   ├── cozywriter.db
│   ├── chroma/
│   ├── logs/
│   └── models/moka-ai/m3e-base/
│
└── web/                          # 前端 SPA（Alpine.js 无构建）
    ├── index.html                # 外壳 + 脚本 ?v=N
    └── static/
        ├── css/style.css
        └── js/app.js + pages/ + components/
```

---

## 🧪 测试

无 pytest / CI，测试为独立脚本，直接整脚本运行：

```bash
.venv/bin/python tests/test_frontend_routes.py        # 前端调用 ↔ 后端路由一致性
.venv/bin/python tests/test_system_smoke.py           # 系统级 API 冒烟
.venv/bin/python tests/test_script_api.py             # 剧本 API 集成
.venv/bin/python tests/test_script_post_process.py    # 剧本后处理
.venv/bin/python tests/test_script_bootstrap.py       # 剧本 bootstrap / commit
.venv/bin/python tests/test_migrate_project_ids.py    # 项目 ID 迁移
.venv/bin/python tests/test_word_adjust.py            # 字数收敛 / provider
.venv/bin/python tests/test_outline_normalize.py      # 大纲章节号归一化
.venv/bin/python tests/test_deepseek_json_fallback.py # DeepSeek JSON 降级
.venv/bin/python tests/test_clear_project_data.py     # 旧库清理工具
node tests/test_spa_components.js                     # SPA 模板/组件装配
```

Windows 用 `.venv\Scripts\python.exe`。

---

## 🧹 清理旧库项目数据

清除所有项目及其关联数据，保留 `providers` / `system_settings` / 超参预设 / 自定义题材：

```bash
.venv/bin/python tools/clear_project_data.py --dry-run   # 预览
.venv/bin/python tools/clear_project_data.py --yes       # 执行（自动备份到 data/backups/）
.venv/bin/python tools/clear_project_data.py --yes --clear-rag  # 同时清空向量库
```

---

## 🔌 API 概览（常用）

### 项目
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET`/`POST` | `/api/projects` | 列表 / 创建（4 必填校验 + Bootstrap） |
| `GET`/`PUT`/`DELETE` | `/api/projects/{id}` | 详情 / 更新 / 删除 |
| `GET` | `/api/projects/{id}/bootstrap-status` | Bootstrap 状态 |

### 章节
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET`/`POST` | `/api/projects/{id}/chapters` | 章节列表 / 新建（自动带 bootstrap 细纲） |
| `GET`/`PUT`/`DELETE` | `/api/projects/{id}/chapters/{cid}` | 详情 / 更新 / 删除 |
| `POST` | `/api/chapters/generate-pipeline` | 单章 9 步流水线 |
| `POST` | `/api/chapters/batch-generate` | 批量生成 |
| `GET` | `/api/projects/{id}/chapters/{cid}/post-processing` | 本章状态变化 |
| `GET` | `/api/projects/{id}/post-processing/latest` | 最近章节状态变化 |

### 工作流 / 任务
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/workflow/project/{id}/latest` | 项目最新 run |
| `GET` | `/api/workflow/project/{id}/bootstrap-data` | 引导产出预览 |
| `POST` | `/api/workflow/run/{rid}/rerun` / `rerun-all` | 重跑 stage |
| `GET` | `/api/tasks/{task_id}` / `/api/tasks/all` | 任务状态 |

### 设定资源
| 资源 | 路由前缀 |
|---|---|
| 角色 | `/api/projects/{id}/characters` |
| 世界观 | `/api/projects/{id}/worldbuilding` |
| 项目大纲 | `/api/projects/{id}/outline` |
| 章节细纲 | `/api/projects/{id}/chapters/{cid}/outline` |
| 主题 / 伏笔 / 弧光 / 关系 | `/api/projects/{id}/themes`、`/foreshadowings`、`/character-arcs`、`/character-relations` |
| 剧情点 | `/api/projects/{id}/plot-points` |
| 灵感 | `/api/inspirations` |
| 剧本场景 / 分镜 / 道具 | `/api/projects/{id}/screenplays`、`/storyboards`、`/properties` |
| 题材 | `/api/genres` |
| 服务商 | `/api/providers` |
| 导出 | `/api/export/chapters` |

> 完整路由见 `/docs`（FastAPI Swagger UI）。

---

## 💾 数据与日志

- 全部用户数据在 `data/`（gitignore）：`cozywriter.db`、`chroma/`、`logs/`、`models/`
- LLM 完整 prompt/response 默认写日志：`data/logs/cozywriter_YYYYMMDD.log`
- 数据库 schema 变更后运行 `.venv/bin/python migrate.py`；服务启动时 `init_db()` 也会自动补列/迁移

---

## 📄 License

MIT

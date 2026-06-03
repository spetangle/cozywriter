# CozyWriter · AI 小说编写助手

> 本地化 · 一键启动 · 长篇连载级一致性  
> 基于 LLM API + RAG 知识管理 + 9 步章节生成流水线的 FastAPI Web 写作系统

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Embedding: moka-ai/m3e-base](https://img.shields.io/badge/Embedding-m3e--base-orange.svg)](https://huggingface.co/moka-ai/m3e-base)

---

## ✨ 核心特性

### 🤖 9 步章节生成流水线

每章按下述流程自动跑完（可同步 / 异步）：

| 步骤 | 动作 | LLM Role |
|---|---|---|
| 1 | 聚合章节准备信息（项目设定 + 前 3 章 + 登场人物 + 活跃伏笔） | — |
| 2 | 生成章节细纲 | `chapter_outline_gen` |
| 3 | 评审细纲（**只过滤严重性漏洞**，可自动修订） | `outline_reviewer` |
| 4 | 按细纲生成正文 | `novel_writer` |
| 5 | 字数调整（过多缩写 / 过少扩写） | `compressor` / `expander` |
| 6 | 8 维度正文评审 | `reviewer` |
| 7 | 自动决策修订（avg < 6.5 自动改） | `revision_decider` + `reviser` |
| 8 | 保存到 `Chapter.content` + `ChapterVersion` 快照 | — |
| 9 | **后处理**（弧光 / 关系 / 伏笔 / 新角色 + 触发自动检查） | `post_chapter` + `foreshadow_updater` |

### 📊 自动检查与触发

| 触发 | 动作 |
|---|---|
| **每写完 1 章** | 角色弧光 + 关系矩阵 + 伏笔状态机自动更新 |
| **第 3 章** | 黄金三章检查（开局诊断评分 + 建议） |
| **每 5 章** | 连续性 + 一致性检查（自动运行，结果推给用户） |
| 失败重跑 | 任一 stage 失败可单独 `POST /api/workflow/run/{id}/rerun` |

### 🚀 项目引导补全（Bootstrap Workflow）

新建项目时只填 4 必填（书名 / 章节字数 / 题材 / 一句话），其余 8 选填可由 LLM 补全：

```
用户表单 ─┬─ 4 必填 (锁)
          └─ 8 选填 (缺则补)

工作流分 11 个 stage 按依赖执行：
  Stage 1   基础外推        (total_chapters / ai_removal)
  Stage 2A  核心主旨+基调
  Stage 2B  文风+节奏
  Stage 2C  世界观骨架
  Stage 3A  主角细化
  Stage 3B  反派细化
  Stage 3C  配角+关系矩阵
  Stage 3D  角色弧光设计
  Stage 4A  项目大纲
  Stage 4B  伏笔规划
  Stage 5   章节细纲
```

用户已填的字段 → 跳过该 LLM 调用（**5~9 次 LLM 调用动态调整**）。  
浏览器刷新可自动从 `WorkflowRun` 表恢复 wizard。

### 📚 RAG 知识管理

- 角色设定 / 世界观 / 章节摘要 → 自动向量化入 ChromaDB
- 写章节时按 query 检索相关上下文 → 注入 LLM system prompt
- 项目隔离，**数据全部在项目内 `data/`**（不污染 `~/.cache/huggingface`）

### 🎛 任务管理

- 异步任务池 + 2s 进度轮询
- **可终止**：单任务 / 全部任务
- badge 实时显示进行中数量

### 🎨 7 种写作风格 + 去 AI 味强度 1-10

优美 / 幽默 / 冷峻 / 平实 / 诗意  
→ 项目级配置，AI 写作时强制遵循

### ✅ 8 维度智能评审

一致性 · 节奏 · 文笔 · 去 AI 味 · 字数合规 · 伏笔管理 · 角色弧光 · 主旨契合

---

## 🚀 快速开始

### 环境要求

- Python **3.10+**（Windows / Linux / macOS）
- 联网（首次启动需下载 embedding 模型 + 调用 LLM API）

### 一键启动

**Windows (PowerShell)**：
```powershell
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
.\run.ps1
```

**Windows (CMD)**：
```bat
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
run.bat
```

**macOS / Linux**：
```bash
git clone https://github.com/spetangle/cozywriter.git
cd cozywriter
chmod +x run.sh
./run.sh
```

启动脚本会：
1. 自动创建 `.venv`
2. 升级 pip（静默）
3. **只显示新装依赖的进度**（已装的跳过）
4. 启动服务

打开 **http://localhost:13567**

### 首次运行向导

1. 选择 LLM Provider（**Anthropic / OpenAI / MiniMax / Ollama** 四选一）
2. 填入 API Key → 自动写入 `.env`
3. 下载中文 embedding 模型（**~400MB**，前台 SSE 进度条可见）
4. 进入写作台

### 创建第一个项目

填写 4 必填：
- **书名**
- **章节字数**（2/3/4/5 千字）
- **题材**（玄幻/都市/科幻/武侠/仙侠/历史/悬疑/现实主义/奇幻/其他）
- **创意信息**（一句话）

→ 系统启动 **11 步引导补全 workflow**，自动生成角色 / 世界观 / 大纲 / 章节细纲 / 伏笔。

---

## 🤖 支持的 LLM Provider

| Provider | API 协议 | Base URL | 推荐模型 |
|---|---|---|---|
| **Anthropic** | Anthropic Messages | https://api.anthropic.com | `claude-sonnet-4-20250514` |
| **OpenAI** | OpenAI Chat Completions | https://api.openai.com/v1 | `gpt-4o` |
| **MiniMax** | **Anthropic Messages 兼容** | https://api.minimaxi.com | `MiniMax-M2.7` (默认) / `MiniMax-M3` (1M 上下文 / 多模态) |
| **Ollama** | Ollama native | http://localhost:11434 | `qwen2.5` / 其他本地模型 |

> 📘 MiniMax API 文档：https://platform.minimaxi.com/docs/guides/models-intro

### .env 配置

```bash
# LLM Provider（至少配置一个）
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
MINIMAX_API_KEY=eyJxxx
MINIMAX_MODEL=MiniMax-M2.7
MINIMAX_BASE_URL=https://api.minimaxi.com
OLLAMA_BASE_URL=http://localhost:11434

# 默认 Provider: anthropic / openai / minimax / ollama
DEFAULT_LLM_PROVIDER=minimax

# Embedding 模型
EMBEDDING_MODEL=moka-ai/m3e-base
HF_ENDPOINT=https://hf-mirror.com

# 存储
DATA_DIR=./data
CHROMA_PERSIST_DIR=./data/chroma
DATABASE_URL=sqlite:///./data/cozywriter.db
```

---

## 📦 Embedding 模型

首次启动会自动下载中文 embedding 模型到 `data/models/`，**项目内目录**（不污染系统）：

| 模型 | 用途 | 大小 | Hugging Face |
|---|---|---|---|
| **`moka-ai/m3e-base`** | 中文语义 embedding，RAG 检索 | ~400MB | https://huggingface.co/moka-ai/m3e-base |

### 预下载 / 离线安装

若机器无法访问 HuggingFace，可提前下载 `m3e-base` 后放到指定目录：

**方法 1：从 HuggingFace 手动下载**

1. 打开 https://huggingface.co/moka-ai/m3e-base/tree/main
2. 下载所有文件（`config.json`, `model.safetensors`, `tokenizer.json`, `vocab.txt`, `modules.json` 等）
3. 放入 `data/models/moka-ai/m3e-base/` 目录：

```
data/
└── models/
    └── moka-ai/
        └── m3e-base/
            ├── config.json
            ├── model.safetensors         # 主要权重
            ├── tokenizer.json
            ├── tokenizer_config.json
            ├── vocab.txt
            ├── modules.json
            └── sentence_bert_config.json
```

4. 重启服务（`is_model_downloaded()` 会自动识别）

**方法 2：HF 镜像加速（默认）**

代码已配置 `HF_ENDPOINT=https://hf-mirror.com`，国内可直接下载。

**方法 3：HuggingFace 官方 CLI**

```bash
huggingface-cli download moka-ai/m3e-base --local-dir ./data/models/moka-ai/m3e-base
```

### 模型文件大小说明

- `model.safetensors`：~390MB（PyTorch 权重，安全张量格式）
- ~~`pytorch_model.bin`：~390MB（旧权重格式，可删除以节省空间）~~

> ⚠️ `model.safetensors` 优先加载，`pytorch_model.bin` 冗余。手动删除 `pytorch_model.bin` 可节省 390MB 磁盘：
> ```bash
> rm data/models/moka-ai/m3e-base/pytorch_model.bin
> ```

---

## 📂 项目结构

```
cozywriter/
├── main.py                       # FastAPI 入口
├── config.py                     # pydantic-settings 配置
├── logger.py                     # 日志模块
├── requirements.txt
├── .env.example
├── run.bat / run.sh / run.ps1    # 跨平台启动脚本
│
├── llm/                          # LLM 抽象层
│   ├── base.py                   # LLMProvider 抽象基类
│   ├── anthropic_provider.py     # Claude
│   ├── openai_provider.py       # GPT
│   ├── minimax_provider.py       # MiniMax（Anthropic 兼容）
│   ├── ollama_provider.py        # Ollama 本地
│   ├── factory.py                # Provider 工厂
│   ├── roles.py                  # 17 种 LLM Role
│   ├── workflow.py               # Bootstrap 11-stage 工作流
│   └── chapter_pipeline.py       # 9 步章节生成流水线
│
├── rag/                          # RAG
│   ├── model_manager.py          # 模型下载/迁移（项目内扁平目录）
│   ├── embedder.py
│   ├── vector_store.py           # ChromaDB
│   ├── knowledge_base.py         # 知识库
│   └── retrieval.py              # 上下文检索
│
├── storage/                      # 数据层
│   ├── database.py               # SQLite（同步）
│   └── models/                   # SQLAlchemy ORM
│       ├── project.py
│       ├── chapter.py
│       ├── character.py
│       ├── world.py
│       ├── outline.py
│       ├── theme.py
│       ├── consistency.py
│       ├── review.py
│       ├── project_outline.py
│       ├── inspiration.py
│       ├── creative_questionnaire.py
│       └── workflow.py
│
├── api/routes/                   # FastAPI 路由（17 个）
│   ├── init.py / config.py / models.py / tasks.py
│   ├── projects.py / chapters.py
│   ├── characters.py / worldbuilding.py / outline.py / theme.py
│   ├── generate.py / review.py / consistency.py
│   ├── outline_detail.py / inspirations.py
│   ├── creative_questionnaire.py
│   └── workflow.py               # Bootstrap workflow 管理
│
├── data/                         # 用户数据（**不入 git**）
│   ├── cozywriter.db             # SQLite 主数据库
│   ├── chroma/                   # ChromaDB 向量库
│   ├── logs/                     # 日志（按天滚动）
│   └── models/moka-ai/m3e-base/  # Embedding 模型
│
└── web/                          # 前端 SPA（Alpine.js）
    ├── index.html
    └── static/
        ├── css/style.css
        └── js/app.js
```

---

## 🔌 API 概览

### 项目管理
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/projects` | 项目列表 |
| `POST` | `/api/projects` | 创建项目（**含 4 必填校验 + Bootstrap workflow 触发**） |
| `GET` | `/api/projects/{id}` | 项目详情 |
| `PUT` | `/api/projects/{id}` | 更新项目设置 |
| `DELETE` | `/api/projects/{id}` | 删除项目（级联删所有数据） |
| `GET` | `/api/projects/{id}/bootstrap-status` | Bootstrap workflow 状态 |

### 章节 + 9 步流水线
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/projects/{id}/chapters` | 章节列表 |
| `POST` | `/api/projects/{id}/chapters` | 新建章节 |
| `PUT` | `/api/chapters/{id}` | 更新章节（自动版本快照） |
| `POST` | `/api/chapters/{id}/rollback/{ver}` | 版本回滚 |
| **`POST`** | **`/api/chapters/generate-pipeline`** | **9 步流水线生成（同步 / 异步）** |

### 任务管理
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/tasks/{task_id}` | 单任务状态（轮询） |
| `GET` | `/api/tasks/all` | 所有任务 |
| `GET` | `/api/tasks/project/{project_id}` | 项目下任务 |
| **`POST`** | **`/api/tasks/terminate-all`** | **终止所有进行中任务** |
| `POST` | `/api/tasks/{task_id}/terminate` | 终止单个 |

### Bootstrap Workflow 管理
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/workflow/run/{run_id}` | 单 run 状态 |
| `GET` | `/api/workflow/project/{project_id}/latest` | 项目最新 run |
| **`GET`** | **`/api/workflow/in-flight`** | **进行中 run（用于跨页面恢复 wizard）** |
| `POST` | `/api/workflow/run/{run_id}/rerun` | 重跑某 stage |
| `POST` | `/api/workflow/run/{run_id}/commit` | 提交入库（auto_commit=false 时用） |

### 模型管理
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/models/status` | Embedding 模型状态 |
| `POST` | `/api/models/download` | **SSE 进度流式下载** |

### AI 生成 + 评审
| 方法 | 路由 | 说明 |
|---|---|---|
| `POST` | `/api/generate` | 单次文本生成（带 RAG 上下文） |
| `POST` | `/api/reviews` | 创建评审（同步） |
| `POST` | `/api/reviews/async` | 异步评审 |
| `POST` | `/api/reviews/{id}/revise` | 根据评审修订 |
| `GET` | `/api/projects/{id}/consistency/check` | 一致性检查 |
| `GET` | `/api/projects/{id}/consistency/report` | 一致性报告 |

### 角色 / 世界观 / 大纲 / 主题 / 灵感 / 伏笔 / 弧光
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/characters` | 角色 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/character-arcs` | 弧光 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/character-relations` | 关系矩阵 |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/worldbuilding` | 世界观 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/outline` | 大纲节点 |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/chapter-outlines` | 章节细纲 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/themes` | 主题 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/foreshadowings` | 伏笔 CRUD |
| `GET` `/POST` `/PUT` `/DELETE` | `/api/projects/{id}/inspirations` | 灵感 CRUD |

### 创意问卷
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/questions` | 获取问卷题目 |
| `GET` `/POST` | `/api/questionnaires` | 问卷 CRUD |
| `PUT` | `/api/questionnaires/{id}` | 更新问卷 |
| `POST` | `/api/questionnaires/{id}/build-project` | 根据问卷创建项目 |

### 初始化
| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/api/init/status` | 初始化状态（决定显示 Setup Wizard） |
| `POST` | `/api/config/save-provider` | 保存 Provider API Key |

---

## 🧠 LLM Role 体系（17 种）

### 基础写作（7 种）
| Role | 用途 |
|---|---|
| `novel_writer` | 小说续写（含风格/去 AI 味/字数约束） |
| `polisher` | 润色（保留情节，改善句式） |
| `reviewer` | 8 维度评审 + 建议 |
| `consistency_checker` | 一致性检查（人物/物品/能力/资源） |
| `outline_generator` | 章节细纲生成 |
| `reviser` | 根据评审意见修订 |
| `plot_planner` | 全书级大纲统筹 |

### Bootstrap（1 种）
| Role | 用途 |
|---|---|
| `bootstrap` | 项目引导补全（动态构造） |

### 9 步章节流水线（9 种）
| Role | 用途 |
|---|---|
| `chapter_outline_gen` | 生成章节细纲 |
| `outline_reviewer` | 细纲评审（仅过滤 high severity） |
| `compressor` | 缩写（字数过多时） |
| `expander` | 扩写（字数过少时） |
| `revision_decider` | 决定是否自动修订 |
| `post_chapter` | 弧光 + 关系 + 新角色更新 |
| `foreshadow_updater` | 伏笔状态机 |
| `golden_3_checker` | 黄金三章开局诊断 |
| `chapter_director` | 全书级统筹规划（情节/伏笔/弧光） |

---

## 💾 数据存储（项目内）

```
data/                              # 全部不入 git
├── cozywriter.db                  # SQLite 主数据库
├── chroma/                        # ChromaDB 向量库
├── logs/                          # 运行日志（按天滚动）
└── models/                        # Embedding 模型（项目内扁平）
    └── moka-ai/m3e-base/
        ├── config.json
        ├── model.safetensors
        ├── tokenizer.json
        ├── ...
```

`.env` 也**不入 git**（含真实 API Key）。  
`.env.example` 是公开模板。

---

## 🪵 日志

`data/logs/cozywriter_YYYYMMDD.log` 按天滚动：

- `INFO`：API 请求、任务开始/完成、LLM 调用
- `DEBUG`：LLM 请求详情（脱敏后的 prompt）
- `ERROR`：异常堆栈

---

## 🤝 贡献

欢迎 PR！建议方向：
- 新 LLM Provider（cohere / gemini / moonshot / 智谱 / 通义千问）
- 章节流水线新 stage（如多幕剧结构生成 / 文风迁移）
- 前端 UI 改进（基于 Alpine.js，保持轻量）
- 多语言 i18n

---

## 📄 License

MIT

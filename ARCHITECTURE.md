# CozyWriter 项目架构文档

> **梳理时间**: 2026-06-12  
> **项目版本**: 开发中  
> **技术栈**: FastAPI + SQLAlchemy + Alpine.js + ChromaDB

---

## 目录

1. [项目概览](#1-项目概览)
2. [目录结构](#2-目录结构)
3. [数据库模型](#3-数据库模型)
4. [API 路由](#4-api-路由)
5. [LLM 调用链路](#5-llm-调用链路)
6. [异步任务系统](#6-异步任务系统)
7. [9 步章节生成流水线](#7-9-步章节生成流水线)
8. [前端交互](#8-前端交互)
9. [核心工作流](#9-核心工作流)
10. [数据流图](#10-数据流图)

---

## 1. 项目概览

CozyWriter 是一个 AI 辅助小说编写系统，核心能力：

- **Bootstrap 流程**: 从用户输入的 4 个必填字段出发，自动生成世界观、角色、大纲、章节细纲等设定
- **章节生成流水线**: 9 步自动化流水线，从细纲生成到正文写作、评审、修订、保存
- **一致性检查**: 自动检测角色行为、时间线、伏笔等一致性问题
- **RAG 知识库**: 基于 ChromaDB 的向量检索，为 LLM 提供上下文

### 技术架构

```
┌─────────────────────────────────────────────┐
│                 浏览器 (Alpine.js)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 写作面板  │ │ 设定预览  │ │ 流水线进度    │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
└────────────────────┬────────────────────────┘
                     │ HTTP (fetch)
┌────────────────────▼────────────────────────┐
│              FastAPI 服务器                    │
│  ┌──────────────────────────────────────┐   │
│  │          API 路由 (api/routes/)       │   │
│  │  projects │ chapters │ workflow │ ... │   │
│  └──────────────┬───────────────────────┘   │
│                 │                            │
│  ┌──────────────▼───────────────────────┐   │
│  │       任务系统 (api/tasks.py)         │   │
│  │   ThreadPoolExecutor (max_workers=10)│   │
│  └──────────────┬───────────────────────┘   │
│                 │                            │
│  ┌──────────────▼───────────────────────┐   │
│  │       LLM 层 (llm/)                  │   │
│  │  factory → provider → generate()     │   │
│  └──────────────┬───────────────────────┘   │
│                 │                            │
│  ┌──────────────▼───────────────────────┐   │
│  │       存储层                          │   │
│  │  SQLAlchemy (SQLite) │ ChromaDB (RAG) │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 2. 目录结构

```
cozywriter/
├── main.py                    # FastAPI 入口，路由注册，中间件
├── config.py                  # 全局配置 (Pydantic Settings)
├── logger.py                  # 日志系统
├── migrate.py                 # 数据库迁移脚本
├── run.bat / run.ps1 / run.sh # 启动脚本
├── requirements.txt           # Python 依赖
├── .env                       # 环境变量（API keys）
│
├── api/
│   ├── tasks.py               # 异步任务系统（核心）
│   └── routes/
│       ├── projects.py        # 项目 CRUD
│       ├── chapters.py        # 章节 CRUD + 流水线入口
│       ├── workflow.py        # Bootstrap 工作流
│       ├── generate.py        # AI 生成（续写/扩写/润色）
│       ├── review.py          # 评审
│       ├── consistency.py     # 一致性检查
│       ├── characters.py      # 角色管理
│       ├── theme.py           # 主题/伏笔管理
│       ├── outline.py         # 大纲
│       ├── outline_detail.py  # 章节细纲
│       ├── inspirations.py    # 灵感库
│       ├── export.py          # 导出正文
│       ├── config.py          # LLM 配置 API
│       ├── models.py          # Pydantic 模型定义
│       ├── tasks.py           # 任务查询 API
│       └── ...
│
├── storage/
│   ├── database.py            # SQLAlchemy 引擎/Session
│   └── models/                # 数据库模型（16 个表）
│       ├── project.py         # Project
│       ├── chapter.py         # Chapter, ChapterVersion
│       ├── character.py       # Character, CharacterArc, CharacterRelation
│       ├── theme.py           # Theme, Foreshadowing
│       ├── outline.py         # OutlineNode
│       ├── project_outline.py # ProjectOutline, ChapterOutline
│       ├── review.py          # ReviewSession
│       ├── workflow.py        # WorkflowRun
│       ├── inspiration.py     # Inspiration
│       ├── consistency.py     # ConsistencyRecord
│       └── ...
│
├── llm/
│   ├── base.py                # LLMProvider 抽象基类
│   ├── factory.py             # LLMFactory（Provider 工厂）
│   ├── roles.py               # Prompt 角色定义（16 个 Role）
│   ├── chapter_pipeline.py    # 9 步章节生成流水线（核心，1468 行）
│   ├── anthropic_provider.py  # Anthropic Claude
│   ├── openai_provider.py     # OpenAI GPT
│   ├── ollama_provider.py     # Ollama 本地模型
│   ├── minimax_provider.py    # MiniMax
│   └── mimo_provider.py       # 小米 MiMo
│
├── rag/
│   ├── embedder.py            # 本地 Embedding (m3e-base)
│   ├── knowledge_base.py      # ChromaDB 知识库管理
│   └── retrieval.py           # RAG 检索服务
│
├── web/
│   ├── index.html             # 单页应用（Alpine.js，~1600 行）
│   └── static/
│       ├── css/style.css      # 样式
│       └── js/app.js          # 前端逻辑（~2870 行）
│
└── data/
    ├── cozywriter.db          # SQLite 数据库
    └── chroma/                # ChromaDB 向量数据库
```

---

## 3. 数据库模型

### 3.1 核心模型关系图

```
Project (1)
  ├── (1:N) Chapter ──── (1:N) ChapterVersion  (版本快照)
  ├── (1:N) Character ── (1:N) CharacterArc    (角色弧光)
  │         └── (N:N) CharacterRelation        (角色关系)
  ├── (1:N) Theme                              (主旨/基调/文风)
  ├── (1:N) Foreshadowing                      (伏笔)
  ├── (1:N) OutlineNode                        (大纲节点)
  ├── (1:1) ProjectOutline                     (项目大纲)
  ├── (1:N) ChapterOutline                     (章节细纲)
  ├── (1:N) ReviewSession                      (评审记录)
  ├── (1:N) WorkflowRun                        (Bootstrap 运行记录)
  ├── (1:N) Inspiration                        (灵感库)
  ├── (1:N) ConsistencyRecord                  (一致性记录)
  └── (1:N) WorldEntry                         (世界观条目)
```

### 3.2 关键模型字段

#### Project (项目)
| 字段 | 类型 | 说明 |
|------|------|------|
| title | String(255) | 项目标题 |
| description | Text | 项目描述 |
| word_count | Integer | 当前总字数 |
| writing_style | String(50) | 写作风格（默认"平实"） |
| ai味去除程度 | Integer | 去 AI 味强度 (0-10，默认 7) |
| target_word_count | Integer | 目标每章字数 (默认 3000) |
| word_count_min / max | Integer | 字数范围 (2000-5000) |
| total_chapters | Integer | 总章节数 |

#### Chapter (章节)
| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | FK → Project | 所属项目 |
| title | String(255) | 章节标题 |
| content | Text | 正文内容 |
| synopsis | Text | 章节梗概 |
| order | Integer | 排序序号 (0-based) |
| word_count | Integer | 字数 |

#### ChapterVersion (章节版本)
| 字段 | 类型 | 说明 |
|------|------|------|
| chapter_id | FK → Chapter | 所属章节 |
| content | Text | 版本快照内容 |
| version_num | Integer | 版本号 |

**关键行为**: 每次 PUT 更新章节时，自动创建版本快照（`api/routes/chapters.py:128-140`）

#### WorkflowRun (Bootstrap 运行)
| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | FK → Project | 所属项目 |
| status | String | pending / running / completed / failed |
| stage_results | JSON | 各阶段产出（结构化存储） |
| user_inputs | JSON | 用户原始输入 |

#### ChapterOutline (章节细纲)
| 字段 | 类型 | 说明 |
|------|------|------|
| chapter_id | FK → Chapter | 所属章节 |
| chapter_position | String | 章节位置（开篇/发展/高潮/结局） |
| key_content | Text | 核心内容 |
| plot_advance | Text | 情节推进 |
| conflicts | Text | 冲突 |
| highlights | Text | 高潮亮点 |
| target_word_count | Integer | 目标字数 |
| pacing | String | 节奏（快/中/慢） |
| foreshadow_ids | JSON | 关联伏笔 ID 列表 |

---

## 4. API 路由

### 4.1 路由前缀

| 模块 | 前缀 | 文件 |
|------|------|------|
| 项目管理 | `/api/projects` | `projects.py` |
| 章节管理 | `/api/projects/{pid}/chapters` | `chapters.py` |
| 章节流水线 | `/api/chapters` | `chapters.py` (pipeline_router) |
| Bootstrap 工作流 | `/api/workflow` | `workflow.py` |
| AI 生成 | `/api/generate` | `generate.py` |
| 角色 | `/api/projects/{pid}/characters` | `characters.py` |
| 主题/伏笔 | `/api/themes` | `theme.py` |
| 大纲 | `/api/outlines` | `outline.py` |
| 章节细纲 | `/api/outline-detail` | `outline_detail.py` |
| 评审 | `/api/reviews` | `review.py` |
| 一致性 | `/api/consistency` | `consistency.py` |
| 灵感库 | `/api/inspirations` | `inspirations.py` |
| 导出 | `/api/export` | `export.py` |
| 任务管理 | `/api/tasks` | `tasks.py` |
| 配置 | `/api/config` | `config.py` |

### 4.2 核心端点

#### 章节管理 (`chapters.py`)
```
GET    /projects/{pid}/chapters              # 列出章节
POST   /projects/{pid}/chapters              # 创建章节
GET    /projects/{pid}/chapters/{cid}        # 获取单章
PUT    /projects/{pid}/chapters/{cid}        # 更新章节（自动创建版本）
DELETE /projects/{pid}/chapters/{cid}        # 删除章节
GET    .../chapters/{cid}/versions           # 版本历史
POST   .../chapters/{cid}/rollback/{ver}     # 回滚到指定版本
```

#### 章节流水线 (`chapters.py` - pipeline_router)
```
POST   /api/chapters/generate-pipeline       # 启动 9 步生成流水线
POST   /api/chapters/revise                  # 启动修订流水线
```

#### Bootstrap 工作流 (`workflow.py`)
```
GET    /api/workflow/in-flight               # 进行中的 workflow
GET    /api/workflow/run/{run_id}            # 查询 run 状态
GET    /api/workflow/project/{pid}/latest    # 最新 run
GET    /api/workflow/project/{pid}/bootstrap-data  # 设定预览数据
POST   /api/workflow/run/{run_id}/rerun      # 重跑某阶段
POST   /api/workflow/run/{run_id}/rerun-all  # 重跑全部
POST   /api/workflow/run/{run_id}/commit     # 提交到数据库
POST   /api/workflow/run/{run_id}/rerun-and-commit  # 重跑+提交
```

#### AI 生成 (`generate.py`)
```
POST   /api/generate                         # 续写/扩写/润色/自由生成
```

#### 导出 (`export.py`)
```
POST   /api/export/chapters                  # 导出正文（支持重新分章、独立保存为 zip）
```

---

## 5. LLM 调用链路

### 5.1 Provider 体系

```
LLMProvider (ABC)           # llm/base.py
  ├── AnthropicProvider     # Claude
  ├── OpenAIProvider        # GPT
  ├── OllamaProvider        # 本地模型
  ├── MiniMaxProvider       # MiniMax M2.7
  └── MimoProvider          # 小米 MiMo

LLMFactory.create(provider, db)   # llm/factory.py
  优先级: 参数 > 数据库 SystemSetting > config.py
```

### 5.2 调用链路

```
前端/流水线
  │
  ▼
_call_llm(role_name, ctx, user_msg, provider, db)   # llm/chapter_pipeline.py:140
  │
  ├─ ROLES[role_name]         # llm/roles.py - 获取 Role 定义
  │   ├─ role.build_system()  # 构建 system prompt
  │   └─ role.build_user()    # 构建 user prompt（注入上下文）
  │
  ├─ LLMFactory.create()      # 创建 Provider 实例
  │
  └─ llm.generate(            # 调用 LLM
       prompt=user,
       system_prompt=system,
       max_tokens=role.max_tokens,
       temperature=role.temperature,
       task_type="chapter_pipeline_{role_name}"
     )
```

### 5.3 Role 清单 (llm/roles.py)

| Role 名称 | 用途 | 使用场景 |
|-----------|------|---------|
| `chapter_prep` | 聚合章节上下文 | 流水线 Step 1 |
| `chapter_outline_gen` | 生成章节细纲 | 流水线 Step 2 |
| `outline_reviewer` | 细纲评审 | 流水线 Step 3 |
| `writing` | 生成正文 | 流水线 Step 4 |
| `compressor` | 压缩文本 | 上下文窗口管理 |
| `expander` | 扩写文本 | 字数调整 |
| `review` | 正文评审 | 流水线 Step 6 |
| `revision_decider` | 修订决策 | 流水线 Step 7 |
| `revision` | 修订正文 | 流水线 Step 7 |
| `post_chapter` | 后处理（伏笔更新等） | 流水线 Step 9 |
| `foreshadow_updater` | 更新伏笔状态 | 后处理子步骤 |
| `golden_3_checker` | 黄金三章检查 | 后处理子步骤 |
| `chapter_director` | 章节导演（续写指导） | 续写生成 |
| `consistency` | 一致性检查 | 独立检查 |
| `outline` | 大纲生成 | Bootstrap |
| `polish` | 润色 | 独立润色 |
| `plot` | 情节分析 | 独立分析 |
| `bootstrap` | 动态生成 | Bootstrap 各阶段 |

### 5.4 RAG 检索

```
RetrievalService (rag/retrieval.py)
  │
  ├─ LocalEmbedder (rag/embedder.py)
  │   └─ 模型: moka-ai/m3e-base (HuggingFace)
  │
  └─ ChromaDB (data/chroma/)
      └─ 存储项目知识向量，支持语义检索
```

在章节生成前，`build_chapter_prep_info()` 会调用 RAG 检索相关上下文。

---

## 6. 异步任务系统

### 6.1 架构 (`api/tasks.py`)

```
ThreadPoolExecutor (max_workers=10, thread_name_prefix="llm_task")
  │
  ├─ Task 数据类
  │   ├─ id: str (UUID)
  │   ├─ task_type: str ("generate" / "review" / "chapter_pipeline")
  │   ├─ status: str ("pending" → "running" → "completed" / "failed")
  │   ├─ progress: int (0-100)
  │   ├─ result: Any
  │   └─ project_id, run_id
  │
  ├─ submit_llm_task(task_type, llm_call_fn, **kwargs)
  │   └─ 提交任务到线程池，立即返回 task_id
  │
  └─ get_task(task_id) → Task
      └─ 前端轮询用
```

### 6.2 任务生命周期

```
前端 POST 请求
  │
  ▼
submit_llm_task()           # 创建 Task 对象，提交到线程池
  │                          # 立即返回 task_id
  ▼
ThreadPoolExecutor          # 后台线程执行 LLM 调用
  │
  ├─ status = "running"     # 开始执行
  ├─ progress = 0-100       # 进度更新
  └─ status = "completed"   # 执行完成
     或 "failed"            # 执行失败

前端 GET /api/tasks/{task_id}   # 轮询（每 1-3 秒）
  └─ 获取 status, progress, result
```

### 6.3 取消机制

```
前端 → POST /api/tasks/{task_id}/cancel
  └─ task.cancelled = True
     ThreadPoolExecutor 检查 cancelled 标志，提前退出
```

---

## 7. 9 步章节生成流水线

### 7.1 流水线阶段 (`llm/chapter_pipeline.py`)

```
Step 1: 准备上下文 (1_prep, weight=1)
  └─ build_chapter_prep_info(db, project_id, chapter_id)
     聚合: 项目设定、大纲、前章摘要、角色、伏笔、一致性问题

Step 2: 生成章节细纲 (2_outline_gen, weight=2)
  └─ generate_chapter_outline(db, project_id, chapter_id, provider, guide)
     LLM → JSON 细纲

Step 3: 细纲评审 (3_outline_review, weight=1)
  └─ review_chapter_outline(outline, prep_info, provider)
     LLM → 评审意见
     如果 verdict="needs_revision" 且有 high severity → 自动修订细纲

Step 4: 生成正文 (4_text_gen, weight=4)
  └─ generate_chapter_text(db, project_id, chapter_id, outline, prep_info, provider)
     LLM → 正文文本

Step 5: 字数调整 (5_word_adjust, weight=1)
  └─ adjust_word_count(text, target, min, max, outline, provider)
     字数不足 → expander 扩写
     字数过多 → compressor 压缩

Step 6: 正文评审 (6_review, weight=2)
  └─ review_chapter_text(db, project_id, chapter_id, text, provider)
     LLM → 评审报告（评分 + 问题 + 建议）

Step 7: 修订决策 (7_revise, weight=3)
  └─ decide_revision(review_data, outline, content, provider)
     决策: "pass" / "revise"
     如果 decision="revise" 且 auto_revise=True:
       → revise_chapter_text() 修订正文
       → 可选: 修订后重审

Step 8: 保存到数据库 (8_save, weight=1)
  └─ chapter.content = final_text
     chapter.word_count = _count_chinese_chars(final_text)
     创建 ChapterVersion 快照
     db.commit()

Step 9: 后处理 (9_post, weight=2)
  └─ run_post_chapter_processing(db, project_id, chapter_id, final_text, provider)
     ├─ 更新伏笔状态
     ├─ 黄金三章检查 (前 3 章)
     └─ 快速一致性检查
```

### 7.2 进度回调机制

```python
# 每个 stage 开始/完成时调用
progress_cb(stage_id, status, info)
  # status: "running" | "completed" | "failed"
  # info: {label, weight, duration_ms, progress_pct, scores}

# 通过 task.result.stages 同步到前端
# 前端轮询 /api/tasks/{task_id} 获取最新状态
```

### 7.3 前端流水线交互

```
用户点击「一键生成」
  │
  ▼
POST /api/chapters/generate-pipeline → task_id
  │
  ▼
打开流水线进度浮层 (showPipelineProgress)
  │
  ▼
setInterval 轮询 /api/tasks/{task_id} (每 1 秒)
  ├─ 更新 stages UI（9 个步骤的进度）
  ├─ 显示当前阶段、耗时、评分
  └─ 终态 (completed/failed/cancelled) → 停止轮询
  │
  ▼
完成后 selectChapter() → GET 最新章节数据
  └─ 自动刷新编辑器内容
```

---

## 8. 前端交互

### 8.1 技术栈

- **Alpine.js 3.x**: 轻量响应式框架
- **单文件 SPA**: `web/index.html` (~1600 行) + `web/static/js/app.js` (~2870 行)
- **无构建步骤**: 直接加载，开发体验接近 Vue

### 8.2 核心数据状态

```javascript
// Alpine.js data 对象
{
  // 项目状态
  projects: [],
  currentProject: null,
  chapters: [],
  currentChapter: null,

  // 面板状态
  activePanel: 'writing',      // writing / themes / characters / ...
  subPanel: 'themes',

  // Bootstrap 数据
  bootstrapData: null,          // 设定预览数据

  // 流水线状态
  pipelineTask: null,           // 当前流水线任务
  showPipelineProgress: false,

  // 编辑状态
  chapterDirty: false,          // 用户手动编辑过
  chapterContentSnapshot: '',   // 内容快照（用于 diff）

  // 导出状态
  showExportModal: false,
  exportRechapter: false,
  exportSaveIndividual: false,

  // AI 生成
  showGenerateModal: false,
  generatedText: null,
  generating: false,
}
```

### 8.3 用户交互流程

#### 写作流程
```
选择章节 → 加载编辑器
  │
  ├─ 手动编辑 → textarea @input → onContentChange() → chapterDirty = true
  │   └─ 保存按钮可用 → 点击 → 二次确认（显示字数变化）→ PUT /chapters/{id}
  │
  ├─ AI 续写 → 生成文本 → insertGenerated() → 自动保存 (silent)
  │
  └─ 一键生成 → 9 步流水线 → 自动保存（Step 8）
      └─ 完成后自动刷新编辑器
```

#### 保存机制
| 触发方式 | 保存方式 | 用户确认 |
|---------|---------|---------|
| 手动编辑 → 保存按钮 | PUT /chapters/{id} | ✅ 二次确认 |
| AI 插入 (insertGenerated) | PUT /chapters/{id} (silent) | ❌ 自动 |
| Pipeline 生成 (Step 8) | 直接 db.commit() | ❌ 自动 |
| 修订 (runRevise) | 异步任务，后端自动保存 | ❌ 自动 |
| 编辑标题 (@change) | PUT /chapters/{id} | ❌ 自动 |

### 8.4 轮询机制

```javascript
// 1. 任务轮询 (refreshAllTasks)
setInterval(() => this.refreshAllTasks(), 3000)  // 每 3 秒

// 2. 流水线轮询
setInterval(() => this._pollPipeline(), 1000)    // 每 1 秒

// 3. Bootstrap 状态轮询
setInterval(() => this._pollBootstrapStatus(), 2000)  // 每 2 秒
```

---

## 9. 核心工作流

### 9.1 项目创建 → Bootstrap

```
用户填写 4 个必填字段（标题、描述、类型、字数目标）
  │
  ▼
POST /api/projects → 创建项目
  │
  ▼
POST /api/workflow/run → 启动 Bootstrap
  │
  ▼
后台线程执行 Bootstrap 各阶段:
  ├─ _meta: 收集用户输入
  ├─ base: 基础外推（总章节数、总字数）
  ├─ theme: 主旨 + 基调
  ├─ style: 文风 + 节奏
  ├─ world: 世界观
  ├─ characters: 角色设定
  ├─ arcs: 角色弧光
  ├─ outline: 项目大纲
  ├─ foreshadowings: 伏笔
  └─ chapter_outlines: 章节细纲
  │
  ▼
前端轮询进度 → 显示 Bootstrap 向导
  │
  ▼
用户审核设定 → POST /api/workflow/run/{id}/commit
  │
  ▼
commitBootstrap(): 将 stage_results 写入数据库各表
  ├─ Project (更新设定)
  ├─ Theme / Foreshadowing
  ├─ Character / CharacterArc / CharacterRelation
  ├─ WorldEntry
  ├─ ProjectOutline
  ├─ ChapterOutline (每章细纲)
  └─ 创建 Chapter (空章节)
```

### 9.2 章节生成

```
用户选择章节 → 点击「一键生成」
  │
  ▼
POST /api/chapters/generate-pipeline
  │
  ▼
9 步流水线（异步执行，见第 7 节）
  │
  ▼
Step 8: 自动保存到数据库
  │
  ▼
Step 9: 后处理（伏笔更新、一致性检查）
  │
  ▼
前端自动刷新编辑器
```

### 9.3 导出正文

```
用户点击「📤 导出」→ 打开导出浮层
  │
  ├─ 选择章节（全选/反选/单选）
  ├─ 可选: 重新分章（设置每章字数）
  ├─ 可选: 章节独立保存（每章一个文件 → zip）
  └─ 选择格式 (TXT / Markdown)
  │
  ▼
POST /api/export/chapters
  │
  ├─ 普通导出 → 单文件下载
  └─ 独立保存 → zip 压缩包下载
```

---

## 10. 数据流图

### 10.1 LLM 调用数据流

```
┌──────────┐     POST      ┌──────────┐    submit     ┌──────────────┐
│  浏览器   │ ────────────→ │ FastAPI   │ ────────────→ │ ThreadPool   │
│ (Alpine)  │               │ 路由      │               │ Executor     │
└──────────┘               └──────────┘               └──────┬───────┘
     │                                                       │
     │  GET /api/tasks/{id}                                  │
     │  (轮询)                                               │
     │                                                       ▼
     │                                              ┌──────────────────┐
     │                                              │ _call_llm()      │
     │                                              │  ├─ Role.build   │
     │                                              │  ├─ Factory      │
     │                                              │  └─ provider.gen │
     │                                              └────────┬─────────┘
     │                                                       │
     │                                                       ▼
     │                                              ┌──────────────────┐
     │                                              │ LLM API          │
     │                                              │ (Anthropic/OpenAI│
     │                                              │  /Ollama/...)    │
     │                                              └────────┬─────────┘
     │                                                       │
     │                                                       ▼
     │                                              ┌──────────────────┐
     │                                              │ 解析响应          │
     │                                              │ _parse_json()    │
     │                                              └────────┬─────────┘
     │                                                       │
     │                                                       ▼
     │                                              ┌──────────────────┐
     │                                              │ 写入数据库        │
     │                                              │ db.commit()      │
     │                                              └──────────────────┘
     │
     ▼
  前端更新 UI
```

### 10.2 Bootstrap 数据流

```
用户输入 (4 必填 + 8 选填)
  │
  ▼
POST /api/workflow/run
  │
  ▼
WorkflowRun 创建 (status=pending)
  │
  ▼
后台线程:
  ├─ 每个阶段 → LLM 生成 → stage_results[stage] = result
  ├─ progress_cb → 更新 WorkflowRun.stage_results
  └─ 最终 status = completed
  │
  ▼
前端轮询 → 渲染设定预览
  │
  ▼
用户确认 → POST /commit
  │
  ▼
commitBootstrap():
  ├─ stage_results → 解析各阶段产出
  ├─ 写入 Project / Theme / Character / ...
  ├─ 创建 Chapter + ChapterOutline
  └─ db.commit()
```

---

## 附录

### A. 启动方式

```bash
# Windows
run.bat
# 或
python main.py

# 服务地址
http://localhost:13567
```

### B. 配置项 (.env)

```env
# LLM Provider
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
MINIMAX_API_KEY=...
MIMO_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434

# 默认 Provider
DEFAULT_LLM_PROVIDER=anthropic

# Embedding
EMBEDDING_MODEL=moka-ai/m3e-base
HF_ENDPOINT=https://hf-mirror.com

# 数据库
DATABASE_URL=sqlite:///./data/cozywriter.db
```

### C. 关键文件索引

| 功能 | 文件 | 行数 |
|------|------|------|
| 9 步流水线 | `llm/chapter_pipeline.py` | 1468 |
| Prompt 角色 | `llm/roles.py` | 840 |
| 异步任务系统 | `api/tasks.py` | ~400 |
| Bootstrap 工作流 | `api/routes/workflow.py` | ~550 |
| 章节 API + 流水线入口 | `api/routes/chapters.py` | 452 |
| 前端逻辑 | `web/static/js/app.js` | 2870 |
| 前端页面 | `web/index.html` | ~1600 |
| 数据库模型 | `storage/models/` | 16 个文件 |

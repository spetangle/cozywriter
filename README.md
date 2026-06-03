# CozyWriter - AI 小说编写助手

基于 LLM API + RAG 知识管理的本地小说写作系统，支持 FastAPI Web 界面。

## 主要特性

### 创作管理
- **多项目管理**：独立项目隔离，支持小说标题、描述、总章节数配置
- **章节管理**：支持版本历史回滚（每次保存自动快照）
- **大纲 / 细纲**：
  - 项目级大纲：剧情线规划、起承转合结构、整体节奏说明
  - 章节细纲：定位（开局/高潮等）、节奏、字数目标、伏笔埋设、冲突看点

### 灵感收集
- **灵感记录**：随时记录写作灵感，支持打标签（脑洞/阅读/梦境/生活等）
- **标签管理**：按标签筛选灵感，灵感可关联角色/章节
- **独立项目隔离**：灵感池按项目隔离

### 创意问卷
- **12 步问卷引导**：类型/主题/基调/节奏/风格等核心问题
- **根据答案一键创建项目**：自动填入世界观/主角/基调/风格/字数估算
- **问卷模板持久化**：可随时继续/修改

### 角色与世界观
- **角色管理**：支持主角/配角/反派/龙套，含 JSON 自由字段
- **角色弧光**：成长型/堕落型/平线型/循环型，记录起止状态
- **关系矩阵**：多维度关系类型（友情/爱情/亲情/敌对等），强度可调
- **世界观设定**：分类管理（地理/历史/势力/规则等），标签支持

### 伏笔管理
- 伏笔埋入章节 → 回收章节跟踪
- 状态流转：active → planted → resolved / abandoned
- 超 3 章未回收自动预警

### 一致性保障
- 状态变更记录（角色能力/物品/资源）
- 自动检测：性格突变、物品数量错误、能力超出设定
- 字数波动检测（低于下限/超出上限）

### AI 辅助写作
- **7 种专属 Role**：小说续写 / 润色 / 评审 / 一致性检查 / 细纲生成 / 修订 / 大纲生成
- **RAG 上下文注入**：角色设定 + 世界观 + 章节摘要 + 伏笔 + 主题
- **字数把控**：项目级字数目标/下限/上限，AI 生成时自动约束
- **文风定制**：优美/幽默/冷峻/平实/诗意 + 去 AI 味强度（1-10）

### 智能评审
8 维度打分（0-10）：一致性 · 节奏 · 文笔 · 去 AI 味 · 字数合规 · 伏笔管理 · 角色弧光 · 主旨契合，含详细评审意见和修改建议，支持根据评审修订

### 系统稳定性
- **异步任务**：LLM 调用不阻塞主线程，任务状态轮询 API
- **超时保护**：180 秒任务超时限制
- **完整日志**：`data/logs/` 按天滚动，支持 DEBUG/INFO/ERROR 多级别
- **环境隔离**：API Keys 存储于 `.env`，不硬编码

---

## 快速开始

### 环境要求
- Python 3.10+
- Windows / Linux / macOS

### 安装

```bash
# 1. 克隆/下载项目
cd cozywriter

# 2. 创建虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
copy .env.example .env
# 编辑 .env，填入 API Key

# 5. 启动（首次会自动下载 embedding 模型）
python main.py
# 或双击 run.bat
```

访问 **http://localhost:13567**

### 首次运行引导

1. 选择 LLM Provider（Anthropic / OpenAI / Ollama）
2. 填入 API Key
3. 下载中文 embedding 模型（~400MB，约 5-10 分钟）
4. 进入写作台

---

## 项目结构

```
cozywriter/
├── main.py                    # FastAPI 入口
├── config.py                  # pydantic-settings 配置
├── logger.py                  # 日志模块
├── requirements.txt           # 依赖清单
├── .env.example              # 环境变量模板
│
├── llm/                      # LLM 抽象层
│   ├── base.py               # LLMProvider 抽象基类
│   ├── anthropic_provider.py  # Claude 实现
│   ├── openai_provider.py    # GPT 实现
│   ├── ollama_provider.py     # Ollama 实现
│   ├── factory.py            # Provider 工厂
│   └── roles.py              # 7 种专属 Role 模板
│
├── rag/                      # RAG 核心
│   ├── model_manager.py      # 模型下载管理（hf-mirror 加速）
│   ├── embedder.py           # sentence-transformers 封装
│   ├── vector_store.py       # ChromaDB 封装
│   ├── knowledge_base.py      # 知识库管理
│   └── retrieval.py          # 上下文检索 + Role 渲染
│
├── storage/                  # 数据层
│   ├── database.py           # SQLite 初始化
│   └── models/               # SQLAlchemy ORM（按领域拆分）
│       ├── project.py        # Project
│       ├── chapter.py        # Chapter / ChapterVersion
│       ├── character.py       # Character / CharacterArc / CharacterRelation
│       ├── world.py          # WorldEntry
│       ├── outline.py         # OutlineNode
│       ├── theme.py          # Theme / Foreshadowing
│       ├── consistency.py    # ConsistencyRecord
│       ├── review.py         # ReviewSession
│       └── project_outline.py # ProjectOutline / ChapterOutline
│
├── api/routes/               # API 路由（14 个模块）
│   ├── init.py              # 初始化状态检查
│   ├── config.py            # Provider 配置保存
│   ├── models.py            # 模型下载 API
│   ├── tasks.py             # 异步任务轮询
│   ├── projects.py          # 项目 CRUD
│   ├── chapters.py         # 章节 CRUD + 版本历史
│   ├── characters.py       # 角色管理
│   ├── worldbuilding.py    # 世界观管理
│   ├── outline.py         # 大纲节点
│   ├── generate.py         # AI 生成
│   ├── theme.py           # 主题/伏笔/弧光/关系
│   ├── consistency.py      # 一致性检查
│   ├── review.py          # 评审 + 修订
│   └── outline_detail.py  # 大纲/细纲
│
└── web/                    # 前端 SPA（Alpine.js）
    ├── index.html
    └── static/
        ├── css/style.css
        └── js/app.js
```

---

## API 概览

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/init/status` | 初始化状态检查 |
| POST | `/api/config/save-provider` | 保存 Provider 配置 |
| GET | `/api/models/status` | Embedding 模型状态 |
| POST | `/api/models/download` | 下载 Embedding 模型 |
| GET | `/api/projects` | 项目列表 |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}/chapters` | 章节列表 |
| POST | `/api/projects/{id}/chapters` | 创建章节 |
| PUT | `/api/chapters/{id}` | 更新章节（自动快照） |
| POST | `/api/chapters/{id}/rollback/{ver}` | 回滚版本 |
| GET | `/api/projects/{id}/themes` | 主题列表 |
| POST | `/api/projects/{id}/themes` | 创建主题 |
| GET | `/api/projects/{id}/foreshadowings` | 伏笔列表 |
| POST | `/api/projects/{id}/foreshadowings` | 创建伏笔 |
| GET | `/api/projects/{id}/character-arcs` | 角色弧光 |
| POST | `/api/projects/{id}/character-arcs` | 创建弧光 |
| GET | `/api/projects/{id}/character-relations` | 关系矩阵 |
| GET | `/api/projects/{id}/consistency/check` | 一致性检查 |
| GET | `/api/projects/{id}/consistency/report` | 一致性报告 |
| POST | `/api/generate` | AI 生成文本 |
| POST | `/api/reviews` | 创建评审（同步） |
| POST | `/api/reviews/async` | 异步评审（轮询） |
| GET | `/api/reviews/{id}` | 评审结果 |
| POST | `/api/reviews/{id}/revise` | 根据评审修订 |
| GET | `/api/projects/{id}/outline` | 获取项目大纲 |
| POST | `/api/projects/{id}/outline` | 保存项目大纲 |
| GET | `/api/projects/{id}/chapter-outlines` | 章节细纲列表 |
| GET | `/api/tasks/{task_id}` | 任务状态（轮询） |
| GET | `/api/tasks/project/{project_id}` | 项目任务列表 |
| GET | `/api/projects/{id}/inspirations` | 灵感列表（支持标签筛选） |
| POST | `/api/projects/{id}/inspirations` | 保存灵感 |
| DELETE | `/api/projects/{id}/inspirations/{insp_id}` | 删除灵感 |
| GET | `/api/questions` | 获取问卷题目列表 |
| GET | `/api/questionnaires` | 所有问卷列表 |
| POST | `/api/questionnaires` | 创建问卷 |
| PUT | `/api/questionnaires/{id}` | 更新问卷答案 |
| POST | `/api/questionnaires/{id}/build-project` | 根据问卷创建项目 |

---

## LLM Role 体系

| Role | 用途 | System Prompt 要点 |
|------|------|------------------|
| `novel_writer` | 小说续写 | 含风格指令、去 AI 味、主题/弧光/伏笔上下文，字数约束 |
| `polisher` | 润色 | 保留情节，改善句式，增强画面感 |
| `reviewer` | 评审 | 8 维度 JSON 评分 + critique + suggestions |
| `consistency_checker` | 一致性检查 | 识别矛盾点，JSON 返回 issues |
| `outline_generator` | 细纲生成 | 按结构/字数/伏笔要求输出 JSON 细纲 |
| `reviser` | 修订 | 根据评审意见修改原文 |
| `plot_planner` | 大纲生成 | 按总章节数输出剧情线 + 结构 + 节奏规划 |

---

## 日志说明

日志文件位于 `data/logs/cozywriter_YYYYMMDD.log`，每次启动自动创建新文件。

日志级别：
- `INFO`：API 请求、任务开始/完成、LLM 调用
- `DEBUG`：LLM 请求详情（脱敏后的 prompt）
- `ERROR`：异常堆栈

---

## 数据存储

所有数据全部存放在项目内 `data/` 目录下，**不依赖系统 `~/.cache/huggingface`**：

```
data/
├── cozywriter.db              # SQLite 主数据库
├── chroma/                    # ChromaDB 向量库
├── logs/                      # 日志（按天滚动）
└── models/                    # Embedding 模型（项目内扁平目录）
    └── moka-ai/
        └── m3e-base/
            ├── config.json
            ├── tokenizer.json
            ├── tokenizer_config.json
            ├── vocab.txt
            ├── modules.json
            └── sentencepiece.bpe.model
```

首次启动会下载 `moka-ai/m3e-base`（约 400MB）到 `data/models/moka-ai/m3e-base/`。

如果之前用过 `cache_dir` 嵌套结构（`data/models/models--moka-ai--m3e-base/snapshots/...`），
启动时会自动迁移到扁平目录。

---

## 环境变量

```bash
# .env

# LLM Provider（至少配置一个）
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
OLLAMA_BASE_URL=http://localhost:11434

DEFAULT_LLM_PROVIDER=anthropic

# Embedding 模型
EMBEDDING_MODEL=moka-ai/m3e-base
HF_ENDPOINT=https://hf-mirror.com

# 存储路径
DATA_DIR=./data
CHROMA_PERSIST_DIR=./data/chroma
DATABASE_URL=sqlite:///./data/cozywriter.db
```

---

## License

MIT

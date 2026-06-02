# 小说编写系统实现计划

## Context

用户需要构建一套本地小说写作辅助系统，核心需求：
- 通过 LLM API 完成文本生成（需支持多模型切换）
- 通过 RAG 知识管理保持前后文一致性（人物设定 + 已写章节回顾）
- 本地跑 embedding（sentence-transformers）
- **首次运行时引导配置大模型提供商 + 下载 embedding 模型（Setup Wizard）**
- **使用中文优化的 embedding 模型**
- FastAPI 提供 Web 界面
- 完整写作套件：项目/章节管理、大纲管理、版本历史、多文档管理
- **敏感信息（API Keys）存储于 `.env` 文件，不硬编码**
- **Python 项目，使用 venv 虚拟环境**

这是一个 greenfield 项目，目录为空，从头构建。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Web Layer                        │
│  (项目管理 / 章节编辑 / 角色管理 / 世界观 / 大纲 / 版本历史)      │
├──────────────────────────────────────────────────────────────┤
│                      Service Layer                            │
│  LLMService / RAGService / ProjectService / ChapterService   │
├──────────────────────────────────────────────────────────────┤
│                      Storage Layer                            │
│  SQLite (结构化数据) + ChromaDB (向量库) + 文件系统 (原始文本)  │
├──────────────────────────────────────────────────────────────┤
│                    Embedding / LLM Providers                  │
│  sentence-transformers (本地) / Claude / GPT / Ollama        │
└──────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
cozywriter/
├── main.py                      # FastAPI 入口
├── requirements.txt             # 依赖
├── requirements-dev.txt         # 开发依赖（pytest, black, ruff...）
├── .env.example                 # 环境变量模板
├── .env                         # 敏感信息（不提交到 git）
├── .gitignore
├── config.py                    # 配置（从 .env 读取，pydantic-settings）
├── llm/
│   ├── __init__.py
│   ├── base.py                  # LLMProvider 抽象基类
│   ├── anthropic_provider.py    # Claude 实现
│   ├── openai_provider.py       # GPT 实现
│   ├── ollama_provider.py       # Ollama 本地实现
│   └── factory.py               # provider 工厂
├── rag/
│   ├── __init__.py
│   ├── embedder.py              # 本地 embedding 封装
│   ├── vector_store.py          # ChromaDB 封装
│   ├── knowledge_base.py        # 知识库管理（角色/世界观）
│   ├── retrieval.py             # 检索逻辑
│   └── model_manager.py        # ⭐ 模型下载/管理（首次运行初始化）
├── storage/
│   ├── __init__.py
│   ├── database.py              # SQLite + SQLAlchemy 初始化
│   ├── models.py                # ORM 模型
│   └── repositories.py          # 数据访问层
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── init.py             # ⭐ 初始化状态检查
│   │   ├── config.py           # ⭐ Provider 配置保存
│   │   ├── models.py           # ⭐ 模型下载状态/触发
│   │   ├── projects.py         # 项目 CRUD
│   │   ├── chapters.py         # 章节 CRUD + 版本
│   │   ├── characters.py       # 角色管理
│   │   ├── worldbuilding.py    # 世界观管理
│   │   ├── outline.py          # 大纲管理
│   │   └── generate.py         # 生成接口
│   └── schemas.py              # Pydantic 请求/响应模型
├── web/
│   ├── index.html               # 单页应用入口
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           ├── app.js           # 主应用逻辑
│           └── setup.js         # ⭐ Setup Wizard 前端逻辑
└── tests/
    └── ...
```

---

## Embedding 模型选型（中文优化 + 国内可用）

### 推荐模型

| 模型 | 参数量 | 中文效果 | 下载地址 | 国内速度 |
|------|--------|---------|---------|---------|
| `moka-ai/m3e-base` | ~400MB | ⭐⭐⭐ 优秀 | HuggingFace / HF Mirror | 一般（推荐配镜像） |
| `BAAI/bge-large-zh-v1.5` | ~400MB | ⭐⭐⭐ 优秀 | HuggingFace / HF Mirror | 一般 |
| `shibing624/text2vec-base-chinese` | ~400MB | ⭐⭐ 良好 | HuggingFace / HF Mirror | 一般 |

**默认选择**：`moka-ai/m3e-base`（MokaAI 开发，中文语义效果突出）

### 国内下载加速

通过设置 `HF_ENDPOINT` 环境变量使用 HuggingFace 中国镜像：

```bash
# 写入 .env
HF_ENDPOINT=https://hf-mirror.com
```

---

## 首次运行初始化引导（Setup Wizard）

应用首次启动时，检测未配置项并弹出引导教程，逐步引导用户完成系统初始化。

### 引导流程（5 步）

```
第 1 步：欢迎页
  └─ "欢迎使用 CozyWriter，点击开始初始化你的写作环境"

第 2 步：选择 LLM 提供商
  ├─ [ ] Anthropic (Claude) — 需要 ANTHROPIC_API_KEY
  ├─ [ ] OpenAI (GPT) — 需要 OPENAI_API_KEY
  └─ [ ] Ollama (本地) — 需要 OLLAMA_BASE_URL

第 3 步：配置 API Key（根据第 2 步选择显示）
  └─ 输入框写入 .env 文件

第 4 步：Embedding 模型下载
  ├─ 默认模型：moka-ai/m3e-base（中文优化）
  ├─ 国内加速：已自动配置 HF Mirror（hf-mirror.com）
  └─ [下载模型] 按钮

第 5 步：完成
  └─ "初始化完成，开始你的第一本小说吧！"
```

### 前端引导状态管理

```javascript
// web/static/js/setup.js
const SetupWizard = {
  state: { step: 1, llmProvider: null, modelReady: false },

  async checkStatus() {
    const [modelRes, configRes] = await Promise.all([
      fetch('/api/models/status'),
      fetch('/api/init/status'),
    ])
    const model = await modelRes.json()
    const config = await configRes.json()
    if (config.providers_configured.length > 0 && model.downloaded) {
      return false
    }
    this.state.step = 1
    return true
  },

  async saveProviderStep(provider, apiKey) {
    await fetch('/api/config/save-provider', {
      method: 'POST',
      body: JSON.stringify({ provider, apiKey })
    })
    this.state.llmProvider = provider
    this.state.step = 4
  },

  async downloadModel() {
    const res = await fetch('/api/models/download', { method: 'POST' })
    const data = await res.json()
    if (data.status === 'downloaded') {
      this.state.modelReady = true
      this.state.step = 5
    }
  }
}
```

### 启动时引导拦截

```python
# api/routes/init.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/init", tags=["初始化"])

class InitStatusResponse(BaseModel):
    needs_setup: bool
    steps: dict

@router.get("/status", response_model=InitStatusResponse)
async def get_init_status():
    provider_configured = _check_provider_configured()
    model_downloaded = ModelManager().is_model_downloaded()
    needs_setup = not (provider_configured and model_downloaded)
    return InitStatusResponse(
        needs_setup=needs_setup,
        steps={"provider": provider_configured, "model": model_downloaded}
    )
```

### API 接口（新增）

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/init/status` | GET | 查询初始化状态（决定是否显示引导） |
| `/api/config/save-provider` | POST | 保存用户选择的 provider 和 API Key 到 .env |
| `/api/models/status` | GET | 查询 embedding 模型下载状态 |
| `/api/models/download` | POST | 下载模型 |

---

## 首次运行模型下载（model_manager.py）

```python
# rag/model_manager.py
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_check, snapshot_download
from pathlib import Path
import os
import gc

MODEL_CACHE_DIR = Path("./data/models")
DEFAULT_MODEL = "moka-ai/m3e-base"

class ModelManager:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.cache_dir = MODEL_CACHE_DIR
        self._model = None

    def is_model_downloaded(self) -> bool:
        try:
            return snapshot_check(self.model_name, cache_dir=str(self.cache_dir))
        except Exception:
            return False

    def download_model(self) -> str:
        return snapshot_download(
            self.model_name,
            cache_dir=str(self.cache_dir),
            resume_download=True,
        )

    def load_model(self):
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, cache_folder=str(self.cache_dir))
        return self._model

    def unload_model(self):
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()
```

---

## 核心模块设计

### 1. LLM Provider 抽象层 (`llm/`)

```python
# llm/base.py
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str: ...
    @abstractmethod
    def get_context_window(self) -> int: ...

# llm/factory.py
class LLMFactory:
    @staticmethod
    def create(provider: str, **config) -> LLMProvider:
        return {
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "ollama": OllamaProvider,
        }[provider](**config)
```

### 2. RAG 系统 (`rag/`)

**Embedding**：`LocalEmbedder`（延迟加载）
```python
# rag/embedder.py
class LocalEmbedder:
    def __init__(self, model_name: str | None = None):
        self._manager = ModelManager(model_name)
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self._model = self._manager.load_model()
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def unload(self):
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()
```

**向量存储**: ChromaDB
```python
# rag/vector_store.py
import chromadb
class VectorStore:
    def __init__(self, persist_path="./data/chroma"):
        self.client = chromadb.PersistentClient(persist_path)
```

**知识库 Collection**：
- `characters` — 角色设定
- `worldbuilding` — 世界观设定
- `chapters` — 已写章节

### 3. 数据模型 (`storage/`)

**SQLite + SQLAlchemy ORM**

| Model | Fields |
|-------|--------|
| Project | id, title, description, created_at, updated_at |
| Chapter | id, project_id, title, order, content, word_count, created_at, updated_at |
| ChapterVersion | id, chapter_id, content, version_num, created_at |
| Character | id, project_id, name, profile (JSON), description |
| WorldEntry | id, project_id, category, title, content |
| OutlineNode | id, project_id, parent_id, title, content, order |

### 4. API 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/init/status` | GET | 初始化状态检查 |
| `/api/config/save-provider` | POST | 保存 provider 到 .env |
| `/api/models/status` | GET | embedding 模型下载状态 |
| `/api/models/download` | POST | 下载 embedding 模型 |
| `/api/projects` | GET/POST | 项目列表 / 创建 |
| `/api/projects/{id}` | GET/PUT/DELETE | 项目 CRUD |
| `/api/projects/{id}/chapters` | GET/POST | 章节列表 / 创建 |
| `/api/chapters/{id}` | GET/PUT/DELETE | 章节 CRUD |
| `/api/chapters/{id}/versions` | GET | 版本历史 |
| `/api/chapters/{id}/rollback/{version}` | POST | 回滚 |
| `/api/projects/{id}/characters` | GET/POST/PUT/DELETE | 角色管理 |
| `/api/projects/{id}/worldbuilding` | GET/POST/PUT/DELETE | 世界观管理 |
| `/api/projects/{id}/outline` | GET/POST/PUT/DELETE | 大纲管理 |
| `/api/generate` | POST | 文本生成（带 RAG） |

### 5. 生成接口

```python
# 请求
{
    "project_id": int,
    "chapter_id": int | null,
    "prompt": str,
    "mode": "continue" | "polish" | "expand",
    "provider": str | null
}

# 流程
1. 检索角色 + 世界观 → system_prompt
2. 检索已写章节（近 N 章 + 语义相似片段）→ context
3. 拼接 → 调用 LLM → 返回生成文本
```

### 6. Web 前端

SPA（Alpine.js，保持轻量），功能页面：
- **设置页** — Setup Wizard（首次运行强制显示）
- **项目列表页** — 所有小说项目
- **写作台** — 核心编辑界面
- **角色/世界观/大纲面板** — 侧边管理
- **版本历史** — diff 视图

---

## 实现步骤

### Phase 1：项目骨架
1. 初始化目录结构，创建 `config.py`、`.env.example`
2. 配置 SQLite + SQLAlchemy ORM
3. 配置 ChromaDB 初始化
4. 实现 `LLMProvider` 抽象基类和 factory

### Phase 2：模型下载（首次运行）
5. 实现 `rag/model_manager.py`（下载/检测/缓存管理）
6. 实现 `/api/init/status` + `/api/models/status` + `/api/models/download`
7. 实现 `/api/config/save-provider`（写入 .env）
8. 前端 Setup Wizard UI（5 步引导）

### Phase 3：RAG 核心
9. 实现 `LocalEmbedder` + `VectorStore`
10. 实现 `KnowledgeBase`（角色/世界观/章节索引）
11. 实现 `RetrievalService`（查询 → 拼接上下文）

### Phase 4：LLM 集成
12. 实现 `AnthropicProvider`、`OpenAIProvider`、`OllamaProvider`
13. 实现 `/api/generate` 接口

### Phase 5：业务 API
14. 项目管理、章节管理 CRUD + 版本历史
15. 角色管理、世界观管理、大纲管理

### Phase 6：前端
16. SPA：项目列表 → 写作台（核心）
17. 角色/世界观/大纲面板
18. 版本历史 + diff 视图
19. 设置页（API Key 管理）

### Phase 7：收尾
20. `.gitignore`、目录初始化（自动创建 `data/` 目录）

---

## 依赖 (`requirements.txt`)

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.0
chromadb>=0.4.0
sentence-transformers>=2.2.0
huggingface-hub>=0.20.0
anthropic>=0.18.0
openai>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-multipart>=0.0.9
python-dotenv>=1.0.0
```

## 环境变量配置

```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_PROVIDER=anthropic
EMBEDDING_MODEL=moka-ai/m3e-base
HF_ENDPOINT=https://hf-mirror.com
DATA_DIR=./data
CHROMA_PERSIST_DIR=./data/chroma
DATABASE_URL=sqlite+aiosqlite:///./data/cozywriter.db
```

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "anthropic"
    embedding_model: str = "moka-ai/m3e-base"
    hf_endpoint: str = "https://hf-mirror.com"
    data_dir: str = "./data"
    chroma_persist_dir: str = "./data/chroma"
    database_url: str = "sqlite+aiosqlite:///./data/cozywriter.db"
```

---

## 验证计划

1. **首次运行验证**：清空 `data/` 目录后启动，确认弹出 Setup Wizard
2. **下载完成验证**：`POST /api/models/download` 后，模型文件出现在 `data/models/` 下
3. **生成测试**：创建项目 → 添加角色 → 生成文本，验证 RAG 上下文注入
4. **版本回滚**：保存章节 → 修改 → 回滚到旧版本，验证内容正确恢复
5. **多模型切换**：配置多个 LLM provider，验证生成结果差异

---

## 关键文件清单

| 文件 | 作用 |
|------|------|
| `.env.example` + `config.py` | 环境变量模板 + pydantic-settings 配置 |
| `rag/model_manager.py` | ⭐ 模型下载/检测/缓存管理（首次运行核心） |
| `api/routes/init.py` | ⭐ 初始化状态检查 + Setup Wizard API |
| `api/routes/config.py` | ⭐ Provider 配置保存（写入 .env） |
| `llm/base.py` + `factory.py` | LLM 抽象层核心 |
| `rag/embedder.py` + `vector_store.py` | 本地 embedding + 向量库 |
| `rag/knowledge_base.py` + `retrieval.py` | 知识库管理 + 检索 |
| `storage/models.py` | 所有 ORM 模型 |
| `api/routes/generate.py` | 核心生成接口 |
| `web/static/js/setup.js` | ⭐ Setup Wizard 前端逻辑 |

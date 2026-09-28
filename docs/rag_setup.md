# RAG（向量检索）启用说明

CozyWriter 的 RAG 用于：
- 检索「已发生事件」的相似过去章节，辅助防止剧情重复；
- 一致性检查 / 评审时提供相关上下文。

RAG 支持两种 embedding 来源，可在「全局设置 → RAG 向量」里切换：

| 模式 | 依赖 | 说明 |
|---|---|---|
| **本地 CPU** | `sentence-transformers` + `moka-ai/m3e-base` | 完全离线，强制 `device="cpu"` |
| **在线 API** | OpenAI 兼容 `/embeddings` 服务 | 无需下载模型，填 Base URL / 模型名 / API Key |

未启用 RAG 时系统仍可正常写作，但：
- RAG 相似事件检索会跳过；
- 去重与一致性检查效果弱于启用 RAG。

## 如何判断是否已启用

- 项目编辑页顶栏：未启用时显示 **`⚠️ RAG 未启用`**；
- 接口：`GET /api/config/status` 返回 `rag_enabled` / `rag_model` / `rag_mode`；
- 接口：`GET /api/config/rag` 返回当前模式与在线配置。

## 方式一：本地 CPU 模型

### 步骤 0：安装依赖（不会装 nvidia-*）

```bash
./tools/install_rag_cpu.sh          # Linux / macOS
.\tools\install_rag_cpu.ps1         # Windows PowerShell
tools\install_rag_cpu.bat           # Windows CMD
```

脚本会：卸载 CUDA 版 torch → 安装 CPU 版 torch → 安装 `requirements-rag.txt` → 清理残留 `nvidia-*`。

手动方式：
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-rag.txt
```

### 步骤 1：准备模型

**网页下载（推荐）**：打开「全局设置 → 模型管理」，下载 `moka-ai/m3e-base`（有 SSE 进度）。

**手动放置**：把模型文件放到 `data/models/moka-ai/m3e-base/`，至少包含以下之一即可被识别：
`config.json` / `modules.json` / `tokenizer_config.json`。

```
data/
└── models/
    └── moka-ai/
        └── m3e-base/
            ├── config.json
            ├── model.safetensors
            ├── tokenizer.json
            ├── tokenizer_config.json
            ├── vocab.txt
            ├── modules.json
            └── sentence_bert_config.json
```

**HF 镜像加速**：代码默认 `HF_ENDPOINT=https://hf-mirror.com`。

**官方 CLI**：
```bash
huggingface-cli download moka-ai/m3e-base --local-dir ./data/models/moka-ai/m3e-base
```

### 步骤 2：在「全局设置 → RAG 向量」选择“本地 CPU 模型”，点「测试连接」

### 模型文件大小说明

- `model.safetensors`：~390MB，优先加载；
- `pytorch_model.bin`：旧格式，可删除以省 ~390MB：
  ```bash
  rm data/models/moka-ai/m3e-base/pytorch_model.bin
  ```

## 方式二：在线 Embedding API

1. 打开「全局设置 → RAG 向量」；
2. 模式选择“在线 Embedding API”；
3. 填写：
   - **Base URL**：OpenAI 兼容地址，如 `https://api.openai.com/v1`
   - **模型名**：如 `text-embedding-3-small`
   - **API Key**
4. 点「测试连接」，成功后「保存」。

> 切换本地/在线或更换 embedding 模型后，向量维度会变化，请点 **「♻️ 重置向量库」**，
> 下次写入时会按新模型重建空 collection。

## 相关接口

| 方法 | 路由 | 说明 |
|---|---|---|
| `GET`/`PUT` | `/api/config/rag` | 读取 / 更新 RAG 模式与在线配置 |
| `POST` | `/api/config/rag/test` | 测试当前（或传入）配置是否可用 |
| `POST` | `/api/config/rag/reset` | 清空向量库，等待重建 |

## 启用后建议复测

1. 生成一章后查看「📚 已发生事件 + RAG 相似过去章节」是否出现相似度；
2. 连续生成 ≥5 章，确认一致性检查产生 `ConsistencyRecord`；
3. 若出现 `RAG event index failed` 警告，检查依赖或在线 Key/额度。


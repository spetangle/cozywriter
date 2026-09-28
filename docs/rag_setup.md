# RAG（向量检索）启用说明

CozyWriter 的 RAG 用于：
- 检索「已发生事件」的相似过去章节，辅助防止剧情重复；
- 一致性检查 / 评审时提供相关上下文。

RAG 依赖本地 embedding 模型 **`moka-ai/m3e-base`**（约 400MB）。未下载时系统仍可正常写作，但：

- `build_chapter_prep_info` 的 RAG 相似事件检索会跳过（日志会提示失败）；
- 每 5 章的一致性检查、事件去重依赖文本摘要，效果弱于启用 RAG。

## 如何判断是否已启用

- 项目编辑页顶栏：未启用时显示 **`⚠️ RAG 未启用`**；
- 接口：`GET /api/config/status` 返回 `rag_enabled` / `rag_model`；
- 接口：`GET /api/init/status` 返回 `model_downloaded`。

## 如何启用

### 方式一：网页下载（推荐）

1. 打开「全局设置」；
2. 在模型管理里下载 `moka-ai/m3e-base`（会显示进度）；
3. 下载完成后刷新项目页，`⚠️ RAG 未启用` 提示消失。

模型落盘位置：`data/models/moka-ai/m3e-base/`。

### 方式二：手动放置

把模型文件放到 `data/models/moka-ai/m3e-base/`，至少包含 `config.json` 之一即可被识别。

## 首次联网

模型从 HuggingFace 下载，默认走镜像 `HF_ENDPOINT=https://hf-mirror.com`（见 `.env`）。
国内网络可保持默认；无法访问时可在 `.env` 调整 `HF_ENDPOINT`。

## 启用后建议复测

1. 生成一章后查看「📚 已发生事件 + RAG 相似过去章节」是否出现相似度；
2. 连续生成 ≥5 章，确认一致性检查产生 `ConsistencyRecord`；
3. 若出现 `RAG event index failed` 警告，检查 `sentence-transformers` 是否安装。

# LLM 超参数配置指南

## 概述

本系统支持按 LLM 提供商和任务类型配置不同的超参数方案。不同的小说生成任务需要不同的超参配置，以获得最佳的生成效果。

## 超参数说明

### 核心超参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| temperature | float | 0.7 | 温度系数，控制生成的随机性。0=确定性，1=随机性强 |
| top_p | float | 0.9 | 核采样概率阈值，只保留累积概率超过此值的 token |
| max_tokens | int | 4096 | 最大生成长度（token） |
| frequency_penalty | float | 0.0 | 频率惩罚，降低重复token的概率 |
| presence_penalty | float | 0.0 | 存在惩罚，降低已出现token的概率 |
| top_k | int | 0 | Top-K 采样，只从概率最高的 K 个 token 中选择 |
| repetition_penalty | float | 1.0 | 重复惩罚（Ollama专用），大于1时降低重复 |

### 参数影响分析

- **temperature**: 越高越有创意但可能偏离主题，越低越保守但可能过于机械
- **top_p**: 越小越集中于高概率token，越大越多样化
- **frequency_penalty**: 高值减少重复内容，适合长篇生成
- **presence_penalty**: 高值促进新话题引入，适合创意生成

## 任务类型与推荐配置

### 配置方案总览

#### 方案 A：创意生成类（高温度）
适用于需要丰富创意和细节的任务

| 任务类型 | temperature | top_p | max_tokens | 说明 |
|---------|------------|-------|------------|------|
| 角色生成 | 0.85 | 0.90 | 2048 | 需要丰富的人物细节和创意设定 |
| 正文生成 | 0.80 | 0.90 | 8192 | 需要流畅的叙事和生动的描写 |
| 扩写 | 0.70 | 0.90 | 6144 | 需要丰富细节但保持原有结构 |

#### 方案 B：逻辑结构类（中温度）
适用于需要逻辑性和结构性的任务

| 任务类型 | temperature | top_p | max_tokens | 说明 |
|---------|------------|-------|------------|------|
| 大纲生成 | 0.70 | 0.95 | 4096 | 需要整体结构和逻辑性 |
| 细纲生成 | 0.75 | 0.92 | 3072 | 需要详细场景设计和逻辑连贯 |

#### 方案 C：分析评审类（低温度）
适用于需要客观分析和严谨判断的任务

| 任务类型 | temperature | top_p | max_tokens | 说明 |
|---------|------------|-------|------------|------|
| 评审 | 0.30 | 0.80 | 2048 | 需要客观分析和评分 |
| 一致性检查 | 0.20 | 0.70 | 2048 | 需要严谨的前后对比 |
| 修订决策 | 0.20 | 0.70 | 512 | 需要客观判断是否修订 |
| 事件签名抽取 | 0.20 | 0.70 | 512 | 需要简洁准确的概括 |
| 伏笔更新 | 0.30 | 0.80 | 1024 | 需要逻辑判断状态变化 |
| 黄金三章检查 | 0.30 | 0.80 | 2048 | 需要专业分析 |

#### 方案 D：修订优化类（中低温度）
适用于需要保持风格一致性的修订任务

| 任务类型 | temperature | top_p | max_tokens | 说明 |
|---------|------------|-------|------------|------|
| 修订 | 0.50 | 0.85 | 8192 | 需要保持原有风格同时改进 |
| 缩写 | 0.40 | 0.80 | 4096 | 需要保留核心内容 |
| 细纲评审 | 0.30 | 0.80 | 1536 | 需要严格把关细纲质量 |

### 按提供商的特殊配置

#### OpenAI (GPT)
- 默认使用 temperature + top_p 组合
- 推荐使用 frequency_penalty 控制长篇生成的重复

#### Anthropic (Claude)
- Claude 对温度变化更敏感
- 推荐稍低的 temperature 保持稳定性

#### Ollama (本地模型)
- 本地模型通常需要更高的 temperature 激发创意
- 需要配置 repetition_penalty 控制重复
- 建议设置 top_k=40 或更高

#### MiniMax / Mimo
- 遵循通用配置原则
- 根据模型特性微调 temperature

## API 接口

### 列出所有配置
```
GET /api/llm-hyperparams/presets
```

### 获取指定配置
```
GET /api/llm-hyperparams/presets/{provider}/{task_type}
```

### 创建配置
```
POST /api/llm-hyperparams/presets
```

请求体：
```json
{
  "provider": "openai",
  "task_type": "generate_character",
  "name": "角色生成",
  "description": "生成人物设定",
  "temperature": 0.85,
  "top_p": 0.9,
  "max_tokens": 2048
}
```

### 更新配置
```
PUT /api/llm-hyperparams/presets
```

### 删除配置
```
DELETE /api/llm-hyperparams/presets/{preset_id}
```

### 初始化默认配置
```
POST /api/llm-hyperparams/initialize
```

## 配置策略建议

### 1. 分层配置策略
- **项目级别**: 使用系统默认配置
- **任务级别**: 根据任务类型自动选择配置
- **章节级别**: 允许手动覆盖特定章节的配置

### 2. 渐进式调整
- 初始使用推荐配置
- 根据生成质量逐步调整 temperature
- 长篇生成时逐步增加 frequency_penalty

### 3. 质量监控
- 定期检查生成质量
- 根据评审结果调整配置
- 记录不同配置的效果对比

## 附录：任务类型列表

| 任务类型 | 描述 | 所属方案 |
|---------|------|---------|
| generate_character | 生成人物设定 | A |
| generate_outline | 生成小说大纲 | B |
| generate_chapter_outline | 生成章节细纲 | B |
| generate_chapter_text | 生成小说正文 | A |
| review | 评审章节内容 | C |
| consistency_check | 一致性检查 | C |
| revision | 修订章节内容 | D |
| golden_3_check | 黄金三章检查 | C |
| post_chapter | 章节后处理 | D |
| foreshadow_updater | 伏笔更新 | C |
| event_signature_extractor | 事件签名抽取 | C |
| expander | 扩写正文 | A |
| compressor | 缩写正文 | D |
| revision_decider | 修订决策 | C |
| outline_reviewer | 细纲评审 | D |
| default | 默认配置 | - |
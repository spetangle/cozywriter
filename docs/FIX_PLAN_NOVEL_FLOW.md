# 小说流程测试发现 · 修改方案

> 依据：`docs/TEST_REPORT_NOVEL_FLOW.md`（真实 LLM 跑通「问卷建项目 → bootstrap → 连续生成 10 章」后暴露的问题）
> 状态：`P0/P1` 中部分已在 `35cd1e1` 修复，本方案补齐剩余项
> 制定时间：2026-09-26

---

## 0. 问题清单与优先级

| 编号 | 问题 | 严重度 | 现状 |
|---|---|---|---|
| P0-1 | 细纲重写丢失 `chapter_num` / `previous_events`，重写内容与前面章节重复 | 高 | ✅ 已修（`35cd1e1`） |
| P0-2 | `consistency_checker` 缺 `content`，每 5 章一致性检查空转 | 高 | ✅ 已修（`35cd1e1`） |
| P1-3 | `adjust_word_count` 压缩/扩写不稳定，落点可偏离目标 ±250 字 | 中高 | ⏳ 待修 |
| P1-4 | 单章正文可远超字数上限（第 7 章 2640 字 vs 目标 800） | 中高 | ⏳ 待修 |
| P1-5 | DeepSeek JSON 模式返回空响应，降级后仍为空 | 中 | ⏳ 待修 |
| P2-6 | RAG（embedding）未参与，事件去重/相似度拦截失效 | 中 | ⏳ 环境问题，需复测 |
| P2-7 | 角色弧光/关系/伏笔等后处理结果只在日志可见，前端未接线 | 低 | ⏳ 待接线 |

---

## 1. P0-1（已修）细纲重写上下文

**根因**：`_revise_outline()` 调 `chapter_outline_gen` role 时，只传了 6 个上下文键，
模板需要的 `chapter_num`、`previous_events` 缺失，渲染成「第（未提供）章」，
且模型看不到硬约束「已发生事件」，从而重写重复。

**已做**：`llm/chapter_pipeline.py` 的 `_revise_outline` 补 `chapter_num`、
`previous_events`，并把 `prep["chapter_outline"]` 取值改为 `.get()` 兜底。

**回归建议**：保留一个纯函数级测试（无需真实 LLM），断言渲染后的
`chapter_num` 为 `order+1`、`previous_events` 非空占位。

---

## 2. P0-2（已修）一致性检查上下文

**根因**：`run_quick_consistency_check()` 把 `content` 放进了 system 模板 ctx，
但 `CONSISTENCY_SYSTEM` 没有 `{content}` 占位符，导致 `str.format` 抛
KeyError 后被兜底成空模板；LLM 只收到「待检查文本：（content 未提供）」。

**已做**：`content` 改由 user 消息传入；`world` / `foreshadowings` 填真实数据；
返回结果做 `dict` 校验。

**回归建议**：断言 `ctx` 不含 `content`、user 消息包含正文前若干字。

---

## 3. P1-3 字数调整不稳定

### 现象
- 第 7 章：正文 2640 字（目标 800），压缩后仍超标，最终选“最接近”候选。
- 第 10 章：1050 → 压缩到 666（下限 720），二次调整返回同一结果，最终偏差 134 字。

### 根因分析
1. **单次压缩幅度不可控**：`compressor` 只给“区间”，没给“从当前字数减到目标附近”的量化指令，模型容易一次砍太多。
2. **二次调整无区分**：第二轮只是提高 temperature，但 `ctx["content"]` 已被换成第一轮结果，模型倾向复述同一段。
3. **候选选择只看与 target 的绝对差**，没有“优先选落在区间内的候选”这一层。
4. **超长正文压缩一次可能仍超限**：`max_adjust_attempts=2` 且未对“压缩不足”做多次收敛。

### 修改方案
文件：`llm/chapter_pipeline.py` 的 `adjust_word_count()`；`llm/roles.py` 的 COMPRESS/EXPAND 模板。

1. **在 prompt 里给量化目标**：
   - 压缩：显式给出 `需删减 ≈ {current_word_count - target_word_count} 字`，并分档
     （“先删环境/次要对话，再删重复心理描写，不得删主线事件”）。
   - 扩写：给出 `需补充 ≈ {target_word_count - current_word_count} 字`，指定补充维度顺序。
2. **调整次数与收敛策略**：
   - 将 `max_adjust_attempts` 从 2 提升到 3。
   - 每轮把上一轮结果与“距区间中心偏差”一起传入，要求“只做小幅修正（±15% 内）”。
   - 第二轮起 temperature 递增保留，但 `ctx` 增加 `previous_attempt_count` 与
     `last_delta`，提示模型“上一轮过冲/不足”。
3. **候选选择加优先级**：
   - 先在所有候选里找 `min_w <= n <= max_w` 的，取离 `target` 最近者；
   - 若都不在区间，再按“是否越过越界方向”惩罚（过短/过长分开），最后才用绝对值差。
4. **保护性短路**：若压缩后字数 < `min_w * 0.9`，视为“过冲失败”，
   直接丢弃该候选并记录 warning，不进入候选池。

### 回归
- 纯函数测试：构造 3 组假 LLM 输出（过冲、不足、命中），断言最终选择的候选优先级正确。
- 真实流程小样本：目标 800 字，输入 1050 / 2640 两种正文，观察落点是否进区间。

---

## 4. P1-4 单章严重超字数

### 现象
第 7 章 2640 字，是目标 800 的 3.3 倍，且 `WordAdjust` 未能收敛。

### 根因分析
1. `calculate_max_tokens` 按 `max_words` 计算，但 role 默认 `max_tokens=2048`；
   长内容时模型输出被允许到 ~2048 tokens（约 1500+ 汉字），本身就给超长留了空间。
2. `_generate_text` 只校验 `len(text) > 100` 即视为成功，没有“超过上限太多就重生成”的策略。
3. 超长正文进入 Step5 压缩，压缩器上限 `max_tokens = int(max_w * 1.3)` 偏小，
   长文压缩时输出空间不足，容易截断或只压缩一部分。

### 修改方案
文件：`llm/chapter_pipeline.py`

1. **生成阶段加上限校验**：`_generate_text` 命中后，若
   `actual > max_words * 1.8`，视为生成失控，重试一次（并在 prompt 里强调字数上限）；
   仍失控则进入压缩，但标记 `over_length=True`。
2. **压缩阶段动态 `max_tokens`**：压缩器的 `max_tokens` 由
   `目标区间上限` 而不是“当前字数”决定，避免因当前超长而放开输出。
3. **压缩闭环**：若首轮压缩后仍 > `max_w * 1.5`，允许追加一轮“仅删减”压缩。
4. **落库前最终防线**：Step8 保存前，若字数仍超 `max_w * 2`，
   记录 warning 并在 `Chapter.fingerprint` 标注 `word_count_overflow`，方便前端提示。

### 回归
- 真实流程：目标 800 字生成 5 章，统计“进入区间比例”与最大偏差，目标 ≥ 80% 命中。

---

## 5. P1-5 DeepSeek JSON 模式空响应

### 现象
`deepseek-v4-flash` 在 `use_json=True` 时返回空字符串；去掉 `response_format` 重试仍为空。
同一提示下 `mimo` / `minimax` 正常。

### 根因分析（待确认）
1. 该模型/端点对 `response_format={"type":"json_object"}` 的兼容性存疑；
2. 或 prompt 里“请以 JSON 格式输出”与短 `max_tokens` 组合导致模型只输出空；
3. 现降级逻辑只重试一次且不改变 prompt，无法排除 prompt 因素。

### 修改方案
文件：`llm/deepseek_provider.py`

1. **降级重试带上 schema 提示**：fallback 时在 prompt 尾部追加“必须输出 JSON，从 `{` 开始”，并提升 `max_tokens` 下限（如 ≥ 512）。
2. **可配置关闭 JSON 模式**：给 `DeepSeekProvider` 增加 `use_json_output` 覆盖入口
   （构造函数已支持），并在 Provider 设置页暴露开关，默认对疑似不兼容模型关闭。
3. **失败可观测**：空响应时把 `finish_reason`、`usage`、是否降级写入 `log_llm_payload` 的 extra，便于定位。
4. **文档**：在 `docs/` 记录“DeepSeek 某些模型建议关闭 JSON 模式”。

### 回归
- 单元级：mock client 返回空 → 断言降级重试参数正确（含追加提示、提升 max_tokens）。
- 真实：同一 prompt 下 `use_json=True/False` 各跑一次，记录成功与耗时。

---

## 6. P2-6 RAG 未参与

### 现状
本机无 `sentence_transformers`，`[PostChapter] RAG event index failed`，
事件去重检索、相似度拦截全部跳过。

### 修改方案
1. **非阻塞降级已存在（保留）**，但要**显式提示**：
   - `GET /api/init/status` 的 `model_downloaded=false` 时，前端在项目页显示“RAG 未启用，已发生事件去重仅依赖文本摘要”。
2. **环境准备文档**：在 `AGENTS.md` / `README.md` 说明首次需下载 `moka-ai/m3e-base`，以及 `data/models/` 路径。
3. **复测清单**：装好模型后跑 10 章，验证
   - `event_dedup_matches` 非空；
   - 第 5/10 章的 5 章一致性检查能产出 `ConsistencyRecord`。

---

## 7. P2-7 后处理结果前端未接线

### 现状
`post_chapter` / `foreshadow_updater` 返回的 `arc_updates`、`relation_updates`、
`new_foreshadowings` 已写入数据库，但前端“角色弧光 / 伏笔”面板未展示最近变化。

### 修改方案
1. 后端：`GET /api/projects/{id}/chapters/{cid}/fingerprint` 已有；
   增加 `GET /api/projects/{id}/post-processing/latest`（按章返回 arc/relation/foreshadow 变更）。
2. 前端：`novel_editor` 生成完成后轮询该接口并在面板展示“本章状态变化”。
3. 需要同步 `web/index.html` 的 `?v=N`。

---

## 8. 实施顺序

1. **P1-3 / P1-4（字数控制）**：同一模块，合并一次改动 + 一次真实 5 章验证。
2. **P1-5（DeepSeek）**：独立小改，单元测试为主。
3. **P2-6**：文档 + 状态提示，环境就绪后复测。
4. **P2-7**：后端接口 → 前端展示，最后做一次端到端。

---

## 9. 验证策略

| 层级 | 内容 |
|---|---|
| 纯函数 | `_revise_outline` ctx、`adjust_word_count` 候选选择、DeepSeek 降级参数 |
| 冒烟 | `tests/test_system_smoke.py`（无需真实 LLM）确保无回归 |
| 真实小样本 | provider=mimo，目标 800 字，生成 5 章，统计命中率与最大偏差 |
| 真实全量 | 目标 2000 字，生成 10 章，检查字数、重复度、一致性记录 |

---

## 10. 附：本次测试产出的资产

- `tests/test_system_smoke.py`：系统级 API 冒烟（79 项，已通过）
- `tests/test_migrate_project_ids.py`：ID 迁移回归
- `docs/TEST_REPORT.md`：接口冒烟测试报告
- `docs/TEST_REPORT_NOVEL_FLOW.md`：真实 LLM 小说流程测试报告
- 临时产物：`/tmp/opencode/novel_10ch.txt`（10 章导出样例）

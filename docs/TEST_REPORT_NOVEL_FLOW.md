# CozyWriter 真实流程测试报告 · 小说项目

- 测试日期：2026-09-25 ~ 2026-09-26
- 被测分支：`fix/core-blockers`
- 运行环境：Linux (WSL2) + FastAPI `TestClient` + 独立临时 SQLite（`cozywriter_novel_flow.db`，不触碰 `data/cozywriter.db`）
- 真实 LLM：provider = `mimo`（`mimo-v2.5-pro`，兼容 Anthropic 协议）
- 结论：**问卷模式创建项目 + bootstrap 全部成功；批量生成 10/10 章全部成功并导出全文。**

---

## 1. 测试方式

1. 用问卷 API 写入完整答案后调用 `POST /api/questionnaires/{id}/build-project`，触发真实 bootstrap。
2. 等待 bootstrap workflow 落库（`run.status = committed`）。
3. 调用 `POST /api/chapters/batch-generate`，`start_chapter=0, count=10, provider=mimo`。
4. 等批次任务结束后统计每章字数，并调用 `POST /api/export/chapters` 导出全文 TXT。
5. RAG 未下载 `sentence_transformers` 模型，测试中 stub 了向量检索，只验证主流程。

---

## 2. 结果一：问卷模式创建小说项目

| 检查项 | 结果 |
|---|---|
| 问卷创建 | ✅ `POST /api/questionnaires` 200 |
| 创建项目 + 启动 bootstrap | ✅ `build-project` 200，返回 `project_id=96b890ed`, `run_id=1` |
| bootstrap 最终状态 | ✅ `committed` |
| 项目类型 / 标题 | ✅ `novel` / 《荒原问剑》 |
| 问卷状态 | ✅ `completed`，`created_project_id=96b890ed` |
| 落库主题数 | ✅ 1 |
| 落库角色数 | ✅ 5 |
| 落库世界观条目 | ✅ 5 |
| 章节细纲（chapter_outlines） | ✅ 10 章 |

结论：问卷 → 项目骨架 → bootstrap 设定生成 → 提交落库全链路正常，且问卷预创建的主角名（林墨白）与各设定字段均在落库结果中保留。

---

## 3. 结果二：批量生成 10 章

批次任务 `3801bb53`：`status=completed`，`progress=100`，10/10 章成功，总耗时约 **2390 秒（≈ 40 分钟）**。

| 章 | 标题 | 字数 |
|---|---|---|
| 1 | 风沙孤客 | 974 |
| 2 | 荒原残碑 | 628 |
| 3 | 残碑断忆 | 873 |
| 4 | 荒原问剑 | 642 |
| 5 | 月照双剑 | 782 |
| 6 | 同行异梦 | 784 |
| 7 | 河谷暗影 | 2640 |
| 8 | 遗迹残影 | 890 |
| 9 | 石台惊变 | 744 |
| 10 | 尘烟余烬 | 666 |
| | **合计** | **约 11,730 字** |

- 每章都完整跑完 9 步流水线（细纲 → 评审 → 正文 → 字数校验 → 评审 → 修订决策 → 保存 → 后处理 → 一致性/伏笔/事件签名）。
- 加权综合分稳定在 **80~93/100**，多数章节无需修订。
- 章节标题由 LLM 自动生成并写回（不再停留在“第 N 章”）。
- 全文导出成功：`/tmp/opencode/novel_10ch.txt`（35,094 字节，TXT 格式）。

---

## 4. 过程中发现的问题

### 4.1 细纲评审触发重写时丢失上下文（已定位，严重影响质量）

当细纲评审返回 `high` 级问题并触发重写时，`_revise_outline()` 只传了 6 个上下文键：
`chapter_position / pacing / key_content / plot_advance / prep_info / target_word_count`。

但 `chapter_outline_gen` role 模板需要 `previous_events`、`chapter_num`，导致：

- 日志报 `缺少必要的上下文键: previous_events / chapter_num`
- 重写请求变成「请生成第 （chapter_num 未提供） 章细纲」
- 模型看不到“已发生事件”，于是重写出的细纲与前面章节高度重复

运行日志中第 9、10 章都出现了这个情况：

- 第 9 章细纲评审判定“与第 7 章高度重复”→ 触发重写 → 重写时丢失上下文
- 第 10 章细纲被重写成“第 1 章《风沙孤客》的重复情节”

**影响**：章节重写分支存在内容重复/倒退风险，建议尽快修复（补全 `_revise_outline` 上下文并传入章节序号）。

### 4.2 一致性检查 role 在 post-processing 中被错误调用（已定位）

`run_post_chapter_processing` 调用一致性检查时只传了 `characters / world / foreshadowings`，缺少 `content`，导致：

- 日志报 `缺少必要的上下文键: 'content'`
- LLM 收到「待检查文本：（content 未提供）」
- 返回“无法审核”，一致性检查实质空转

### 4.3 WordAdjust 压缩不稳定

第 7、10 章正文超出目标字数较多，压缩器一次把内容从 1050 字压到 666 字（低于下限 720），两次尝试都停在同一结果，最终只能选最接近的候选。字数落点偏差可达 ±250 字。

### 4.4 RAG 未参与

本机未下载 `sentence_transformers` / embedding 模型，日志中多次出现：

```
[PostChapter] RAG event index failed: No module named 'sentence_transformers'
```

因此事件去重检索、RAG 相似度拦截在本轮测试中未生效，需要装好模型后再验证。

### 4.5 DeepSeek JSON 模式返回空

`deepseek-v4-flash` 在 `use_json=True` 时返回空响应并触发降级重试，降级后的纯文本请求也拿到空响应。同一提示下 `mimo` / `minimax` 正常。可能是该模型/端点的 JSON 输出约束问题，建议后续单独排查（本轮未阻塞流程，因为它不是默认模型）。

---

## 5. 结论与建议

- **主流程可用**：问卷模式建项目 + bootstrap + 连续生成 10 章 + 导出，全部跑通。
- **优先修复 4.1 / 4.2**：这两个问题是流水线内部上下文传参错误，会直接拉低章节质量，且目前只体现在日志里，用户不易察觉。
- **建议单独跟进 4.3 / 4.5**：字数压缩稳定性、DeepSeek JSON 空响应。
- **RAG 需在完整环境复测**：下载 `moka-ai/m3e-base` 后重跑一次，确认事件去重与一致性检查生效。

> 临时测试库与产物：`cozywriter_novel_flow.db`、`/tmp/opencode/novel_10ch.txt`；未写入真实 `data/cozywriter.db`。

# 150 章项目流程测试报告（opencode / deepseek-v4.1-flash）

- 测试日期：2026-09-28
- Provider：`opencode`（OpenCode Go）
- 模型：`deepseek-v4.1-flash`（推理模型）
- 端点：`https://opencode.ai/zen/go/v1`（OpenAI 兼容）
- 方式：独立临时 SQLite + FastAPI `TestClient`，不触碰 `data/cozywriter.db`
- 结论：**150 章一句话大纲完整生成（150/150，无缺号）；前 5 章正文全部生成且字数达标。**

---

## 1. 问卷模式创建 150 章项目

| 检查项 | 结果 |
|---|---|
| 问卷创建 + `build-project` | ✅ |
| bootstrap 最终状态 | ✅ `committed` |
| 项目目标章节数 | ✅ `150` |
| **chapter_outlines 总数** | ✅ **150** |
| **唯一章节号** | ✅ **150** |
| 章节号范围 | ✅ `1 ~ 150` |
| **缺号数量** | ✅ **0** |
| 分批续写 | ✅ 首批 100 章 + 续写 1 轮补 50 章 = 150/150 |

bootstrap 总耗时约 **487 秒**（含 100+50 两批大纲生成）。

---

## 2. 前 5 章正文生成

批次任务 `completed`，5/5 成功，耗时约 **2040 秒（34 分钟）**。

| 章 | 标题 | 字数（目标 2000，允许 1800~2200） |
|---|---|---|
| 1 | 黑砧补剑 | 2145 ✅ |
| 2 | 炭火听音 | 1887 ✅ |
| 3 | 街剑袖底的铜钱 | 2188 ✅ |
| 4 | 鞘底一针 | 1944 ✅ |
| 5 | 剑痕指北 | 1987 ✅ |
| | **合计** | **10,151 字** |

- **5/5 章全部落在目标字数区间内**（此前字数收敛不稳定的问题已修复生效）。
- 章节标题由 LLM 自动生成（非「第 N 章」）。
- 全文导出：`data/novel_150_5ch.txt`（35,714 字节）。

---

## 3. 本次修复验证

| 问题 | 修复 | 验证结果 |
|---|---|---|
| 续写返回 `chapter_number` 被当成「新增 0 章」，大纲停在 100/150 | `_normalize_chapter_outlines` 统一章节号字段 | ✅ 150/150 |
| bootstrap stage 未传 `use_json`，推理模型返回 reasoning 文本导致 JSON 解析失败、整个 run failed | 所有 JSON 调用显式 `use_json=True` | ✅ bootstrap `committed` |
| opencode JSON 模式 content 为空时用 reasoning 冒充 JSON | JSON 任务放大 `max_tokens` 重试，不回退 reasoning | ✅ 各 stage 正常返回 JSON |
| 推理模型 reasoning 占用 token 预算导致空响应 | JSON 任务 `max_tokens` 下限 8192 | ✅ |
| 字数压缩不稳定 | 量化目标 + 3 轮小幅修正 + 过冲候选淘汰 | ✅ 5/5 章命中区间 |
| batch/bootstrap 任务超时过短 | bootstrap 2h、batch 6h | ✅ 状态标记准确 |

---

## 4. 耗时参考（推理模型）

| 阶段 | 耗时 |
|---|---|
| bootstrap（含 150 章大纲） | ~487s |
| 单章正文（9 步流水线） | ~350–500s |
| 5 章合计 | ~2040s |

> `deepseek-v4.1-flash` 为推理模型，单次调用含较长 reasoning，整体速度显著慢于非推理模型。若追求吞吐，可考虑项目级选用非推理模型，或降低单章目标字数。

---

## 5. 遗留

- 日志中偶发 `usage_tracker ... database is locked` 警告（SQLite 并发写），不影响主流程，但 token 统计可能漏记。
- RAG 未启用（缺 embedding 模型），事件去重/相似度拦截未参与本轮。

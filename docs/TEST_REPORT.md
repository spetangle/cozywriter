# CozyWriter 系统功能测试报告

- 测试日期：2026-09-25
- 被测分支：`fix/core-blockers`（HEAD `473b7e8` 基础上新增冒烟测试）
- 测试方式：独立临时 SQLite + FastAPI `TestClient` + 现有独立测试脚本 + 前端模板装配检查
- 结论：**主链路全部通过**；测试过程中发现并修复 1 个真实接口缺陷。

---

## 1. 测试环境

| 项目 | 值 |
|---|---|
| OS | Ubuntu 24.04.4 LTS (WSL2, Linux 5.15 x86_64) |
| Python | 3.11.15（`/tmp/opencode/cozywriter-venv`，uv 创建） |
| Node.js | v22.22.2 |
| FastAPI | 0.141.1 |
| SQLAlchemy | 2.0.54 |
| Pydantic | 2.13.5 |
| ChromaDB | 1.5.9 |
| 数据库 | 临时 SQLite（`DATABASE_URL=sqlite:////tmp/...`），不碰 `data/cozywriter.db` |
| LLM | 未调用真实 provider；测试中使用 stub / 依赖缺失时走降级路径 |
| Embedding | 未下载 `moka-ai/m3e-base`；涉及 RAG 写接口的测试 stub 掉 `KnowledgeBase` |

---

## 2. 测试结果总览

| 测试项 | 覆盖内容 | 结果 |
|---|---|---|
| `tests/test_frontend_routes.py` | 前端 `/api` 调用 ↔ 后端路由一致性 | ✅ ALL PASS |
| `tests/test_script_bootstrap.py` | 剧本 planner / locked / commit / JSON 兜底 | ✅ ALL PASS |
| `tests/test_script_post_process.py` | 剧本后处理（外貌/弧光/道具） | ✅ ALL PASS |
| `tests/test_script_api.py` | 剧本 API：分镜 / 道具 / 角色外貌入口 | ✅ ALL PASS |
| `tests/test_migrate_project_ids.py` | int → hex 项目 ID 迁移（保留列 / 外键） | ✅ ALL PASS |
| `tests/test_system_smoke.py` | **系统级 API 冒烟（新增）** | ✅ **79 passed / 0 failed** |
| `node tests/test_spa_components.js` | SPA 模板占位符展开 / 组件装配 / 标签配平 | ✅ ALL PASS |
| 全量 `python -m py_compile` | 排除 `data/`、`.venv/` 的全部 Python 文件 | ✅ 通过 |
| 全量 `node --check` | `web/static/js/**.js` | ✅ 通过 |

---

## 3. 系统冒烟覆盖明细

`tests/test_system_smoke.py` 共 79 项断言，覆盖以下子链路：

### 3.1 初始化 / 配置 / 模型 / 题材
- `GET /api/init/status`
- `GET /api/config/status`
- `GET /api/models/status`
- `GET /api/providers`
- `GET /api/genres`、`POST /api/genres`、`DELETE /api/genres/{id}`

### 3.2 项目 CRUD
- 缺必填 → `missing_required`
- 创建小说项目 / 剧本项目
- 列表、详情、更新（含 `chapter_word_count` → `target_word_count` 换算）
- `bootstrap-status`
- 项目删除 + 删除后 404

### 3.3 小说设定资源
- 角色：创建 / 更新 / 列表 / 引用检查
- 世界观：创建 / 更新
- 主题：创建 / 列表 / 更新 / 删除
- 伏笔：创建 / 删除
- 剧情点：创建 / 列表 / 更新 / 删除

### 3.4 章节 / 大纲 / 导出
- 项目大纲：创建 / 更新
- 章节：创建 / 列表 / 详情 / 更新 / 版本列表 / `prep-info`
- 章节细纲：创建 / 读取
- 导出：TXT、Markdown、独立打包 ZIP（校验 `PK` 文件头）

### 3.5 灵感 / 问卷
- 灵感：创建 / 列表 / 标签 / 更新 / 删除
- 问卷：创建 / 列表 / 题目 / 分步题目 / `current-step` / `answer-step` / `prev-step` / 更新 / 删除
- 无 provider 时问卷生成选项自动降级，不报 5xx

### 3.6 剧本子系统
- 场景：创建 / 列表 / 更新 / 删除
- 分镜：创建 / 项目级列表 / 更新 / 删除 / 地点回填
- 道具：创建 / 流转历史 / 列表 / 删除

### 3.7 工作流 / Token / 任务
- `GET /api/workflow/project/{id}/latest`
- `GET /api/workflow/project/{id}/bootstrap-data`
- `GET /api/token-usage/project/{id}`、`/recent`
- `GET /api/tasks/all`

---

## 4. 测试中发现并修复的问题

### 4.1 `POST /api/projects/{id}/outline` 写入 Pydantic 对象导致 500

- 现象：请求体带 `plot_lines` 时，`outline_detail.py` 把 Pydantic `PlotLine` 对象直接塞进 SQLAlchemy JSON 列，序列化抛：
  `StatementError: Object of type PlotLine is not JSON serializable`
- 影响：项目大纲首次创建（POST）失败，前端“生成大纲后保存”链路会 500。
- 修复：新增 `_jsonable()`，在写入前把 Pydantic 模型 / 嵌套结构转换为普通 dict/list。
- 文件：`api/routes/outline_detail.py`

### 4.2 真实库孤儿外键记录已清理

- 测试前对 `data/cozywriter.db` 执行 `PRAGMA foreign_key_check`：229 条告警，全部来自 `character_relations`（80 行孤儿关系）。
- 已备份：`data/cozywriter_before_fk_cleanup_20260925_223153.db`
- 只删除违反外键的 80 行，保留合法关系；清理后 FK violations = 0，并执行 `VACUUM`。

---

## 5. 未覆盖 / 待人工验证

| 项目 | 原因 / 建议 |
|---|---|
| 真实 LLM 调用 | 未配置有效 provider；建议在目标环境配置 API Key 后跑一次真实 bootstrap / 单章生成 |
| Embedding 模型语义检索 | 未下载 `moka-ai/m3e-base`（~400MB）；测试 stub 了 RAG 写入 |
| 浏览器端到端 | 未启动真实浏览器操作 SPA；建议用 `run.sh` 启动后手动冒烟：建项目 → 引导补全 → 单章生成 → 评审 → 导出 → 建剧本 → 场景生成 → 分镜 |
| 并发 / 长任务 | 未压测多任务并发、任务取消、进程崩溃恢复 |
| Windows 侧 | 本报告在 Linux/WSL2 下执行；项目目标运行环境如为 Windows，需复跑 5 个 Python 测试脚本 |
| 旧库升级 | 已有迁移测试覆盖代表场景，真实旧库升级前仍建议先备份 `data/cozywriter.db` |

---

## 6. 复现命令

```bash
# 系统冒烟（新增）
.venv/bin/python tests/test_system_smoke.py

# 其余 Python 回归
.venv/bin/python tests/test_frontend_routes.py
.venv/bin/python tests/test_script_bootstrap.py
.venv/bin/python tests/test_script_post_process.py
.venv/bin/python tests/test_script_api.py
.venv/bin/python tests/test_migrate_project_ids.py

# 前端
node tests/test_spa_components.js
```

Windows 将 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

---

## 7. 结论

- 核心 API 主链路（项目、章节、大纲、导出、角色、世界观、主题、伏笔、剧情点、灵感、问卷、剧本、任务、Token 用量）在临时库环境下全部通过。
- 新增的系统冒烟测试可长期作为回归入口，本次已捕获并修复项目大纲 POST 的真实 500 缺陷。
- 生产使用前建议补一次真实 provider + Embedding 模型的端到端人工冒烟。

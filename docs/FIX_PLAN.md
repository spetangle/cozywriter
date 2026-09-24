# CozyWriter 修复计划

> 状态：执行中
> 制定时间：2026-09-24
> 依据：项目评估报告（已逐条读码核实）

## Phase 0 · 安全网与仓库整理

- [x] 0.1 建工作分支 `fix/core-blockers`
- [x] 0.2 新增 `.gitattributes` 统一行尾，`git add --renormalize` 单独提交
- [x] 0.3 按模块拆分提交现有 2 个月成果

## Phase 1 · 5 个 Blocker（恢复主流程）

- [x] 1.1 B1 异步任务丢 `project_id`：`generate.py` / `review.py` / `full_review.py` 改用 `_project_id=`
- [x] 1.2 B2 Bootstrap 写入 project 0：`projects.py` create 路径补 `_project_id`（含 `inspirations.py`）
- [x] 1.3 B3 问卷 AI 补全返回 None：`creative_questionnaire.py` 修正 `return` 缩进 + `or {}` 兜底
- [x] 1.4 B4 全文评审读 `Theme.name`：`full_review.py` 改 `t.title`
- [x] 1.5 B5 Step9 后处理崩溃：`chapter_pipeline.py` 循环后 `post_data or {}` + 类型校验

## Phase 2 · 前端拦截级问题

- [x] 2.1 B7 单章生成 422：`novel_editor.js` body 补 `project_id`
- [x] 2.2 B8 导出 404：前端接 `POST /api/export/chapters` + blob 下载（含格式/重新分章/独立打包）
- [x] 2.3 B9 大纲路由冲突：`OutlineNode` 迁到 `/outline-nodes`
- [~] 2.4 前端字段错位：已修模型选择器、场景保存、问卷保存、项目章节字数、plot 字段
  - 待办（依赖 Phase 3/4）：剧本「AI 生成」prompt/mode 后端未读取；fingerprint 未解包；版本表 word_count 字段；评审/一致性前端尚未接线

## Phase 3 · 剧本子系统补全

- [x] 3.1 `plan_bootstrap_stages` 传 `project_type`（projects.py ×2、creative_questionnaire.py、inspirations.py）
  - 附带修复：`script_stage_3d_arcs` / `script_stage_4a_outline` / `script_stage_4b_foreshadow` 补 `needs_llm=True`；`run_bootstrap_sync` 计算总状态时排除 `_meta`，否则正常 run 永远 `partial`
- [x] 3.2 `commit_bootstrap` 增加 Screenplay 落库分支
  - 新增 `_commit_script_bootstrap`：Theme / WorldEntry / Character(含 appearance) / CharacterRelation / CharacterArc / ProjectOutline / Screenplay / Foreshadowing；统一事务，重复 commit 幂等；自动 commit / rerun-and-commit 检查 commit 结果
- [x] 3.3 `script_pipeline` JSON 兜底 / 修订 role / 弧光读取 / 分镜去重
  - 新增 `script_outline_revision` role；修复 ProjectOutline/Foreshadowing 字段；分镜先删后写并按镜号规范化
- [x] 3.4 剧本 rerun 的 `locked` 按 `project_type` 构造
  - 抽出 `_build_bootstrap_locked`；两个 rerun 入口共用；`_rebuild_user_input_from_project` 支持剧本；rerun 前校验 stage 属于本 run；prev_outputs 收集全部前置 stage
  - 附带：`bootstrap-data` 增加剧本视图；`ProjectCreate` 支持剧本 `total_scenes`、剧本不再强制 `chapter_word_count`

## Phase 4 · 稳定性与数据安全

- [x] 4.1 Step4 补 `max_tokens`（长章截断）：主流程与独立函数一致使用 `calculate_max_tokens`
- [x] 4.2 Step8 空文本保护（避免覆盖正文）：空文本抛错不提交；失败/取消先 rollback；后处理空正文直接返回；修订分支字段与位置参数修正
- [~] 4.3 迁移缺口：`init_db` 集成通用迁移；`migrate.py` DateTime/CURRENT_TIMESTAMP 与 NOT NULL 处理已修
  - 待办：`migrate_project_ids.py` 仍硬编码旧 schema（缺 project_type/script_format/script_episode_count、漏 full_review_sessions），重建表仍可能丢外键/唯一约束/索引
- [x] 4.4 开启 `PRAGMA foreign_keys=ON`（每个 SQLite 连接注册 connect 事件；bootstrap 删除角色前显式清关系/弧光）
- [~] 4.5 Bootstrap 失败不误删角色；`user_filled` 透传下游
  - 已修：拒绝 failed run commit；按 stage 状态条件清理；prev_outputs 包含 user_filled；灵感建项目走自动 commit；移除中间 commit
  - 待办：`protagonist_name` 等问卷预创建字段仍未进入 stage 输出契约
- [~] 4.6 Provider 一致性：Anthropic temperature/top_p + base_url、OpenAI base_url、DeepSeek 余额查询默认关、init/main/超参补 deepseek
  - 待办：MiniMax/MiMo 专用异常分支仍未记录失败用量
- [x] 4.7 `chapters.py` 修正无效 import，并优先读 `ProjectOutline.chapter_outlines` / `stage_4a_chapter_outlines`，兼容旧 `stage_4a_outline`

## Phase 5 · 工程与文档

- [ ] 5.1 `AGENTS.md` 增补已知坏损链路
- [ ] 5.2 `README.md` / `ARCHITECTURE.md` 标注或更新
- [ ] 5.3 Windows 侧跑通 3 个 Python 测试脚本
- [ ] 5.4 清理死代码

## 验证策略

1. 本机：`python3 -m py_compile`（全量）+ `node --check`（全量）
2. 本机：`node tests/test_spa_components.js`
3. Windows：`tests/test_frontend_routes.py`、`test_script_api.py`、`test_script_post_process.py`、`test_script_bootstrap.py`
4. 手动冒烟：建项目 → 引导补全落库 → 单章生成 → 评审 → 导出 → 建剧本 → 场景生成 → 分镜

## 决策记录

1. 导出：✅ 已按推荐前端接 `POST /api/export/chapters`（保留重新分章 / 打包）
2. 大纲路由：✅ 已按推荐把 `OutlineNode` 迁到 `/outline-nodes`
3. 行尾规范化：✅ Phase 0 全库执行
4. 旧库处理：⏳ 待定（Phase 4 需要：写数据修复脚本 vs 允许重置数据库）

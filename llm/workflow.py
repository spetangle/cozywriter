"""
项目引导补全 Workflow

当用户创建项目时，4 必填已锁，8 选填可空。
LLM 补全分多个 stage，按依赖关系调度：
  Stage 1    基础外推（必跑）
  Stage 2A/B/C  创意外延（3 子 stage 并行，按需跳过）
  Stage 3A/B/C/D  角色体系
  Stage 4A/B  大纲 + 伏笔
  Stage 5    汇总入库（事务写入 + RAG 索引）

每个 stage 一次 LLM 调用，JSON 输出，失败可重跑。
"""
import json
import re
import time
from typing import Any

from logger import logger
from llm.factory import LLMFactory
from llm.roles import build_bootstrap_role


# ═══════════════════════════════════════════════════════════════
# Stage DAG 定义
# ═══════════════════════════════════════════════════════════════

STAGE_DEFS = {
    "stage_1_base": {
        "name": "基础外推",
        "description": "从 4 必填推导总章数 / AI 味强度 / 估算总字数",
        "needs_llm": True,
        "depends_on": [],
        "outputs": ["total_chapters", "est_total_words", "ai_removal"],
        "max_tokens": 1024,
        "temperature": 0.3,
    },
    "stage_2a_theme": {
        "name": "核心主旨 + 基调",
        "description": "生成核心主题与基调",
        "needs_llm_if_missing": ["theme", "tone"],
        "depends_on": ["stage_1_base"],
        "outputs": ["theme", "tone"],
        "max_tokens": 1024,
        "temperature": 0.5,
    },
    "stage_2b_style": {
        "name": "文风 + 节奏",
        "description": "生成文风与节奏偏好",
        "needs_llm_if_missing": ["style", "pacing"],
        "depends_on": ["stage_1_base"],
        "outputs": ["style", "pacing"],
        "max_tokens": 1024,
        "temperature": 0.5,
    },
    "stage_2c_world": {
        "name": "世界观骨架",
        "description": "生成世界观条目（按 category 分类）",
        "needs_llm_if_missing": ["premise"],
        "depends_on": ["stage_1_base"],
        "outputs": ["premise"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
    "stage_3a_protagonist": {
        "name": "主角细化",
        "description": "主角设定（Character + profile）",
        "needs_llm_if_missing": ["protagonist"],
        "depends_on": ["stage_2a_theme", "stage_2b_style", "stage_2c_world"],
        "outputs": ["protagonist"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3b_antagonist": {
        "name": "反派细化",
        "description": "反派设定",
        "needs_llm_if_missing": ["antagonist"],
        "depends_on": ["stage_2a_theme", "stage_2b_style", "stage_2c_world"],
        "outputs": ["antagonist"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3c_supporting": {
        "name": "配角 + 关系矩阵",
        "description": "配角角色 + CharacterRelation[]",
        "needs_llm_if_missing": ["supporting"],
        "depends_on": ["stage_3a_protagonist", "stage_3b_antagonist"],
        "outputs": ["supporting"],
        "max_tokens": 2048,
        "temperature": 0.6,
    },
    "stage_3d_arcs": {
        "name": "角色弧光设计",
        "description": "所有角色的弧光（CharacterArc[]）",
        "needs_llm": True,
        "depends_on": ["stage_3a_protagonist", "stage_3b_antagonist", "stage_3c_supporting"],
        "outputs": ["arcs"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
    "stage_4a_outline": {
        "name": "项目大纲",
        "description": "volumes + plot_lines + structure + outline_text + pacing_notes + reversal_schedule + climax_map",
        "needs_llm": True,
        "depends_on": ["stage_3d_arcs"],
        "outputs": ["outline"],
        # 拆成 2 次调用后,这次只生成架构层(约 5K 输出),8192 够用
        "max_tokens": 8192,
        "temperature": 0.6,
    },
    "stage_4a_chapter_outlines": {
        # 拆分出来的"每章一句话"子阶段(原 stage_4a_outline 拆出来)
        # 单独 max_tokens 16384,保证 100 章小说能完整输出(每章 1 句 = ~200 chars)
        "name": "章节一句话大纲",
        "description": "chapter_outlines[1..N] 每章 1 句话（不依赖架构阶段也能手动重跑）",
        "needs_llm": True,
        "depends_on": ["stage_4a_outline"],
        "outputs": ["chapter_outlines"],
        "max_tokens": 16384,
        "temperature": 0.6,
    },
    "stage_4b_foreshadow": {
        "name": "伏笔规划",
        "description": "Foreshadowing[]（短/中/长周期）",
        "needs_llm": True,
        "depends_on": ["stage_4a_outline"],
        "outputs": ["foreshadowings"],
        "max_tokens": 2048,
        "temperature": 0.5,
    },
}


# ═══════════════════════════════════════════════════════════════
# Stage prompt 构造
# ═══════════════════════════════════════════════════════════════

STAGE_PROMPTS = {
    "stage_1_base": {
        "task": (
            "根据用户提供的必填信息，推导项目基础参数。\n"
            "要求：\n"
            "1. 如果用户已在【硬约束】中指定了 total_chapters（预计总章节数），**必须原样采用**，不得修改；"
            "否则根据【题材】+【创意信息】估算合适的总章节数（玄幻 30~50，都市 25~35，科幻 25~40，"
            "武侠/仙侠 30~50，历史 25~40，悬疑 20~30，现实主义 15~25，奇幻 30~50）\n"
            "2. 根据【章节字数】估算总字数 = total_chapters * chapter_word_count * 1000\n"
            "3. 推荐去 AI 味强度（1-10，默认 7；冷峻/平实风格偏高 8-9，优美/诗意偏低 5-6）\n"
            "4. 推荐 ai_removal 数值（1-10）\n"
        ),
        "json_schema": {
            "total_chapters": 30,
            "est_total_words": 90000,
            "ai_removal": 7,
            "rationale": "推导理由（1-2 句话）",
        },
    },
    "stage_2a_theme": {
        "task": (
            "根据用户的题材和一句话故事，生成：\n"
            "1. theme：核心主题（一句话，15 字内）\n"
            "2. tone：基调（必须从 热血/治愈/黑暗/轻松/史诗/悬疑紧张/浪漫/幽默/冷峻 中选一个）\n"
        ),
        "json_schema": {"theme": "...", "tone": "..."},
    },
    "stage_2b_style": {
        "task": (
            "根据题材和基调推荐：\n"
            "1. style：文风（必须从 优美/平实/诗意/幽默/冷峻 中选一个）\n"
            "2. pacing：节奏（必须从 快节奏/中等节奏/慢热型/起伏型 中选一个）\n"
        ),
        "json_schema": {"style": "...", "pacing": "..."},
    },
    "stage_2c_world": {
        "task": (
            "根据题材构建世界观骨架，输出 4-6 个分类条目。\n"
            "category 必须是以下之一：地理 / 历史 / 势力 / 规则 / 社会 / 技术\n"
            "tags 为该条目的标签数组（2-4 个关键词）。\n"
        ),
        "json_schema": {
            "world_entries": [
                {"category": "地理", "title": "...", "content": "...", "tags": ["..."]},
                {"category": "历史", "title": "...", "content": "...", "tags": ["..."]},
            ]
        },
    },
    "stage_3a_protagonist": {
        "task": (
            "根据题材 + 主旨 + 世界观，设计主角。\n"
            "要求：\n"
            "1. name：角色名（2-3 个汉字）\n"
            "2. role：固定为 '主角'\n"
            "3. profile 字段：age（数字）, gender（男/女/其他）, identity（身份 1 句）,"
            "personality（性格 2-3 个关键词）, goal（核心目标 1 句）, weakness（弱点 1 句）,"
            "ability（能力/资源 1 句）, catchphrase（口头禅 1 句，可空）, background（背景 1-2 句）\n"
            "4. description：补充描述（3-5 句）\n"
        ),
        "json_schema": {
            "name": "...",
            "role": "主角",
            "profile": {
                "age": 18,
                "gender": "男",
                "identity": "...",
                "personality": "...",
                "goal": "...",
                "weakness": "...",
                "ability": "...",
                "catchphrase": "...",
                "background": "...",
            },
            "description": "...",
        },
    },
    "stage_3b_antagonist": {
        "task": (
            "根据题材 + 主旨 + 世界观 + 主角设定，设计反派。\n"
            "要求：\n"
            "1. name：角色名（2-3 个汉字）\n"
            "2. role：固定为 '反派'\n"
            "3. profile 字段：与主角一致\n"
            "4. description：补充描述（3-5 句，包含与主角的核心矛盾）\n"
        ),
        "json_schema": {
            "name": "...",
            "role": "反派",
            "profile": {
                "age": 0,
                "gender": "...",
                "identity": "...",
                "personality": "...",
                "goal": "...",
                "weakness": "...",
                "ability": "...",
                "catchphrase": "...",
                "background": "...",
            },
            "description": "...",
        },
    },
    "stage_3c_supporting": {
        "task": (
            "根据主角与反派设定，设计 2-4 名重要配角，并建立 3-5 条关系。\n"
            "配角 role 必须是 '配角'。\n"
            "关系字段：\n"
            "  from / to：角色名（必须在主角/反派/本步骤配角中）\n"
            "  type：关系类型（友情/爱情/亲情/师徒/敌对/竞争/合作/...）\n"
            "  description：关系描述（1 句）\n"
            "  strength：1-10 的强度\n"
            "  status：stable / developing / tense / broken\n"
        ),
        "json_schema": {
            "supporting": [
                {
                    "name": "...",
                    "role": "配角",
                    "profile": {
                        "identity": "...",
                        "personality": "...",
                        "relationship_to_protagonist": "...",
                    },
                    "description": "...",
                }
            ],
            "relations": [
                {
                    "from": "主角名",
                    "to": "配角名",
                    "type": "...",
                    "description": "...",
                    "strength": 5,
                    "status": "stable",
                }
            ],
        },
    },
    "stage_3d_arcs": {
        "task": (
            "为所有已确认角色设计弧光。\n"
            "arc_type 必须是：成长 / 堕落 / 平线 / 循环\n"
            "要求：\n"
            "1. 每个角色一条弧光\n"
            "2. start_state：起点状态（1 句）\n"
            "3. end_state：终点状态（1 句）\n"
            "4. key_behavior：体现弧光的关键行为（1 句）\n"
            "5. is_stable：是否稳定（默认 true）\n"
        ),
        "json_schema": {
            "arcs": [
                {
                    "character_name": "...",
                    "arc_type": "成长",
                    "start_state": "...",
                    "end_state": "...",
                    "key_behavior": "...",
                    "is_stable": True,
                }
            ]
        },
    },
    "stage_4a_outline": {
        "task": (
            "根据所有已确定的角色与世界设定，设计完整的项目大纲（架构层）。\n"
            "【重要】总章节数已在硬约束或上一阶段产物中确定（total_chapters），大纲必须严格覆盖该章数范围，不得自行增减。\n"
            "\n"
            "═══════════════════════════════════════════════════════════════\n"
            "【分卷结构 - 必须首先输出】\n"
            "═══════════════════════════════════════════════════════════════\n"
            "整本书按【卷（Volume）】组织，每一卷是一个相对完整的剧情阶段：\n"
            "1. volumes：数组，推荐 3-5 卷（短篇 20 章可 2-3 卷，长篇 100 章可 4-6 卷）\n"
            "   每个卷包含：\n"
            "   - volume_num：卷号（1, 2, 3...）\n"
            "   - title：卷名（4-10 字，如「异能觉醒」「暗流涌动」「外星入侵」）\n"
            "   - from_chapter / to_chapter：该卷覆盖的章节范围（必须连续且不重叠）\n"
            "   - summary：该卷核心主线概述（2-3 句话，只讲本卷大事件）\n"
            "   - core_event：本卷最核心的 1 个剧情事件（1 句话，如「主角觉醒异能」「与反派首次正面交锋」）\n"
            "   所有卷合计覆盖 1 ~ total_chapters，不得有缺漏。\n"
            "\n"
            "═══════════════════════════════════════════════════════════════\n"
            "【剧情线 + 节奏】\n"
            "═══════════════════════════════════════════════════════════════\n"
            "1. plot_lines：3-5 条剧情线，每条包含 title, description, from_chapter, to_chapter, priority\n"
            "2. structure.acts：4 幕结构（开局/发展/高潮/结局），每幕给 from_chapter / to_chapter，所有幕合计必须覆盖 1 ~ total_chapters\n"
            "3. pacing_notes：整体节奏规划（2-3 句）\n"
            "4. outline_text：完整大纲文本（200-500 字概述）\n"
            "\n"
            "═══════════════════════════════════════════════════════════════\n"
            "【宏观节奏规划】\n"
            "═══════════════════════════════════════════════════════════════\n"
            "5. reversal_schedule：反转/高潮时刻表，严格遵循以下节奏：\n"
            "   - small_reversals：小反转/小爽点（约每 3 章）：压力积累 + 爆发式爽点循环\n"
            "     例：反派挑衅 → 资源争夺 → 绝地反击 → 获得奖励\n"
            "   - big_reversals：大反转/大爽点（约每 10 章）：重大剧情转折或身份揭晓\n"
            "     例：身世揭秘、阵营反转、核心秘密揭露\n"
            "   每条都要给 chapter 字段(章号) + description 字段(简述)\n"
            "   整个 total_chapters 的小爽点要均匀分布\n"
            "6. climax_map：每个幕的高潮点安排，确保读者追更动力\n"
            "   每条都要给 act(幕名) + climax_chapter(高潮章号) + description(描述)\n"
            "\n"
            "【必填字段清单 - 全部 6 个字段都必须出现,缺一个视为失败】\n"
            "  1. volumes  2. plot_lines  3. structure.acts  4. pacing_notes\n"
            "  5. reversal_schedule  6. climax_map\n"
            "\n"
            "【本阶段不输出】chapter_outlines（每章 1 句话）—\n"
            "        那是下一阶段 stage_4a_chapter_outlines 的事。\n"
            "        本阶段只输出整体架构(分卷/剧情线/四幕/节奏规划/反转/高潮)。\n"
        ),
        "json_schema": {
            "volumes": [
                {
                    "volume_num": 1,
                    "title": "卷名（4-10 字）",
                    "from_chapter": 1,
                    "to_chapter": 25,
                    "summary": "本卷主线概述（2-3 句话）",
                    "core_event": "本卷最核心事件（1 句话）",
                }
            ],
            "plot_lines": [
                {
                    "title": "...",
                    "description": "...",
                    "from_chapter": 1,
                    "to_chapter": 10,
                    "priority": 1,
                }
            ],
            "structure": {
                "acts": [
                    {"name": "第一幕", "from_chapter": 1, "to_chapter": 8},
                    {"name": "第二幕", "from_chapter": 9, "to_chapter": 18},
                    {"name": "第三幕", "from_chapter": 19, "to_chapter": 25},
                    {"name": "第四幕", "from_chapter": 26, "to_chapter": 30},
                ]
            },
            "pacing_notes": "...",
            "outline_text": "...",
            "reversal_schedule": {
                "small_reversals": [
                    {"chapter": 3, "description": "小爽点描述"},
                    {"chapter": 6, "description": "小爽点描述"},
                ],
                "big_reversals": [
                    {"chapter": 10, "description": "大反转描述"},
                    {"chapter": 20, "description": "大反转描述"},
                ],
            },
            "climax_map": [
                {"act": "第一幕", "climax_chapter": 7, "description": "幕高潮描述"},
                {"act": "第二幕", "climax_chapter": 17, "description": "幕高潮描述"},
            ],
        },
    },
    "stage_4a_chapter_outlines": {
        # 拆分出来的"每章一句话"子阶段
        # 输入：上一阶段 stage_4a_outline 的架构（分卷/剧情线/四幕/reversal_schedule）
        # 输出：chapter_outlines[1..total_chapters]，每章 1 句话
        # 单独拆出来避免单次 LLM 输出过长被截断
        "task": (
            "根据项目大纲的架构层（上一阶段已生成），为每一章写 1 句话核心事件大纲。\n"
            "【输入】上一阶段架构（分卷/剧情线/四幕/反转/高潮），会通过 prev_outputs 传入。\n"
            "【输出】chapter_outlines 数组（每章 1 条）\n"
            "\n"
            "═══════════════════════════════════════════════════════════════\n"
            "【每章节细纲 - 严格 1 章 1 句，必须覆盖 1~total_chapters 全部章节】\n"
            "═══════════════════════════════════════════════════════════════\n"
            "chapter_outlines：数组，每个元素对应一章，**禁止 1-N 章共用同一段描述**！\n"
            "\n"
            "【硬性约束 - 必须严格遵守】\n"
            "   ⚠️ 绝对禁止把多章合并成一段情节描述。\n"
            "   ⚠️ 每一章必须有自己独立的核心事件；相邻章可以有关联但不能是同一件事。\n"
            "   ⚠️ 数组长度必须 === total_chapters（少 1 章或多 1 章都会失败）。\n"
            "\n"
            "   每一章包含：\n"
            "   - chapter_num：1..total_chapters（**严格按顺序连续**，不能漏）\n"
            "   - volume_num：本章所属的卷号（1, 2, 3...，参考 stage_4a_outline 输出的 volumes）\n"
            "   - title：本章标题（4-15 字，与内容有关联，不要「第 N 章」这种纯序号，例如「初入诡秘都市」「玄机子的阴谋」）\n"
            "   - chapter_position：本章定位（开局/发展/高潮/回落/结局）\n"
            "   - pacing：节奏（铺垫/推进/高潮/回落/平稳）\n"
            "   - key_content：核心内容（**严格 1 句话，1-2 句**。\n"
            "       格式：第N章大纲：主角XXX做了什么事情，见到了什么人或物。\n"
            "       强制 ≤ 40 字。必须只描述本章发生的 1 个核心事件。\n"
            "       禁止出现「并」「以及」「同时」「还」「+」连接的两件事。\n"
            "       错误示范：「余凌找到林战试探其旧伤，并收到神秘短信」（这是 2 件事）\n"
            "       正确示范：「余凌在健身房试探林战的旧伤反应」\n"
            "       正确示范2：「余凌收到神秘短信警告地脉异常」\n"
            "       → 同一关键事件（'试探林战旧伤'/'收到短信'）必须拆分到不同章）\n"
            "   - plot_advance：剧情如何推进主线（1 句话，不超过 30 字）\n"
            "   - highlights：本章看点/爽点数组（1-3 条）\n"
            "   - target_word_count：目标字数（默认 3000）\n"
            "\n"
            "【防剧情重复硬规则 - 减少后续章节生成时撞车】\n"
            "   生成每一章 key_content 时，请先在脑里建一张「事件表」：\n"
            "     - 同一人物的关键事件（觉醒/加入团队/收到警告/死亡/离开/重逢/战斗/决裂 等）\n"
            "       只能出现 1 次，分别落到不同章\n"
            "     - 同一场景（健身房/茶馆/拍卖会/办公室 等）只用来承载 1 个核心事件，\n"
            "       不要在不同章让同一场景重复出现\n"
            "     - 同一物品/线索/谜题（如「神秘玉佩」「旧伤」「加密文件」）的揭示/获取/使用，\n"
            "       必须分布在不同章\n"
            "\n"
            "【去重自检 - 生成完毕后请逐章检查】\n"
            "   1. 相邻两章的 key_content 不能描述同一件事\n"
            "   2. 同一人物的关键事件只能出现在 1 章中\n"
            "   3. 任意两章的 key_content 文字重合度不能超过 40%\n"
            "   4. 同一场景/物品/线索 不能在多章重复出现\n"
            "   如有违反，必须改写其中一章。\n"
        ),
        "json_schema": {
            "chapter_outlines": [
                {
                    "chapter_num": 1,
                    "volume_num": 1,
                    "title": "本章标题（4-15 字，非纯序号）",
                    "chapter_position": "开局",
                    "pacing": "铺垫",
                    "key_content": "本章核心事件的 1 句话描述（≤40 字，只 1 件事）",
                    "plot_advance": "主线如何推进（1 句话 ≤30 字）",
                    "highlights": ["看点1", "看点2"],
                    "target_word_count": 3000,
                }
            ],
        },
    },
    "stage_4b_foreshadow": {
        "task": (
            "根据项目大纲，规划伏笔系统。伏笔必须分三个层级，确保与主线紧密相关：\n"
            "\n"
            "【伏笔三层级体系】\n"
            "1. 短伏笔（约 6000 字内 / 3 章以内回收）：\n"
            "   - 短期内抛出并迅速解决\n"
            "   - 例：主角进副本前得罪了某人，在副本内立刻遇到并打脸\n"
            "   - 作用：维持近期的阅读期待\n"
            "   - 数量：3-5 条\n"
            "\n"
            "2. 中伏笔（约 5 万字 / 跨越一个完整副本或较大剧情篇章）：\n"
            "   - 开篇埋下线索，在篇章结尾进行回收，形成阶段性闭环\n"
            "   - 例：副本入口的神秘符号 → 副本最终 boss 的弱点\n"
            "   - 作用：维持中期追更动力\n"
            "   - 数量：2-3 条\n"
            "\n"
            "3. 长伏笔（贯穿全书）：\n"
            "   - 从小说第一章埋下，直到大结局才揭晓\n"
            "   - 涉及世界观的核心秘密或主角的最终宿命\n"
            "   - 作用：整本书的灵魂\n"
            "   - 数量：1-2 条\n"
            "\n"
            "要求：\n"
            "1. suggested_plant_chapter：建议埋设章节号\n"
            "2. suggested_resolve_chapter：建议回收章节号（长伏笔写 'final'）\n"
            "3. importance：high / medium / low（长伏笔必须 high）\n"
        ),
        "json_schema": {
            "foreshadowings": [
                {
                    "title": "...",
                    "content": "...",
                    "type": "短伏笔|中伏笔|长伏笔",
                    "suggested_plant_chapter": 1,
                    "suggested_resolve_chapter": 5,
                    "importance": "high|medium|low",
                    "connection_to_mainline": "与主线的关联说明",
                }
            ]
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# 规划：根据用户已填字段动态裁剪 stage
# ═══════════════════════════════════════════════════════════════

def plan_bootstrap_stages(required: dict, user_filled: dict) -> list[dict]:
    """
    根据 4 必填 + 用户已填选填，裁剪 stage 计划

    Returns:
        [
            {"id": "stage_1_base", "name": "...", "needs_llm": True, ...},
            ...
        ]
    """
    stages = []
    for stage_id, defn in STAGE_DEFS.items():
        if "needs_llm_if_missing" in defn:
            # 任一目标字段未填则需要 LLM
            needs = any(
                not user_filled.get(f) for f in defn["needs_llm_if_missing"]
            )
        else:
            needs = defn.get("needs_llm", False)

        stages.append({
            "id": stage_id,
            "name": defn["name"],
            "description": defn["description"],
            "needs_llm": needs,
            "depends_on": defn["depends_on"],
            "outputs": defn["outputs"],
            "status": "pending",
        })
    return stages


# ═══════════════════════════════════════════════════════════════
# 同步执行 Workflow
# ═══════════════════════════════════════════════════════════════

def run_bootstrap_sync(run_id: int, user_input: dict, db=None) -> dict:
    """
    同步执行 bootstrap workflow（在线程池中调用）

    Args:
        run_id: WorkflowRun.id
        user_input: 用户完整输入（4 必填 + 8 选填）
        db: 可选外部 Session

    Returns:
        {"status": "completed" | "failed", "stage_results": {...}, "error": "..."}
    """
    from storage.models.workflow import WorkflowRun
    from storage.database import SessionLocal

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return {"status": "failed", "error": f"Run {run_id} not found"}

        # 持久化 user_input 到 stage_results._meta（供后续 rerun_stage 读取）
        stage_results = dict(run.stage_results or {})
        stage_results["_meta"] = {
            "user_input": {k: v for k, v in user_input.items() if k != "_project_id"},
            "ts": time.time(),
        }

        # 提权 4 必填为 locked
        locked = {
            "title": user_input.get("title", ""),
            "chapter_word_count": user_input.get("chapter_word_count", 0),
            "genre": user_input.get("genre", ""),
            "description": user_input.get("description", ""),
        }

        # 如果用户指定了预计总章节数（> 0），也作为硬约束传入 LLM
        user_total_chapters = user_input.get("total_chapters", 0)
        if user_total_chapters and int(user_total_chapters) > 0:
            locked["total_chapters"] = int(user_total_chapters)

        # 用户已填的选填
        user_filled = {
            k: v for k, v in user_input.items()
            if k not in locked and v
        }

        llm_logs = list(run.llm_logs or [])

        run.status = "running"
        run.current_stage_index = 0
        db.commit()

        # 拓扑排序执行
        stages = run.stages or []
        completed_set = set()

        for stage in stages:
            stage_id = stage["id"]

            # 依赖未满足则跳过
            deps_ok = all(
                stage_results.get(d, {}).get("status") in ("ok", "skipped", "user_filled")
                for d in stage["depends_on"]
            )
            if not deps_ok:
                stage_results[stage_id] = {
                    "status": "failed",
                    "error": f"Dependency not satisfied: {stage['depends_on']}",
                    "started_at": time.time(),  # 占位，前端能稳定算"已耗时"
                    "completed_at": time.time(),
                }
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "skipped_dep",
                })
                continue

            if not stage["needs_llm"]:
                # 用户已填对应字段 → 标记为 user_filled
                stage_results[stage_id] = {
                    "status": "user_filled",
                    "user_values": {k: user_filled.get(k) for k in stage["outputs"] if k in user_filled},
                }
                completed_set.add(stage_id)
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "user_filled",
                })
                continue

            # 执行 LLM 调用
            logger.info(f"[Bootstrap] running stage {stage_id} ...")
            # 立即把 stage 标为 running，commit，让前端轮询能看到
            stage_results[stage_id] = {
                "status": "running",
                "started_at": time.time(),
            }
            run.stage_results = stage_results
            run.current_stage_index = sum(
                1 for r in stage_results.values()
                if r.get("status") in ("ok", "user_filled", "skipped")
            )
            db.commit()
            try:
                # 收集已完成的 stage 产物
                prev_outputs = {
                    sid: stage_results[sid].get("data", {})
                    for sid in completed_set
                    if sid in stage_results and "data" in stage_results[sid]
                }

                result = _run_single_stage(
                    stage_id=stage_id,
                    locked=locked,
                    user_filled=user_filled,
                    prev_outputs=prev_outputs,
                    db=db,
                )

                stage_results[stage_id] = {
                    "status": "ok",
                    "data": result,
                    "completed_at": time.time(),
                }
                completed_set.add(stage_id)
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "ok",
                })
                run.current_stage_index += 1
                db.commit()

            except Exception as e:
                logger.error(f"[Bootstrap] stage {stage_id} failed: {e}")
                # 保留之前的 started_at（如果有），避免覆盖已记录的起始时间
                prev = stage_results.get(stage_id) or {}
                stage_results[stage_id] = {
                    "status": "failed",
                    "error": str(e),
                    "started_at": prev.get("started_at") or time.time(),
                    "completed_at": time.time(),  # 让前端停止计时
                }
                llm_logs.append({
                    "stage": stage_id,
                    "ts": time.time(),
                    "status": "failed",
                    "error": str(e),
                })

        # 计算总状态
        has_failure = any(
            r.get("status") == "failed" for r in stage_results.values()
        )
        all_done = all(
            r.get("status") in ("ok", "user_filled", "skipped")
            for r in stage_results.values()
        )

        if has_failure:
            run.status = "failed"
        elif all_done:
            run.status = "completed"
        else:
            run.status = "partial"

        run.stage_results = stage_results
        run.llm_logs = llm_logs
        db.commit()

        return {
            "status": run.status,
            "stage_results": stage_results,
            "llm_logs": llm_logs,
        }

    finally:
        if should_close:
            db.close()


def _run_single_stage(stage_id: str, locked: dict, user_filled: dict,
                      prev_outputs: dict, db=None) -> dict:
    """单个 stage 的 LLM 调用 + JSON 解析"""
    defn = STAGE_DEFS[stage_id]
    prompt_def = STAGE_PROMPTS[stage_id]

    role = build_bootstrap_role(
        task_description=prompt_def["task"],
        locked_inputs=locked,
        prev_outputs=prev_outputs,
        max_tokens=defn["max_tokens"],
        temperature=defn["temperature"],
    )

    system_prompt = role.system_prompt
    user_prompt = (
        f"请输出 JSON，schema 参考：\n{json.dumps(prompt_def['json_schema'], ensure_ascii=False, indent=2)}\n"
        f"只输出 JSON，不要任何解释。"
    )

    llm = LLMFactory.create(db=db)
    response = llm.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=role.max_tokens,
        temperature=role.temperature,
        task_type=stage_id,  # 入 log 时按 stage 分类（stage_1_base / stage_2a_theme / ...）
    )

    return _parse_json(response)


def _continue_chapter_outlines_if_needed(
    first_result: dict,
    locked: dict,
    user_filled: dict,
    prev_outputs: dict,
    db,
    max_loops: int = 5,
) -> dict:
    """stage_4a_outline 续生成:LLM 一次调用常被 max_tokens 截断(30 章/批),
    自动检测 chapter_outlines 缺口,循环续写直到覆盖 total_chapters。

    续写时把已有 chapter_outlines + volumes/plot_lines/structure 作为上下文喂回去,
    让 LLM 接着写第 N+1 章到 total_chapters。

    Args:
        first_result: 第一次 LLM 调用的完整结果(含 volumes/plot_lines/structure/chapter_outlines)
        locked, user_filled, prev_outputs: 与 _run_single_stage 同样的入参
        db: SQLAlchemy Session
        max_loops: 最多续写几次(防失控),默认 5
    Returns:
        合并后的 result(dict),chapter_outlines 数量应覆盖 total_chapters
    """
    total = int(locked.get("total_chapters") or 0)
    if not total or total <= 0:
        return first_result  # 老项目没锁定 total_chapters,跳过
    chapter_outlines = list(first_result.get("chapter_outlines") or [])
    existing_nums = {int(c.get("chapter_num", 0)) for c in chapter_outlines if c.get("chapter_num")}
    missing_nums = sorted(set(range(1, total + 1)) - existing_nums)
    if not missing_nums:
        return first_result  # 已完整

    # 缺口超过 5 章才续写（容忍少数漏写）
    if len(missing_nums) < 5:
        logger.info(
            f"[stage_4a_outline] chapter_outlines 缺口 {len(missing_nums)} 章 (<5),"
            f"不续写; 缺失: {missing_nums[:10]}"
        )
        return first_result

    logger.info(
        f"[stage_4a_outline] chapter_outlines 不完整:已有 {len(chapter_outlines)}/{total} 章,"
        f"开始续写缺失的 {len(missing_nums)} 章(共 {len(missing_nums)} 章,最多 {max_loops} 轮)"
    )

    # 续写时把上下文压成简短摘要(避免 prompt 超长)
    context_summary = {
        "volumes": first_result.get("volumes", []),
        "plot_lines": [pl.get("title", "") for pl in first_result.get("plot_lines", [])],
        "structure": first_result.get("structure", {}),
        "pacing_notes": first_result.get("pacing_notes", ""),
        "outline_text": (first_result.get("outline_text", "") or "")[:500],
        "existing_chapter_titles": [
            f"第{c.get('chapter_num')}章《{c.get('title', '?')}》: {c.get('key_content', '')}"
            for c in chapter_outlines[-10:]  # 最后 10 章作为衔接
        ],
    }
    import json as _json
    context_str = _json.dumps(context_summary, ensure_ascii=False, indent=1)

    for loop_idx in range(max_loops):
        if not missing_nums:
            break
        # 取本轮要补的章号范围
        batch_size = 30  # 每轮 30 章
        batch_nums = missing_nums[:batch_size]
        batch_start = batch_nums[0]
        batch_end = batch_nums[-1]
        logger.info(
            f"[stage_4a_outline] 续写第 {loop_idx+1}/{max_loops} 轮:"
            f"补第 {batch_start}-{batch_end} 章(共 {len(batch_nums)} 章)"
        )

        # 续写 prompt
        continue_system = (
            "你正在为一部长篇小说续写缺失的章节大纲。\n"
            f"小说总章节数:{total}。需要补全第 {batch_start} 章到第 {batch_end} 章。\n"
            "\n"
            "【已有上下文摘要】\n"
            f"{context_str}\n"
            "\n"
            "【续写要求】\n"
            f"1. 仅输出 chapter_outlines 数组(其他字段都不需要)\n"
            f"2. 数组长度 = {len(batch_nums)}(第 {batch_start} 章到第 {batch_end} 章,不能漏)\n"
            "3. 每章只写 1 句话 key_content(≤40 字,描述本章 1 个核心事件)\n"
            "4. 严格禁止与已有章节的 key_content 重复(去重自检:相邻/任意两章重合度 < 40%)\n"
            "5. 同一人物/场景/物品的关键事件只能出现 1 次\n"
            "6. 标题不要「第 N 章」纯序号,要 4-15 字相关标题\n"
            "7. 保持与已有章节的 volume_num 分配一致\n"
            "\n"
            "返回 JSON 格式:\n"
            '{"chapter_outlines": [...]}'
        )

        try:
            from llm.factory import LLMFactory
            user_prompt = (
                f"请续写第 {batch_start} 章到第 {batch_end} 章的大纲(共 {len(batch_nums)} 章)。\n"
                "只输出 chapter_outlines 字段的 JSON,不要其他内容。"
            )
            llm = LLMFactory.create(db=db)
            response = llm.generate(
                prompt=user_prompt,
                system_prompt=continue_system,
                max_tokens=8192,  # 续写单轮 30 章够用
                temperature=0.6,
                task_type=f"stage_4a_outline_continue_{loop_idx}",
            )
            parsed = _parse_json(response)
            new_outlines = parsed.get("chapter_outlines", []) if isinstance(parsed, dict) else []
            if not new_outlines:
                logger.warning(
                    f"[stage_4a_outline] 续写第 {loop_idx+1} 轮 LLM 没返回 chapter_outlines,停止续写"
                )
                break
            chapter_outlines.extend(new_outlines)
            existing_nums = {int(c.get("chapter_num", 0)) for c in chapter_outlines if c.get("chapter_num")}
            missing_nums = sorted(set(range(1, total + 1)) - existing_nums)
            # 同步更新 context_summary 的最后 10 章(给下一轮用)
            context_summary["existing_chapter_titles"] = [
                f"第{c.get('chapter_num')}章《{c.get('title', '?')}》: {c.get('key_content', '')}"
                for c in chapter_outlines[-10:]
            ]
            context_str = _json.dumps(context_summary, ensure_ascii=False, indent=1)
            logger.info(
                f"[stage_4a_outline] 续写第 {loop_idx+1} 轮完成:新增 {len(new_outlines)} 章,"
                f"累计 {len(chapter_outlines)}/{total},剩 {len(missing_nums)} 章"
            )
        except Exception as e:
            logger.error(f"[stage_4a_outline] 续写第 {loop_idx+1} 轮失败: {e}")
            break

    first_result["chapter_outlines"] = chapter_outlines
    if len(chapter_outlines) < total:
        logger.warning(
            f"[stage_4a_outline] 续写后仍缺 {total - len(chapter_outlines)} 章"
            f"(目标 {total}, 实际 {len(chapter_outlines)}); 用户可手动到面板重新生成"
        )
    else:
        logger.info(
            f"[stage_4a_outline] 续写完成:chapter_outlines {len(chapter_outlines)}/{total} 章"
        )
    return first_result


def _parse_json(text: str) -> dict:
    """从 LLM 响应中解析 JSON（超级容错，专门对付 LLM 输出的非标 JSON）

    容错点（按顺序尝试，任意一步成功就返回）：
      1. 去掉 markdown ```json ``` 包装
      2. 截取首尾 {...} 范围
      3. 第一次尝试 strict mode（标准 JSON）—— 理想路径
      4. strict=False（允许 string value 里有 raw 换行符）
      5. 把 raw 控制字符（0x00-0x08 / 0x0B-0x1F）替换为空格后再试
      6. 修复 trailing comma（"a": 1, "b": 2, } → }）
      7. 修复中文逗号（“” 间的“，”被用作“分隔”）【中常出现】
      8. 尝试 json_repair 库（专门修复 LLM 输出，能处理绝大多数异常）
      9. 实在不行 → 抛出原始错误，调用方记录完整原始响应

    设计哲学：LLM 输出的 JSON 错误千奇百怪，宁可多写几层回退，
    也不要在生产环境上因为一个逗号问题让 30+ 块钱的 LLM 调用全部 failed。
    """
    original = text
    text = text.strip()

    # 1) 去掉 markdown 代码块
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    # 2) 截取首尾 {...} 范围（避免 LLM 前后加说明文本）
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    # 3) 第一次：标准 strict 模式（理想路径）
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 4) 第二次：strict=False（允许 string value 里有 raw 换行符）
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # 5) 第三次：把 raw 控制字符（除 \t\n\r 外）替换为空格
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # 6) 第四次：修复 trailing comma（对象 / 数组中的多余逗号）
    #    LLM 经常在最后一个元素后还带个 ","
    no_trail = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        return json.loads(no_trail, strict=False)
    except json.JSONDecodeError:
        pass

    # 7) 第五次：修复中文逗号（"x": "a"，"y": "b" → "x": "a", "y": "b"）
    #    中国 LLM（如 MiniMax / Qwen）偶尔会在多行 JSON 之间用全角逗号
    #    策略：只替换“看起来像是 key-value 分隔”的中文逗号
    #    判断方法："} ：" 后跟中文逗号 → 变 ASCII 逗号
    #    这里是保守修正，避免误伤 value 中本来含的中文逗号
    zh_comma_fixed = re.sub(r"([\}\]\"\'])\s*[\uff0c]\s*(\"[\w\-_]+\"\s*:)", r"\1, \2", no_trail)
    try:
        return json.loads(zh_comma_fixed, strict=False)
    except json.JSONDecodeError:
        pass

    # 8) 第六次：json_repair 库（专为修复 LLM 输出的 JSON，能处理大量边缘情况）
    #    包括：未闭合引号 / 缺失 key 引号 / 单引号 / 注释 / Python 布尔 None / 中文标点
    try:
        import json_repair
        repaired = json_repair.repair_json(text, return_objects=True)
        if repaired is not None:
            # json_repair 在某些边界情况会返回 list/None / 原始字符串，统一保证为 dict
            if isinstance(repaired, dict):
                return repaired
            # 如果 repair 返回了字符串，再试一次
            if isinstance(repaired, str):
                try:
                    return json.loads(repaired, strict=False)
                except json.JSONDecodeError:
                    pass
    except ImportError:
        # 库未安装，静默跳过（之前几层回退可能已经搞定）
        pass
    except Exception as e:
        # json_repair 本身出错（极罕见），不影响主流程
        pass

    # 9) 实在救不回来：记录完整原始响应 + 各种修复后的中间状态（调试用）
    #    注意：使用 logger.warning 而非 logger.error —— 这个错误在 stage 那里还会记录一次
    try:
        from logger import logger
        # 截断避免日志爆炸（保留前后片段）
        orig_preview = original[:300] + ("..." if len(original) > 300 else "")
        logger.warning(
            f"[JSON-parse] 全部回退均失败，原始响应（后 600 字符）:\n"
            f"  ...{original[-600:] if len(original) > 600 else original}"
        )
        # 同时把可能的“最优修复版”也记录下来，方便人工诊断
        logger.warning(
            f"[JSON-parse] 原文长度={len(original)}，含中文逗号={('，' in original)}, "
            f"含尾随逗号={bool(re.search(r',\\s*[}\\]]', original))}, "
            f"含 markdown 包装={original.strip().startswith('```')}"
        )
    except Exception:
        pass

    # 抛出最后一个错误（让上层 stage_xxx 标 failed 并继续重试机制）
    raise json.JSONDecodeError(
        "All 7 parse strategies failed. See [JSON-parse] warnings for original text.",
        text, 0,
    )


# ═══════════════════════════════════════════════════════════════
# 事务写入 DB
# ═══════════════════════════════════════════════════════════════

def commit_bootstrap(project_id: int, run_id: int, db) -> dict:
    """
    把 stage_results 事务写入 DB + 索引 RAG

    Returns:
        {"status": "committed" | "failed", "summary": {...}, "error": "..."}
    """
    from storage.models.workflow import WorkflowRun
    from storage.models import (
        Project, Theme, WorldEntry, Character, CharacterArc,
        CharacterRelation, ProjectOutline, Foreshadowing, Chapter, ChapterOutline,
    )

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"status": "failed", "error": "Run not found"}

    results = run.stage_results or {}

    try:
        # ── Stage 1: 更新 Project 基础参数 ──
        if results.get("stage_1_base", {}).get("status") == "ok":
            data = results["stage_1_base"]["data"]
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                if data.get("total_chapters"):
                    project.total_chapters = int(data["total_chapters"])
                if data.get("ai_removal"):
                    project.ai味去除程度 = int(data["ai_removal"])
                if data.get("est_total_words"):
                    # 存到 description 后缀（不污染用户原文）
                    total_w = int(data["est_total_words"])
                    if project.description and "[估算总字数：" not in project.description:
                        project.description += f"\n\n[估算总字数：{total_w} 字]"
                    elif not project.description:
                        project.description = f"[估算总字数：{total_w} 字]"

        # ── Stage 2A: Theme ──
        if results.get("stage_2a_theme", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2a_theme")
            theme_title = data.get("theme") or ""
            if theme_title:
                t = Theme(
                    project_id=project_id,
                    theme_type="core_theme",
                    title=theme_title,
                    description=f"基调：{data.get('tone', '')}",
                )
                db.add(t)

        # ── Stage 2B: Style + Pacing ──
        if results.get("stage_2b_style", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2b_style")
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                if data.get("style"):
                    project.writing_style = data["style"]
                if data.get("pacing"):
                    # 节奏存为附加 metadata（暂存到 description）
                    tag = f"[节奏：{data['pacing']}]"
                    if tag not in (project.description or ""):
                        project.description = (project.description or "") + f"\n{tag}"

        # ── Stage 2C: WorldEntry[] ──
        if results.get("stage_2c_world", {}).get("status") in ("ok", "user_filled"):
            data = _stage_data(results, "stage_2c_world")
            # data 可能是 dict（含 world_entries 列表）或字符串（premise 文本）
            if isinstance(data, str):
                we = WorldEntry(
                    project_id=project_id,
                    category="背景设定",
                    title="世界观背景",
                    content=data,
                )
                db.add(we)
            elif isinstance(data, dict):
                if data.get("world_entries"):
                    for we_data in data["world_entries"]:
                        we = WorldEntry(
                            project_id=project_id,
                            category=we_data.get("category", "背景设定"),
                            title=we_data.get("title", ""),
                            content=we_data.get("content", ""),
                            tags=we_data.get("tags", []),
                        )
                        db.add(we)
                elif data.get("premise"):
                    # user_filled 但以 dict 形式（兼容老数据）
                    we = WorldEntry(
                        project_id=project_id,
                        category="背景设定",
                        title="世界观背景",
                        content=data["premise"],
                    )
                    db.add(we)

        # ── Stage 3A/3B/3C: Characters + Relations ──
        # 复用 chapter_pipeline 里的去重 helper（LLM 经常把同一个角色用不同名字
        # 拆成 3A/3B/3C 三个 stage，导致同一个人被创建多次）
        from llm.chapter_pipeline import _find_existing_character
        char_map = {}  # name → id
        for stage_id, role_default, role_label_zh in [
            ("stage_3a_protagonist", "主角", "主角"),
            ("stage_3b_antagonist", "反派", "反派"),
            ("stage_3c_supporting", "配角", "配角"),
        ]:
            stage_info = results.get(stage_id, {})
            status = stage_info.get("status")
            if status == "ok" and stage_info.get("data"):
                # LLM 跑过的情况
                data = stage_info["data"]
                chars = _extract_characters(data, stage_id, role_default)
            elif status == "user_filled":
                # 用户填了的情况：用 LLM 把自由文本解析成结构化字段
                user_values = stage_info.get("user_values") or {}
                # stage_3a: user_values.protagonist / stage_3b: antagonist / stage_3c: supporting
                field_map = {
                    "stage_3a_protagonist": "protagonist",
                    "stage_3b_antagonist": "antagonist",
                    "stage_3c_supporting": "supporting",
                }
                user_text = user_values.get(field_map[stage_id], "")
                if not user_text:
                    continue
                # supporting 是多角色，用换行/句号分块；主角/反派是单段
                if stage_id == "stage_3c_supporting":
                    # 多个配角：用 LLM 一次性解析
                    structured = _parse_user_filled_character(
                        user_text, role_default, role_label_zh, db=db,
                    )
                    chars = [structured] if structured else []
                else:
                    structured = _parse_user_filled_character(
                        user_text, role_default, role_label_zh, db=db,
                    )
                    chars = [structured] if structured else []
            else:
                continue

            for c in chars:
                if not c:
                    continue
                cname = c.get("name", "").strip()
                if not cname or cname == "未命名":
                    continue
                # 去重：同项目下已有同名的就跳过新建，复用旧 id
                existing = _find_existing_character(db, project_id, cname)
                if existing:
                    logger.info(
                        f"[Bootstrap] 跳过新角色「{cname}」：已存在（id={existing.id}, 当前名={existing.name}）"
                    )
                    if cname:
                        char_map[cname] = existing.id
                    continue
                char = Character(
                    project_id=project_id,
                    name=cname,
                    role=c.get("role", role_default),
                    profile=c.get("profile", {}),
                    description=c.get("description", ""),
                )
                db.add(char)
                db.flush()
                if cname:
                    char_map[cname] = char.id
                logger.info(
                    f"[Bootstrap] 创建{role_label_zh}「{cname}」"
                    f"（id={char.id}, 来源={'user_filled' if status == 'user_filled' else 'llm'}, "
                    f"profile 字段数={len(c.get('profile', {}))})"
                )

        # Stage 3C 的 relations
        if results.get("stage_3c_supporting", {}).get("status") == "ok":
            rels = results["stage_3c_supporting"]["data"].get("relations", [])
            for rel in rels:
                from_id = char_map.get(rel.get("from"))
                to_id = char_map.get(rel.get("to"))
                if from_id and to_id and from_id != to_id:
                    relation = CharacterRelation(
                        project_id=project_id,
                        from_character_id=from_id,
                        to_character_id=to_id,
                        relation_type=rel.get("type", ""),
                        description=rel.get("description", ""),
                        strength=rel.get("strength", 5),
                        status=rel.get("status", "stable"),
                    )
                    db.add(relation)

        # ── Stage 3D: CharacterArc[] ──
        if results.get("stage_3d_arcs", {}).get("status") == "ok":
            arcs = results["stage_3d_arcs"]["data"].get("arcs", [])
            for arc in arcs:
                cid = char_map.get(arc.get("character_name"))
                if cid:
                    char_arc = CharacterArc(
                        project_id=project_id,
                        character_id=cid,
                        arc_type=arc.get("arc_type", "成长"),
                        start_state=arc.get("start_state", ""),
                        end_state=arc.get("end_state", ""),
                        current_state=arc.get("start_state", ""),
                        key_behavior=arc.get("key_behavior", ""),
                        is_stable=arc.get("is_stable", True),
                    )
                    db.add(char_arc)

        # ── Stage 4A: ProjectOutline（架构层：分卷/剧情线/四幕/反转/高潮）──
        # 旧版可能在 stage_4a_outline.data 里直接含 chapter_outlines
        # 新版拆出后 chapter_outlines 走 stage_4a_chapter_outlines.data
        # commit 时合并两处数据
        stage_4a = results.get("stage_4a_outline", {})
        stage_4a_extra = results.get("stage_4a_chapter_outlines", {})
        chapter_outlines_total: list = []
        if stage_4a.get("status") == "ok":
            data = stage_4a["data"]
            # 兼容老数据：旧版 4a_outline.data 里就含 chapter_outlines
            chapter_outlines_total = list(data.get("chapter_outlines", []) or [])
            outline = ProjectOutline(
                project_id=project_id,
                plot_lines=data.get("plot_lines", []),
                structure=data.get("structure", {}),
                pacing_notes=data.get("pacing_notes", ""),
                outline_text=data.get("outline_text", ""),
                reversal_schedule=data.get("reversal_schedule", {}),
                climax_map=data.get("climax_map", []),
                volumes=data.get("volumes", []),
                # 先把老数据里的 chapter_outlines 写进去,新版会被覆盖
                chapter_outlines=chapter_outlines_total,
            )
            db.add(outline)
            db.flush()
            outline_id = outline.id
        else:
            outline_id = None

        # ── Stage 4A-extra: chapter_outlines（每章 1 句话,单独 LLM 调用）──
        # 拆出后存到 ProjectOutline.chapter_outlines 字段
        if stage_4a_extra.get("status") == "ok":
            extra_data = stage_4a_extra["data"]
            extra_chapter_outlines = list(extra_data.get("chapter_outlines", []) or [])
            if extra_chapter_outlines:
                chapter_outlines_total = extra_chapter_outlines
            # 大纲质量自检
            try:
                _validate_chapter_outlines_uniqueness(
                    chapter_outlines_total,
                    project_total_chapters=project.total_chapters,
                )
            except Exception as e:
                logger.warning(f"[Bootstrap] 大纲质量自检发现问题: {e}")
            # 更新 ProjectOutline.chapter_outlines
            if outline_id:
                outline_row = db.query(ProjectOutline).filter(ProjectOutline.id == outline_id).first()
                if outline_row:
                    outline_row.chapter_outlines = chapter_outlines_total
                    db.commit()
            else:
                # 兼容：只跑了 4a_chapter_outlines 没跑 4a_outline
                # 把 chapter_outlines 写到一个临时 ProjectOutline(架构字段留空)
                outline = ProjectOutline(
                    project_id=project_id,
                    chapter_outlines=chapter_outlines_total,
                )
                db.add(outline)

        # ── Stage 4B: Foreshadowing[] ──
        foreshadow_map = {}  # title → id
        if results.get("stage_4b_foreshadow", {}).get("status") == "ok":
            fores = results["stage_4b_foreshadow"]["data"].get("foreshadowings", [])
            for fs in fores:
                fore = Foreshadowing(
                    project_id=project_id,
                    title=fs.get("title", ""),
                    content=fs.get("content", ""),
                    cycle=fs.get("type", "短伏笔"),
                    importance=fs.get("importance", "medium"),
                    connection_to_mainline=fs.get("connection_to_mainline", ""),
                    plant_order=fs.get("suggested_plant_chapter", 0),
                    status="active",
                )
                db.add(fore)
                db.flush()
                if fs.get("title"):
                    foreshadow_map[fs["title"]] = fore.id


        run.status = "committed"
        db.commit()

        # 索引 RAG（失败不影响主流程）
        # 使用新的统一 reindex_project_rag（包含 chapter_events 集合）
        try:
            from llm.chapter_pipeline import reindex_project_rag
            reindex_project_rag(project_id, db, with_signatures=True)
        except Exception as rag_err:
            logger.warning(f"[Bootstrap commit] reindex RAG 失败: {rag_err}")

        return {
            "status": "committed",
            "summary": {
                "themes": db.query(Theme).filter(Theme.project_id == project_id).count(),
                "world_entries": db.query(WorldEntry).filter(WorldEntry.project_id == project_id).count(),
                "characters": db.query(Character).filter(Character.project_id == project_id).count(),
                "relations": db.query(CharacterRelation).filter(CharacterRelation.project_id == project_id).count(),
                "arcs": db.query(CharacterArc).filter(CharacterArc.project_id == project_id).count(),
                "foreshadowings": db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id).count(),
                "chapters": db.query(Chapter).filter(Chapter.project_id == project_id).count(),
            },
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[Bootstrap commit] failed: {e}")
        return {"status": "failed", "error": str(e)}


def _stage_data(results: dict, stage_id: str) -> dict | str:
    """提取 stage 实际数据（user_filled 时可能是字符串）"""
    info = results.get(stage_id, {})
    if info.get("status") == "user_filled":
        return info.get("user_values", {})
    return info.get("data", {})


def _extract_characters(data: dict, stage_id: str, role_default: str) -> list[dict]:
    """从 stage 数据中提取角色列表"""
    if stage_id == "stage_3c_supporting":
        return data.get("supporting", [])
    # 主角 / 反派是单 character
    if data.get("name") or data.get("profile"):
        return [data]
    return []


def _parse_user_filled_character(
    user_text: str, role_default: str, role_label_zh: str, db=None,
) -> dict | None:
    """用 LLM 把用户填写的自由文本解析成结构化角色字段（与 stage_3a/3b 输出 schema 一致）。

    用户填的是自由文本（不是 JSON），如：
        **姓名**：陈默
        - **年龄**：26岁
        - **身份**：九重天系统·唯一指定天道客服
        - **性格**：情绪稳定、逻辑严密
        - **能力**：管理员权限

    Returns:
        {"name": "陈默", "profile": {...}, "description": "..."} 或 None（解析失败）
    """
    if not user_text or not user_text.strip():
        return None

    # 快速路径：尝试正则提取"姓名：X"（用户常见的 markdown 格式）
    import re
    name_match = re.search(r"姓\s*名\s*[:：]\s*([^\n\r*#-]+)", user_text)
    fast_name = name_match.group(1).strip() if name_match else None

    try:
        from llm.factory import LLMFactory
        system = (
            "你是一个角色设定解析器。把用户提供的角色自由文本解析为结构化 JSON。\n"
            f"用户填写的应该是「{role_label_zh}」。\n"
            "输出 schema：\n"
            "{\n"
            '  "name": "角色名（2-4 个汉字，必填）",\n'
            '  "profile": {\n'
            '    "age": "年龄字符串（如「26岁」「未知」）",\n'
            '    "gender": "男/女/其他/未知",\n'
            '    "identity": "身份/职业（1 句话）",\n'
            '    "personality": "性格特征（关键词，逗号分隔）",\n'
            '    "goal": "核心目标（1 句话）",\n'
            '    "ability": "能力/资源（1 句话）",\n'
            '    "catchphrase": "口头禅（可空）",\n'
            '    "background": "背景（1-2 句话）"\n'
            "  },\n"
            '  "description": "完整保留用户原文中关于该角色的描述（3-5 句话）"\n'
            "}\n"
            "只输出 JSON，不要任何解释。\n"
        )
        user_prompt = (
            f"用户输入的角色设定：\n{user_text}\n\n"
            "请按 schema 输出 JSON。"
        )

        llm = LLMFactory.create(db=db)
        response = llm.generate(
            prompt=user_prompt,
            system_prompt=system,
            max_tokens=1024,
            temperature=0.2,
            task_type="bootstrap_parse_user_character",
        )
        # 复用 workflow 内部的宽松 JSON 解析
        result = _parse_json(response)
        if not isinstance(result, dict):
            return None
        # 兜底：name 缺失时用 fast_name
        if not result.get("name") and fast_name:
            result["name"] = fast_name
        # 最后兜底：name 仍缺失
        if not result.get("name"):
            result["name"] = f"（{role_label_zh}）" if role_label_zh else "未命名"
        result.setdefault("profile", {})
        result.setdefault("description", user_text[:1000])
        result.setdefault("role", role_default)
        return result
    except Exception as e:
        logger.warning(f"[Bootstrap] 解析用户填写{role_label_zh}失败: {e}")
        # 兜底：纯文本入 description，name 用 fast_name
        return {
            "name": fast_name or f"（{role_label_zh}）",
            "profile": {},
            "description": user_text[:1000],
            "role": role_default,
        }


def _resolve_foreshadow_ids(notes: str, foreshadow_map: dict) -> list[int]:
    """从 foreshadow_notes 文本中匹配伏笔标题 → id"""
    if not notes or not foreshadow_map:
        return []
    ids = []
    for title, fid in foreshadow_map.items():
        if title and title in notes:
            ids.append(fid)
    return ids


def _validate_chapter_outlines_uniqueness(
    chapter_outlines: list, project_total_chapters: int = 0,
) -> list[str]:
    """大纲质量自检：检测相邻/任意两章的 key_content 文字重合度，发现问题就 warn。

    不抛异常（避免 commit 失败），只记录到日志供用户参考。
    用户看到警告后可以手动到「大纲」面板点击「重新生成大纲」重跑。

    Returns:
        warnings: 警告信息列表（每条形如 '第N章与第M章 key_content 文字重合 78%'）
    """
    warnings = []

    # 1) 长度检查
    if project_total_chapters and len(chapter_outlines) != project_total_chapters:
        warnings.append(
            f"chapter_outlines 数组长度 ({len(chapter_outlines)}) "
            f"!= total_chapters ({project_total_chapters})，可能漏章"
        )

    # 2) 按 chapter_num 排序
    sorted_outlines = sorted(chapter_outlines, key=lambda x: x.get("chapter_num", 0))

    # 3) 检测 key_content 文字重合度
    def _text_overlap_ratio(a: str, b: str) -> float:
        """简单字符级 Jaccard 相似度（A ∩ B / A ∪ B，按字符 2-gram 计算）。"""
        if not a or not b:
            return 0.0
        a2 = {a[i:i+2] for i in range(len(a) - 1)}
        b2 = {b[i:i+2] for i in range(len(b) - 1)}
        if not a2 or not b2:
            return 0.0
        inter = len(a2 & b2)
        union = len(a2 | b2)
        return inter / union if union else 0.0

    key_contents = [(c.get("chapter_num"), c.get("key_content", "").strip()) for c in sorted_outlines]

    # 相邻章检测
    for i in range(len(key_contents) - 1):
        n1, k1 = key_contents[i]
        n2, k2 = key_contents[i + 1]
        if not k1 or not k2:
            continue
        ratio = _text_overlap_ratio(k1, k2)
        if ratio > 0.5:
            warnings.append(
                f"第{n1}章与第{n2}章 key_content 文字重合度 {ratio:.0%} "
                f"（>50% 建议重跑 stage_4a_outline）"
            )

    # 任意两章检测（仅在章数 <=30 时跑全两两比较，避免性能问题）
    if len(key_contents) <= 30:
        for i in range(len(key_contents)):
            for j in range(i + 2, len(key_contents)):  # 跳过相邻（已检过）
                n1, k1 = key_contents[i]
                n2, k2 = key_contents[j]
                if not k1 or not k2:
                    continue
                ratio = _text_overlap_ratio(k1, k2)
                if ratio > 0.6:
                    warnings.append(
                        f"第{n1}章《{sorted_outlines[i].get('title', '?')}》"
                        f"与第{n2}章《{sorted_outlines[j].get('title', '?')}》"
                        f" key_content 文字重合度 {ratio:.0%}"
                    )

    if warnings:
        for w in warnings[:5]:  # 最多打 5 条，避免日志爆炸
            logger.warning(f"[大纲质量自检] {w}")
        if len(warnings) > 5:
            logger.warning(f"[大纲质量自检] ...还有 {len(warnings) - 5} 条警告未列出")

    return warnings


def _index_to_rag(project_id: int, db):
    """把所有生成的设定索引到 Chroma"""
    try:
        from rag.knowledge_base import KnowledgeBase
        from storage.models import Character, WorldEntry, Chapter

        kb = KnowledgeBase()

        for c in db.query(Character).filter(Character.project_id == project_id).all():
            try:
                kb.add_character(c)
            except Exception:
                pass

        for w in db.query(WorldEntry).filter(WorldEntry.project_id == project_id).all():
            try:
                kb.add_world_entry(w)
            except Exception:
                pass

        for ch in db.query(Chapter).filter(Chapter.project_id == project_id).all():
            try:
                kb.add_chapter(ch)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[RAG index] partial failure: {e}")


# ═══════════════════════════════════════════════════════════════
# 单 stage 重跑
# ═══════════════════════════════════════════════════════════════

def _rebuild_user_input_from_project(project_id: int, db) -> dict:
    """
    老 run 兼容：_meta.user_input 缺失时，从 Project 表反向重建。

    老 run 是在 rerun_stage 实现之前创建的，bootstrap 启动时没把 user_input
    存进 stage_results._meta，导致现在点重跑拿不到原始 user_input。

    重建策略：
      - title              ← Project.title
      - description        ← Project.description
      - chapter_word_count ← Project.target_word_count
      - genre              ← ""（Project 模型没这个字段，只能空缺，
                                 选填字段如 theme/tone/style 也都空缺）
      - 8 选填             ← 全部空（无法从 Project 表还原）

    返回：dict（4 必填部分填好，选填空）→ 可直接喂给 locked/user_filled。
         任何字段重建失败（如 project 不存在）→ 返回空 dict。
    """
    if not project_id:
        return {}
    try:
        from storage.models.project import Project

        proj = db.query(Project).filter(Project.id == project_id).first()
        if not proj:
            return {}
        return {
            "title": proj.title or "",
            "description": proj.description or "",
            "chapter_word_count": proj.target_word_count or 0,
            "genre": "",  # Project 模型无此字段，重跑时 LLM 上下文会缺 genre（可接受）
            "total_chapters": proj.total_chapters or 0,
            # 8 选填：Project 也没存这些，无法还原，留空（user_filled 全是 falsy 不会影响）
            "theme": "",
            "tone": "",
            "style": "",
            "pacing": "",
            "premise": "",
            "protagonist": "",
            "antagonist": "",
            "supporting": "",
            "notes": "",
        }
    except Exception as e:
        logger.warning(f"[RebuildUserInput] failed for project {project_id}: {e}")
        return {}


def rerun_stage(run_id: int, stage_id: str, db) -> dict:
    """
    重新跑某个 stage（覆盖之前的结果）

    注意：必须满足依赖；返回 {status, stage_result}
    """
    from storage.models.workflow import WorkflowRun

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"status": "failed", "error": "Run not found"}

    if stage_id not in STAGE_DEFS:
        return {"status": "failed", "error": f"Unknown stage: {stage_id}"}

    stage_def = STAGE_DEFS[stage_id]
    stage_results = dict(run.stage_results or {})

    # 检查依赖
    for dep in stage_def["depends_on"]:
        if stage_results.get(dep, {}).get("status") not in ("ok", "user_filled", "skipped"):
            return {"status": "failed", "error": f"Dependency {dep} not ready"}

    # 提取 locked + user_filled（从 _meta 读取持久化的 user_input）
    project_id = run.project_id
    meta = stage_results.get("_meta", {})
    user_input = meta.get("user_input", {})
    if not user_input:
        # 老 run 兼容：_meta.user_input 缺失时，从 Project 表反向重建
        # （老的 run 是在 rerun_stage 实现之前创建的，_meta 里没存 user_input）
        user_input = _rebuild_user_input_from_project(project_id, db)
        if not user_input:
            return {
                "status": "failed",
                "error": "user_input not found in run._meta and project is missing "
                         "(run predates rerun support)",
            }
        # 顺手把反推出来的 user_input 写回 _meta，下次直接命中
        stage_results["_meta"] = {
            **meta,
            "user_input": user_input,
            "user_input_source": "rebuilt_from_project",
            "user_input_rebuilt_at": time.time(),
        }
        run.stage_results = stage_results
        db.commit()

    locked = {
        "title": user_input.get("title", ""),
        "chapter_word_count": user_input.get("chapter_word_count", 0),
        "genre": user_input.get("genre", ""),
        "description": user_input.get("description", ""),
        # 续写机制需要：rerun 时也得把 total_chapters 透传下去
        "total_chapters": int(user_input.get("total_chapters") or 0),
    }
    user_filled = {
        k: v for k, v in user_input.items()
        if k not in locked and v
    }

    prev_outputs = {
        sid: stage_results[sid].get("data", {})
        for sid in stage_def["depends_on"]
        if sid in stage_results and "data" in stage_results[sid]
    }

    try:
        result = _run_single_stage(
            stage_id=stage_id,
            locked=locked,
            user_filled=user_filled,
            prev_outputs=prev_outputs,
            db=db,
        )
        # ── stage_4a_chapter_outlines 续生成：单独阶段也可能被截断
        #     (虽然 max_tokens=16384 通常够 100 章,但 LLM 偶尔输出 <N 章)
        if stage_id == "stage_4a_chapter_outlines" and isinstance(result, dict):
            # 把 result 包成类似老 stage_4a_outline 的结构,让 _continue_chapter_outlines_if_needed 能读
            wrapped = {"chapter_outlines": result.get("chapter_outlines", [])}
            wrapped = _continue_chapter_outlines_if_needed(
                wrapped, locked, user_filled, prev_outputs, db,
            )
            result["chapter_outlines"] = wrapped.get("chapter_outlines", [])
        stage_results[stage_id] = {"status": "ok", "data": result, "completed_at": time.time()}
        run.stage_results = stage_results
        db.commit()
        return {"status": "ok", "stage_result": stage_results[stage_id]}
    except Exception as e:
        stage_results[stage_id] = {
            "status": "failed",
            "error": str(e),
            "completed_at": time.time(),
        }
        run.stage_results = stage_results
        db.commit()
        return {"status": "failed", "error": str(e)}


def rerun_all_failed_stages(run_id: int, db, only_failed: bool = True, force_all: bool = False) -> dict:
    """
    重跑 run 中所有 stage（按依赖顺序串行执行）。

    Args:
        run_id: WorkflowRun.id
        db: SQLAlchemy Session
        only_failed: force_all=False 时有效 —— 现已废弃，由 force_all 接管语义
        force_all: True=重跑全部 stage（包括已成功的）；False=只重跑失败/未完成的

    Returns:
        {
            "status": "ok" | "failed",
            "rerun_stages": [stage_id, ...],   # 重跑了的
            "still_failed": [stage_id, ...],   # 重跑仍失败的
            "skipped_no_deps": [stage_id, ...] # 跳过（依赖未就绪）
            "error": "..." (出错时)
        }
    """
    from storage.models.workflow import WorkflowRun
    from storage.database import SessionLocal

    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return {"status": "failed", "error": "Run not found"}

        stage_results = dict(run.stage_results or {})
        meta = stage_results.get("_meta", {})
        user_input = meta.get("user_input", {})
        if not user_input:
            # 老 run 兼容：_meta.user_input 缺失时，从 Project 表反向重建
            user_input = _rebuild_user_input_from_project(run.project_id, db)
            if not user_input:
                return {
                    "status": "failed",
                    "error": "user_input not found in run._meta and project is missing "
                             "(run predates rerun support)",
                }
            # 写回 _meta，下次直接命中
            stage_results["_meta"] = {
                **meta,
                "user_input": user_input,
                "user_input_source": "rebuilt_from_project",
                "user_input_rebuilt_at": time.time(),
            }
            run.stage_results = stage_results
            db.commit()

        locked = {
            "title": user_input.get("title", ""),
            "chapter_word_count": user_input.get("chapter_word_count", 0),
            "genre": user_input.get("genre", ""),
            "description": user_input.get("description", ""),
        }
        user_filled = {
            k: v for k, v in user_input.items()
            if k not in locked and v
        }

        # 待重跑的 stage（按 stages 定义的顺序遍历，依赖关系保证上游先 OK）
        # 这里依赖 run.stages 的顺序（plan_bootstrap_stages 已按拓扑排序）
        # 关于 force_all 的语义：
        #   True  → 选所有非 user_filled/skipped 的 stage（包括已成功的也重跑）
        #           （用户场景：想完全重新生成所有设定）
        #   False → 只选 failed/cancelled/未开始的 stage
        #           （用户场景：bootstrap 跑到一半被取消或部分失败，一键继续）
        # 共同底线：user_filled（用户手填）和 skipped（明确跳过）永远不动
        targets: list[str] = []
        for stage in (run.stages or []):
            sid = stage["id"]
            cur_status = stage_results.get(sid, {}).get("status")
            if cur_status in ("user_filled", "skipped"):
                # 用户手填 / 明确跳过的：永远不动
                continue
            if force_all:
                # 强制重跑全部：ok 也要重跑
                targets.append(sid)
            elif cur_status == "ok":
                # 非强制模式：已成功的跳过
                continue
            else:
                # failed / cancelled / None
                targets.append(sid)

        if not targets:
            return {
                "status": "ok",
                "rerun_stages": [],
                "still_failed": [],
                "skipped_no_deps": [],
                "message": "没有需要重跑的 stage",
            }

        rerun_stages: list[str] = []
        still_failed: list[str] = []
        skipped_no_deps: list[str] = []
        completed_set: set[str] = set()

        # 收集已成功 stage 的 data 作为 prev_outputs
        for stage in (run.stages or []):
            sid = stage["id"]
            sr_info = stage_results.get(sid, {})
            if sr_info.get("status") in ("ok", "user_filled") and "data" in sr_info:
                completed_set.add(sid)

        # 顺手把 run 状态恢复 running（让前端轮询能看到变化）
        run.status = "running"
        db.commit()

        for sid in targets:
            stage_def = STAGE_DEFS.get(sid)
            if not stage_def:
                continue

            # 检查依赖：依赖的 stage 必须 ok/user_filled/skipped 之一
            deps_ok = True
            for dep in stage_def["depends_on"]:
                dep_status = stage_results.get(dep, {}).get("status")
                if dep_status not in ("ok", "user_filled", "skipped"):
                    deps_ok = False
                    break
            if not deps_ok:
                stage_results[sid] = {
                    "status": "failed",
                    "error": f"依赖未满足: {stage_def['depends_on']}",
                }
                run.stage_results = stage_results
                db.commit()
                skipped_no_deps.append(sid)
                still_failed.append(sid)
                continue

            # 立即标 running 让前端能看见
            stage_results[sid] = {
                "status": "running",
                "started_at": time.time(),
            }
            run.stage_results = stage_results
            db.commit()

            # 构造 prev_outputs
            prev_outputs = {
                dep: stage_results[dep].get("data", {})
                for dep in stage_def["depends_on"]
                if dep in stage_results and "data" in stage_results[dep]
            }

            try:
                result = _run_single_stage(
                    stage_id=sid,
                    locked=locked,
                    user_filled=user_filled,
                    prev_outputs=prev_outputs,
                    db=db,
                )
                stage_results[sid] = {
                    "status": "ok",
                    "data": result,
                    "completed_at": time.time(),
                }
                completed_set.add(sid)
                rerun_stages.append(sid)
            except Exception as e:
                logger.error(f"[Bootstrap rerun-all] stage {sid} failed: {e}")
                stage_results[sid] = {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": time.time(),
                }
                still_failed.append(sid)

        # 重新计算 run 总状态
        has_failure = any(r.get("status") == "failed" for r in stage_results.values())
        all_done = all(
            r.get("status") in ("ok", "user_filled", "skipped")
            for r in stage_results.values()
        )
        if has_failure:
            run.status = "failed"
        elif all_done:
            run.status = "completed"
        else:
            run.status = "partial"
        run.stage_results = stage_results
        # 更新 current_stage_index
        run.current_stage_index = sum(
            1 for r in stage_results.values()
            if r.get("status") in ("ok", "user_filled", "skipped")
        )
        db.commit()

        logger.info(
            f"[Bootstrap rerun-all] run={run_id} rerun={rerun_stages} "
            f"still_failed={still_failed} skipped_no_deps={skipped_no_deps} "
            f"final_status={run.status}"
        )
        return {
            "status": "ok",
            "rerun_stages": rerun_stages,
            "still_failed": still_failed,
            "skipped_no_deps": skipped_no_deps,
            "run_status": run.status,
        }
    finally:
        if should_close:
            db.close()

"""
评审评分权重系统
==================

设计原则：
- 综合分满分 100 分（不再使用 0-10 平均分）
- 8 个维度按重要性分配权重（重点维度给更多权重）
- 单维度评分仍为 0-10 分

权重分配（按重要性递减）：

| 维度              | 权重 | 说明                                            |
|-------------------|------|-------------------------------------------------|
| 一致性 (consistency)     | 15   | 人物/世界/时间线的一致性是小说可信度的根本      |
| 节奏 (pacing)            | 14   | 节奏决定读者是否继续阅读                        |
| 去AI味 (ai_removal)      | 13   | AI 辅助写作场景的核心痛点                       |
| 伏笔管理 (foreshadowing) | 13   | 长篇小说情节连贯性的关键                        |
| 角色弧光 (character_arc) | 12   | 角色成长是读者共鸣的来源                        |
| 文笔风格 (style)         | 12   | 文字表达力                                      |
| 主旨契合 (thematic)      | 11   | 主题表达                                        |
| 字数合规 (word_count)    | 10   | 仅字数控制，机械指标                            |
| **合计**                 | **100** |                                              |

公式：overall = Σ(score_i × weight_i) / 10
- 所有维度满分时：overall = 100
- 一致性满分其余零分：overall = 15
- 所有维度均分 5：overall = 50
"""


# 8 维度权重（综合分满分 100）
REVIEW_WEIGHTS = {
    "consistency":    15,  # 一致性
    "pacing":         14,  # 节奏
    "ai_removal":     13,  # 去AI味
    "foreshadowing":  13,  # 伏笔管理
    "character_arc":  12,  # 角色弧光
    "style":          12,  # 文笔风格
    "thematic":       11,  # 主旨契合
    "word_count":     10,  # 字数合规
}

# 期望的 8 个评分维度（用于校验 LLM 返回的完整性）
EXPECTED_REVIEW_KEYS = list(REVIEW_WEIGHTS.keys())


def calculate_overall_score(scores: dict) -> float:
    """根据各维度评分 + 权重计算综合分（满分 100）。

    Args:
        scores: 各维度评分 dict，如 {"consistency": 8.5, "pacing": 7.0, ...}
                单维度取值 0-10。

    Returns:
        0-100 的浮点数综合分。若 scores 为空返回 0.0。
    """
    if not scores:
        return 0.0
    total = sum(
        scores.get(k, 0) * w
        for k, w in REVIEW_WEIGHTS.items()
    )
    return round(total / 10, 1)


def calculate_average_score(scores: dict) -> float:
    """简单平均分（0-10），仅供 decide_revision 等决策场景用，
    不作为综合分展示。"""
    if not scores:
        return 0.0
    return round(sum(scores.values()) / len(scores), 2)

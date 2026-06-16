"""RAG 检索服务 - 拼接上下文（含主题/伏笔/风格）"""
from rag.knowledge_base import KnowledgeBase
from storage.models import Project, Theme, Foreshadowing, CharacterArc
from sqlalchemy.orm import Session
from storage.database import SessionLocal


# 写作风格描述
STYLE_PROMPTS = {
    "优美": "文字优美流畅，善用修辞，场景描写如诗如画，情感表达细腻动人。",
    "幽默": "语言轻松诙谐，善用反转和调侃，情节中穿插有趣的细节，让读者会心一笑。",
    "冷峻": "文字克制理性，描写客观冷静，情节推进干脆利落，少用煽情和过度修饰。",
    "平实": "文字朴素自然，叙事清晰直接，不堆砌华丽辞藻，注重故事本身的力量。",
    "诗意": "文字富有韵律和意境，善用留白和象征，情感表达含蓄而深远。",
}

# 去AI味强度描述
AI_REMOVAL_PROMPTS = {
    1: "允许适度的模板化表达，效率优先。",
    3: "减少机械化的连接词使用，避免过于工整的句式。",
    5: "适当变化句式长度，增加对话的自然感，减少过度完美的修辞。",
    7: "刻意打破模板化表达，增加口语化、个性化的叙述方式。",
    9: "强烈要求去除AI味，文字要有手工感和个性，避免完美无缺的机械感。",
}


class RetrievalService:
    """
    RAG 检索服务
    根据查询拼接角色/世界观/章节/主题/伏笔/风格上下文
    """

    SYSTEM_PROMPT_TEMPLATE = """你是一位专业的小说写作助手，根据以下设定和上下文帮助用户续写或修改小说内容。

## 核心主旨与作者意图
{themes}

## 角色设定
{characters}

## 角色弧光现状
{character_arcs}

## 世界观设定
{world}

## 已写章节摘要
{chapters}

## 进行中的伏笔（请注意不要与已有伏笔矛盾）
{foreshadowings}

## 写作风格要求
{writing_style}

## 字数要求
目标字数：{target_word_count} 字
允许范围：{word_count_range}

## 写作要求
- 严格按照上述角色设定，保持人物性格一致
- 遵循世界观设定，不要引入矛盾
- 参考已写章节的内容和风格
- 注意伏笔的埋设和回收，不要与已有伏笔冲突
- 角色弧光发展要符合其成长轨迹
- 严格遵守字数要求
- 回复只输出小说正文，不要输出其他内容
"""

    def __init__(self, knowledge_base: KnowledgeBase | None = None):
        self.kb = knowledge_base or KnowledgeBase()

    def build_context(
        self,
        project_id: int,
        current_chapter_id: int | None = None,
        query: str = "",
        db: Session | None = None,
    ) -> dict[str, str]:
        """
        构建完整的 RAG 上下文

        Args:
            project_id: 项目 ID
            current_chapter_id: 当前章节 ID
            query: 用户查询/写作上下文
            db: 数据库会话（可选，用于查询主题/伏笔等）

        Returns:
            {"system_prompt": ..., "characters_context": ..., ...}
        """
        # 检索相关角色
        char_results = self.kb.search_characters(query, top_k=5)
        characters_text = self._format_char_results(char_results)

        # 检索相关世界观
        world_results = self.kb.search_world(query, top_k=5)
        world_text = self._format_world_results(world_results)

        # 检索相关章节
        chapter_results = self.kb.search_chapters(query, top_k=3)
        chapters_text = self._format_chapter_results(chapter_results)

        # 从数据库补充更多上下文
        themes_text = ""
        foreshadowings_text = ""
        character_arcs_text = ""
        project_info = {}

        if db is None:
            db = SessionLocal()

        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project_info = {
                    "writing_style": project.writing_style,
                    "target_word_count": project.target_word_count,
                    "word_count_min": project.word_count_min,
                    "word_count_max": project.word_count_max,
                    "ai_removal": project.ai味去除程度,
                }

                # 核心主题
                themes = db.query(Theme).filter(Theme.project_id == project_id).all()
                if themes:
                    themes_text = "\n".join([
                        f"- [{t.theme_type}] {t.title}: {t.description}"
                        for t in themes
                    ])

                # 活跃伏笔
                fores = db.query(Foreshadowing).filter(
                    Foreshadowing.project_id == project_id,
                    Foreshadowing.status.in_(["active", "planted"]),
                ).all()
                if fores:
                    foreshadowings_text = "\n".join([
                        f"- 【{fs.title}】{fs.content[:100]}"
                        for fs in fores[:10]
                    ])

                # 角色弧光
                arcs = db.query(CharacterArc).filter(
                    CharacterArc.project_id == project_id
                ).all()
                if arcs:
                    from storage.models import Character
                    char_map = {c.id: c.name for c in db.query(Character).filter(Character.project_id == project_id).all()}
                    character_arcs_text = "\n".join([
                        f"- {char_map.get(arc.character_id, '未知')}（{arc.arc_type}弧光）:"
                        f" 起始={arc.start_state}, 当前={arc.current_state}, 目标={arc.end_state}"
                        for arc in arcs
                    ])
        finally:
            if db:
                db.close()

        # 构建风格描述
        style = project_info.get("writing_style", "平实")
        ai_level = project_info.get("ai_removal", 7)
        style_text = STYLE_PROMPTS.get(style, STYLE_PROMPTS["平实"])
        style_text += AI_REMOVAL_PROMPTS.get(ai_level, AI_REMOVAL_PROMPTS[7])

        # 字数要求
        target = project_info.get("target_word_count", 3000)
        wc_min = project_info.get("word_count_min", 2700)
        wc_max = project_info.get("word_count_max", 3300)
        wc_range = f"{wc_min}～{wc_max} 字"

        # 拼接 system prompt
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            themes=themes_text or "（暂无核心主旨设定）",
            characters=characters_text or "（暂无角色设定）",
            character_arcs=character_arcs_text or "（暂无角色弧光记录）",
            world=world_text or "（暂无世界观设定）",
            chapters=chapters_text or "（暂无已写章节）",
            foreshadowings=foreshadowings_text or "（暂无进行中的伏笔）",
            writing_style=style_text,
            target_word_count=target,
            word_count_range=wc_range,
        )

        return {
            "system_prompt": system_prompt,
            "characters_context": characters_text,
            "world_context": world_text,
            "chapters_context": chapters_text,
            "themes_context": themes_text,
            "foreshadowings_context": foreshadowings_text,
            "character_arcs_context": character_arcs_text,
        }

    def _format_char_results(self, results: dict) -> str:
        if not results.get("documents") or not results["documents"][0]:
            return ""
        return "\n".join(results["documents"][0])

    def _format_world_results(self, results: dict) -> str:
        if not results.get("documents") or not results["documents"][0]:
            return ""
        return "\n".join(results["documents"][0])

    def _format_chapter_results(self, results: dict) -> str:
        if not results.get("documents") or not results["documents"][0]:
            return ""
        return "\n".join(results["documents"][0])

    # ─── 9 步流水线专用方法 ───

    def build_event_dedup_context(
        self,
        project_id: int,
        query: str,
        exclude_chapter_id: int | None = None,
        db: Session | None = None,
        top_k: int = 3,
        similarity_threshold: float = 0.5,
    ) -> dict:
        """为新章节构建"已发生相似事件"清单（用于防重复写作）。

        Args:
            query: 本章的 tentative key_content / plot_advance，用于语义检索
            exclude_chapter_id: 排除自身（重写场景）
            top_k: 最多返回几条
            similarity_threshold: 低于此相似度的不返回（避免噪音）

        Returns:
            {
                "matches": [
                    {"chapter": 2, "title": "...", "signature": "...", "similarity": 0.78},
                    ...
                ],
                "max_similarity": 0.78,  # 用于评审 role 判定
                "raw_query": query,
            }
        """
        if not query or not query.strip():
            return {"matches": [], "max_similarity": 0.0, "raw_query": query or ""}
        try:
            raw = self.kb.search_chapter_events(
                query=query.strip(),
                project_id=project_id,
                top_k=top_k,
                exclude_chapter_id=exclude_chapter_id,
            )
        except Exception as e:
            from logger import logger
            logger.warning(f"[RetrievalService] build_event_dedup_context failed: {e}")
            return {"matches": [], "max_similarity": 0.0, "raw_query": query}

        matches = [
            {
                "chapter": m["order"] + 1,  # 1-based 给前端/LLM 看
                "chapter_id": m["chapter_id"],
                "title": m["title"],
                "signature": m["signature"],
                "similarity": round(m["similarity"], 3),
            }
            for m in raw
            if m["similarity"] >= similarity_threshold
        ]
        max_sim = max((m["similarity"] for m in matches), default=0.0)
        return {
            "matches": matches,
            "max_similarity": round(max_sim, 3),
            "raw_query": query,
        }

    def build_chapter_rag_context(
        self,
        project_id: int,
        chapter_id: int | None,
        query: str,
        db: Session | None = None,
        top_k_chars: int = 3,
        top_k_events: int = 3,
    ) -> dict:
        """9 步流水线专用：拉取相关 characters + chapter_events，作为"软上下文"。

        与 build_context() 的区别：
        - build_context() 用于手动 AI 续写（生成.py），是全量拼 system prompt
        - build_chapter_rag_context() 只返回"语义相关"的子集，给 build_chapter_prep_info 注入

        Returns:
            {
                "characters": [  # 语义相关角色
                    {"name": "...", "role": "...", "profile_text": "..."},
                ],
                "events": [  # 语义相关过去事件
                    {"chapter": 2, "title": "...", "signature": "...", "similarity": 0.78},
                ],
            }
        """
        if not query or not query.strip():
            return {"characters": [], "events": []}
        try:
            char_hits = self.kb.search_characters(query, top_k=top_k_chars)
        except Exception:
            char_hits = {"documents": [[]], "metadatas": [[]]}
        try:
            event_hits = self.kb.search_chapter_events(
                query=query.strip(),
                project_id=project_id,
                top_k=top_k_events,
                exclude_chapter_id=chapter_id,
            )
        except Exception:
            event_hits = []

        characters = []
        try:
            docs = (char_hits.get("documents") or [[]])[0]
            metas = (char_hits.get("metadatas") or [[]])[0]
            for doc, meta in zip(docs, metas):
                characters.append({
                    "name": (meta or {}).get("name", ""),
                    "role": (meta or {}).get("role", ""),
                    "profile_text": doc or "",
                })
        except Exception:
            pass

        events = [
            {
                "chapter": h["order"] + 1,
                "chapter_id": h["chapter_id"],
                "title": h["title"],
                "signature": h["signature"],
                "similarity": round(h["similarity"], 3),
            }
            for h in event_hits
        ]
        return {"characters": characters, "events": events}

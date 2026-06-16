"""RAG 知识库管理"""
from rag.vector_store import VectorStore
from rag.embedder import LocalEmbedder
from storage.models import Character, WorldEntry, Chapter
from typing import Optional
import uuid


COLLECTION_CHARACTERS = "characters"
COLLECTION_WORLD = "worldbuilding"
COLLECTION_CHAPTERS = "chapters"
COLLECTION_CHAPTER_EVENTS = "chapter_events"


class KnowledgeBase:
    """RAG 知识库管理器"""

    def __init__(self, embedder: LocalEmbedder | None = None):
        self.vector_store = VectorStore()
        self.embedder = embedder or LocalEmbedder()
        self._ensure_collections()

    def _ensure_collections(self):
        """确保必要的 collection 存在"""
        for name in [COLLECTION_CHARACTERS, COLLECTION_WORLD, COLLECTION_CHAPTERS, COLLECTION_CHAPTER_EVENTS]:
            self.vector_store.get_or_create_collection(name)

    # ─── Character 操作 ───

    def add_character(self, character: Character) -> str:
        """添加角色到知识库"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHARACTERS)
        doc_id = f"char_{character.id}"
        embedding = self.embedder.embed_single(character.profile_text)
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[character.profile_text],
            metadatas=[{"name": character.name, "role": character.role}],
        )
        return doc_id

    def delete_character(self, character_id: int):
        """从知识库删除角色"""
        collection = self.vector_store.get_collection(COLLECTION_CHARACTERS)
        try:
            collection.delete(ids=[f"char_{character_id}"])
        except Exception:
            pass

    def update_character(self, character: Character):
        """更新角色（删除旧记录再添加新记录）"""
        self.delete_character(character.id)
        self.add_character(character)

    # ─── WorldEntry 操作 ───

    def add_world_entry(self, entry: WorldEntry) -> str:
        """添加世界观条目"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_WORLD)
        doc_id = f"world_{entry.id}"
        embedding = self.embedder.embed_single(entry.summary_text)
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[entry.summary_text],
            metadatas=[{"category": entry.category, "title": entry.title}],
        )
        return doc_id

    def delete_world_entry(self, entry_id: int):
        """删除世界观条目"""
        collection = self.vector_store.get_collection(COLLECTION_WORLD)
        try:
            collection.delete(ids=[f"world_{entry_id}"])
        except Exception:
            pass

    def update_world_entry(self, entry: WorldEntry):
        """更新世界观条目"""
        self.delete_world_entry(entry.id)
        self.add_world_entry(entry)

    # ─── Chapter 操作 ───

    def add_chapter(self, chapter: Chapter) -> str:
        """添加章节摘要到知识库"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHAPTERS)
        doc_id = f"chapter_{chapter.id}"
        embedding = self.embedder.embed_single(chapter.summary)
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[chapter.summary],
            metadatas=[{"title": chapter.title, "order": chapter.order}],
        )
        return doc_id

    def delete_chapter(self, chapter_id: int):
        """删除章节"""
        collection = self.vector_store.get_collection(COLLECTION_CHAPTERS)
        try:
            collection.delete(ids=[f"chapter_{chapter_id}"])
        except Exception:
            pass

    def update_chapter(self, chapter: Chapter):
        """更新章节"""
        self.delete_chapter(chapter.id)
        self.add_chapter(chapter)

    # ─── 检索 ───

    def search_characters(self, query: str, top_k: int = 5) -> list:
        """检索相关角色"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHARACTERS)
        query_embedding = self.embedder.embed_single(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        return results

    def search_world(self, query: str, top_k: int = 5) -> list:
        """检索相关世界观条目"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_WORLD)
        query_embedding = self.embedder.embed_single(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        return results

    def search_chapters(self, query: str, top_k: int = 3) -> list:
        """检索相关章节"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHAPTERS)
        query_embedding = self.embedder.embed_single(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        return results

    # ─── Chapter Event 操作（用于 RAG 去重检索）───

    def add_chapter_event(self, chapter: Chapter) -> str:
        """添加章节事件签名到 chapter_events 集合。

        存储的是 chapter.event_signature_text (event_signature > synopsis > content[:300] 降级)，
        语义密度高，适合用作"事件级"语义去重。
        """
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHAPTER_EVENTS)
        doc_id = f"event_{chapter.id}"
        text = chapter.event_signature_text
        embedding = self.embedder.embed_single(text)
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "title": chapter.title or "",
                "order": int(chapter.order or 0),
                "project_id": int(chapter.project_id or 0),
                "signature": (chapter.event_signature or "")[:200],
            }],
        )
        return doc_id

    def update_chapter_event(self, chapter: Chapter) -> None:
        """更新章节事件（先删后加）"""
        self.delete_chapter_event(chapter.id)
        self.add_chapter_event(chapter)

    def delete_chapter_event(self, chapter_id: int) -> None:
        """从 chapter_events 集合删除"""
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHAPTER_EVENTS)
        try:
            collection.delete(ids=[f"event_{chapter_id}"])
        except Exception:
            pass

    def search_chapter_events(
        self, query: str, project_id: int, top_k: int = 5, exclude_chapter_id: int | None = None,
    ) -> list[dict]:
        """检索相似过去章节事件（用于 RAG 去重）。

        Returns:
            [
                {"chapter_id": 2, "order": 1, "title": "...", "signature": "...",
                 "distance": 0.32, "similarity": 0.68},
                ...
            ]
        """
        collection = self.vector_store.get_or_create_collection(COLLECTION_CHAPTER_EVENTS)
        if not query or not query.strip():
            return []
        # 多查一些再过滤
        fetch_k = top_k + (1 if exclude_chapter_id else 0) + 2
        try:
            query_embedding = self.embedder.embed_single(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(fetch_k, 20),
                where={"project_id": int(project_id)} if project_id else None,
            )
        except Exception:
            return []

        out = []
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        for cid, doc, meta, dist in zip(ids, docs, metas, distances):
            # 解析 chapter_id
            try:
                ch_id = int(str(cid).replace("event_", ""))
            except (ValueError, TypeError):
                continue
            if exclude_chapter_id and ch_id == exclude_chapter_id:
                continue
            # Cosine 距离 → 相似度（m3e-base 已 normalize）
            try:
                sim = max(0.0, min(1.0, 1.0 - float(dist)))
            except (ValueError, TypeError):
                sim = 0.0
            out.append({
                "chapter_id": ch_id,
                "order": int((meta or {}).get("order", 0)),
                "title": (meta or {}).get("title", ""),
                "signature": (meta or {}).get("signature", "") or (doc or "").split("\n", 1)[-1].strip()[:200],
                "distance": float(dist) if dist is not None else 0.0,
                "similarity": sim,
            })
            if len(out) >= top_k:
                break
        return out

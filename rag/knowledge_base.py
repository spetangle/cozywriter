"""RAG 知识库管理"""
from rag.vector_store import VectorStore
from rag.embedder import LocalEmbedder
from storage.models import Character, WorldEntry, Chapter
from typing import Optional
import uuid


COLLECTION_CHARACTERS = "characters"
COLLECTION_WORLD = "worldbuilding"
COLLECTION_CHAPTERS = "chapters"


class KnowledgeBase:
    """RAG 知识库管理器"""

    def __init__(self, embedder: LocalEmbedder | None = None):
        self.vector_store = VectorStore()
        self.embedder = embedder or LocalEmbedder()
        self._ensure_collections()

    def _ensure_collections(self):
        """确保必要的 collection 存在"""
        for name in [COLLECTION_CHARACTERS, COLLECTION_WORLD, COLLECTION_CHAPTERS]:
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

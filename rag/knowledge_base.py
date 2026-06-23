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
            metadatas=[{
                "name": character.name,
                "role": character.role,
                "project_id": int(character.project_id or 0),
            }],
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
            metadatas=[{
                "title": chapter.title,
                "order": int(chapter.order or 0),
                "project_id": int(chapter.project_id or 0),
            }],
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
                where={"project_id": str(project_id)} if project_id else None,
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

    # ─── 项目级清理 ───

    def delete_project_data(self, project_id: str) -> dict:
        """删除一个项目在所有 RAG 集合里的数据。

        应用场景：项目被删除时调用,避免旧项目的角色/世界观/章节/事件
        残留到新建项目中(新项目 id 可能复用旧 id,导致 RAG 误命中)。

        Returns:
            {
                "characters_deleted": N,
                "world_deleted": N,
                "chapters_deleted": N,
                "chapter_events_deleted": N,
                "orphan_by_id_deleted": N,
            }
        """
        from storage.models import Chapter, Character, WorldEntry
        from storage.database import SessionLocal

        pid = str(project_id)  # hex 字符串,不要 int()
        result = {
            "characters_deleted": 0,
            "world_deleted": 0,
            "chapters_deleted": 0,
            "chapter_events_deleted": 0,
            "orphan_by_id_deleted": 0,
        }

        db = SessionLocal()
        try:
            # 1) 按 metadata.project_id 删除（适用于 chapter_events 等已有此字段的集合）
            for cname in [COLLECTION_CHAPTER_EVENTS, COLLECTION_CHAPTERS, COLLECTION_CHARACTERS, COLLECTION_WORLD]:
                coll = self.vector_store.get_or_create_collection(cname)
                try:
                    # ChromaDB 的 where filter：精确匹配
                    # （注意：$eq 是默认的,所以 {"project_id": pid} 等价 {"project_id": {"$eq": pid}}）
                    existing = coll.get(where={"project_id": pid}, include=[])
                    ids_to_del = existing.get("ids") or []
                    if ids_to_del:
                        coll.delete(ids=ids_to_del)
                        key = cname + "_deleted"
                        if cname == COLLECTION_CHAPTER_EVENTS:
                            result["chapter_events_deleted"] += len(ids_to_del)
                        elif cname == COLLECTION_CHAPTERS:
                            result["chapters_deleted"] += len(ids_to_del)
                        elif cname == COLLECTION_CHARACTERS:
                            result["characters_deleted"] += len(ids_to_del)
                        elif cname == COLLECTION_WORLD:
                            result["world_deleted"] += len(ids_to_del)
                except Exception as e:
                    # 旧版本 ChromaDB 可能不支持 where / metadata index
                    pass

            # 2) 按 DB 里的实际 id 列表精确删除（兜底：处理无 project_id 元数据的旧记录）
            char_ids = [c.id for c in db.query(Character.id).filter(Character.project_id == pid).all()]
            ch_ids = [c.id for c in db.query(Chapter.id).filter(Chapter.project_id == pid).all()]
            from storage.models import WorldEntry
            world_ids = [w.id for w in db.query(WorldEntry.id).filter(WorldEntry.project_id == pid).all()]

            for prefix, id_list, cname in (
                ("char_", char_ids, COLLECTION_CHARACTERS),
                ("chapter_", ch_ids, COLLECTION_CHAPTERS),
                ("event_", ch_ids, COLLECTION_CHAPTER_EVENTS),
                ("world_", world_ids, COLLECTION_WORLD),
            ):
                if not id_list:
                    continue
                coll = self.vector_store.get_or_create_collection(cname)
                ids = [f"{prefix}{i}" for i in id_list]
                try:
                    coll.delete(ids=ids)
                    result["orphan_by_id_deleted"] += len(ids)
                except Exception:
                    pass
        finally:
            db.close()

        return result

    def sweep_orphan_records(self) -> dict:
        """扫描并删除 RAG 里的孤儿记录。

        三种"孤儿"判定（任一命中即删）：
          1. 记录指向的 entity_id 在 DB 里不存在（chapter/character/world 已被删）
          2. 记录 metadata.project_id 对应的项目在 DB 里已删除
            （即使 entity_id 还在,记录也属于已删除项目,会污染新项目）
          3. 同 id 但内容不匹配（防止 id 复用导致 RAG 留下旧数据）
            - characters: 比较 name（DB 改名/换角色 → RAG 旧的失效）
            - chapters:   比较 title 或 content[:100]
            - worldbuilding: 比较 title

        用于：历史遗留的 RAG 数据,即使项目已被删除,孤儿记录还在。
        Returns:
            {collection_name: 删除数量, ...}
        """
        from storage.models import Chapter, Character, WorldEntry, Project
        from storage.database import SessionLocal

        result = {COLLECTION_CHARACTERS: 0, COLLECTION_CHAPTERS: 0,
                  COLLECTION_CHAPTER_EVENTS: 0, COLLECTION_WORLD: 0}

        db = SessionLocal()
        try:
            # 取 DB 里所有有效 entity（id → 实体的关键字段）
            char_by_id = {c.id: c for c in db.query(Character).all()}
            ch_by_id = {c.id: c for c in db.query(Chapter).all()}
            world_by_id = {w.id: w for w in db.query(WorldEntry).all()}
            valid_project_ids = {p.id for p in db.query(Project.id).all()}

            # 扫每个集合
            for cname, prefix, valid_by_id in (
                (COLLECTION_CHARACTERS, "char_", char_by_id),
                (COLLECTION_CHAPTERS, "chapter_", ch_by_id),
                (COLLECTION_CHAPTER_EVENTS, "event_", ch_by_id),
                (COLLECTION_WORLD, "world_", world_by_id),
            ):
                coll = self.vector_store.get_or_create_collection(cname)
                try:
                    all_data = coll.get(include=["metadatas"])
                except Exception:
                    continue
                all_ids = all_data.get("ids") or []
                metas = all_data.get("metadatas") or []
                to_del = []
                for i, rid in enumerate(all_ids):
                    s = str(rid)
                    if not s.startswith(prefix):
                        continue
                    # 判定 1: entity_id 不在 DB
                    try:
                        entity_id = int(s[len(prefix):])
                    except ValueError:
                        continue
                    entity = valid_by_id.get(entity_id)
                    if entity is None:
                        to_del.append(s)
                        continue

                    # 判定 2: metadata.project_id 指向已删除项目
                    m = metas[i] if i < len(metas) else {}
                    meta_pid = m.get("project_id") if isinstance(m, dict) else None
                    if meta_pid is not None:
                        try:
                            meta_pid_int = int(meta_pid)
                        except (ValueError, TypeError):
                            meta_pid_int = None
                        if meta_pid_int is not None and meta_pid_int not in valid_project_ids:
                            to_del.append(s)
                            continue

                    # 判定 3: 同 id 但内容已变更（id 复用 → RAG 旧数据失效）
                    if prefix == "char_":
                        # 角色：比较 name（必须严格一致）
                        meta_name = (m or {}).get("name") if isinstance(m, dict) else None
                        if meta_name and meta_name != entity.name:
                            to_del.append(s)
                            continue
                    elif prefix == "chapter_":
                        # 章节：比较 title（章节改名 → RAG 旧数据失效）
                        meta_title = (m or {}).get("title") if isinstance(m, dict) else None
                        if meta_title and meta_title != entity.title:
                            to_del.append(s)
                            continue
                    elif prefix == "event_":
                        # event：检查 chapter 关联是否一致（chapter 的 project_id 是否匹配）
                        # 这里 meta project_id 已经在判定 2 检过,这里再核 event 的章节是否还属于 event 自己声称的项目
                        # 比较 event 的 signature 与 chapter.event_signature 前缀一致
                        meta_sig = (m or {}).get("signature") if isinstance(m, dict) else None
                        ch_sig = getattr(entity, "event_signature", "") or ""
                        if meta_sig and ch_sig and meta_sig[:60] != ch_sig[:60]:
                            to_del.append(s)
                            continue
                    elif prefix == "world_":
                        meta_title = (m or {}).get("title") if isinstance(m, dict) else None
                        if meta_title and meta_title != entity.title:
                            to_del.append(s)
                            continue
                if to_del:
                    try:
                        coll.delete(ids=to_del)
                        result[cname] = len(to_del)
                    except Exception:
                        pass
        finally:
            db.close()
        return result

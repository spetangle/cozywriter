"""项目 ID 迁移：int → 8 位 hex

检测老 schema（projects.id 是 INTEGER），把每个老项目的 int ID 重生成为 hex 字符串，
并把 13 个关联表里的 project_id FK 同步更新。

SQLite 不支持直接 DROP COLUMN 含 PK 的列,所以采用：
  1. 添加临时列（_new_*  TEXT）
  2. UPDATE 填入新值
  3. SQLite ALTER TABLE RENAME COLUMN 把新列改名
  4. DROP 老列

注意：SQLite 3.35+ 支持 DROP COLUMN。SQLAlchemy 的 batch_alter_table 会自动处理。
"""
import logging
import secrets
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _is_old_schema(engine: Engine) -> bool:
    """projects.id 列类型是 INTEGER 吗?"""
    insp = inspect(engine)
    if not insp.has_table("projects"):
        return False
    cols = insp.get_columns("projects")
    id_col = next((c for c in cols if c["name"] == "id"), None)
    if not id_col:
        return False
    type_name = str(id_col["type"]).upper()
    return "INT" in type_name and "VARCHAR" not in type_name and "TEXT" not in type_name


def _new_id_for(old_id: int) -> str:
    """给老 int id 生成新 hex。保证不撞。"""
    return secrets.token_hex(4)


def migrate_project_ids(engine: Engine = None) -> dict:
    """主迁移函数

    Returns:
        {
            "migrated": True/False,
            "projects_migrated": N,
            "tables_updated": [list of table names],
        }
    """
    from storage.database import engine as default_engine

    eng = engine or default_engine

    if not _is_old_schema(eng):
        return {"migrated": False, "reason": "schema 已是新格式或表不存在"}

    # 列出所有 project_id 是 INTEGER 的子表（依赖 projects.id 的 FK）
    insp = inspect(eng)
    child_tables = []
    # 这些是已知的子表（project_id 是 Integer FK）
    known_child_tables = [
        "chapters", "characters", "character_arcs", "character_relations",
        "themes", "foreshadowings", "consistency_records",
        "world_entries", "outline_nodes", "project_outlines",
        "chapter_outlines", "review_sessions",
        "inspirations",  # project_id nullable
        "workflow_runs",
        "plot_points",
    ]
    for t in known_child_tables:
        if insp.has_table(t):
            cols = {c["name"]: c for c in insp.get_columns(t)}
            if "project_id" in cols:
                type_name = str(cols["project_id"]["type"]).upper()
                if "INT" in type_name and "VARCHAR" not in type_name and "TEXT" not in type_name:
                    child_tables.append(t)

    result = {"migrated": True, "projects_migrated": 0, "tables_updated": child_tables}

    with eng.begin() as conn:
        # 1) 取所有老项目（id + new_id 映射）
        rows = conn.execute(text("SELECT id FROM projects")).fetchall()
        id_map = {}
        for (old_id,) in rows:
            new_id = _new_id_for(old_id)
            # 极端情况下 hex 可能撞（42亿分之一）,重来一次
            while new_id in id_map.values():
                new_id = _new_id_for(old_id)
            id_map[old_id] = new_id
        result["projects_migrated"] = len(id_map)

        # 2) projects 表：加临时列 → 更新 → 改名 → DROP 老列
        conn.execute(text("ALTER TABLE projects ADD COLUMN _new_id TEXT"))
        for old_id, new_id in id_map.items():
            conn.execute(
                text("UPDATE projects SET _new_id = :new WHERE id = :old"),
                {"new": new_id, "old": old_id},
            )
        # SQLite: 删老 PK 列需要"表重建"流程
        # 步骤：建新表 → 复制数据 → 删老表 → 改名
        conn.execute(text("""
            CREATE TABLE projects__new (
                id TEXT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT DEFAULT '',
                genre VARCHAR(200) DEFAULT '',
                word_count INTEGER DEFAULT 0,
                writing_style VARCHAR(50) DEFAULT '平实',
                "ai味去除程度" INTEGER DEFAULT 7,
                target_word_count INTEGER DEFAULT 3000,
                word_count_min INTEGER DEFAULT 2700,
                word_count_max INTEGER DEFAULT 3300,
                total_chapters INTEGER DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO projects__new
                (id, title, description, genre, word_count, writing_style,
                 "ai味去除程度", target_word_count, word_count_min, word_count_max,
                 total_chapters, created_at, updated_at)
            SELECT _new_id, title, description, genre, word_count, writing_style,
                 "ai味去除程度", target_word_count, word_count_min, word_count_max,
                 total_chapters, created_at, updated_at
            FROM projects
        """))
        conn.execute(text("DROP TABLE projects"))
        conn.execute(text("ALTER TABLE projects__new RENAME TO projects"))

        # 3) 子表：project_id INTEGER → TEXT
        for tname in child_tables:
            try:
                conn.execute(text(f'ALTER TABLE {tname} ADD COLUMN _new_pid TEXT'))
                for old_id, new_id in id_map.items():
                    conn.execute(
                        text(f"UPDATE {tname} SET _new_pid = :new WHERE project_id = :old"),
                        {"new": new_id, "old": old_id},
                    )
                # 重建表：保留其它所有列,把 _new_pid 改名为 project_id,类型 TEXT
                # 重要:id 列必须保持 PRIMARY KEY（让 SQLite 用 rowid alias 自动填充）
                cols_info = conn.execute(text(f"PRAGMA table_info({tname})")).fetchall()
                # cols_info: (cid, name, type, notnull, dflt_value, pk)
                other_cols = [c for c in cols_info if c[1] not in ("project_id", "_new_pid")]

                # 构造新表 schema,id 列必须有 PRIMARY KEY
                col_defs_full = []
                for c in cols_info:
                    if c[1] in ("project_id", "_new_pid"):
                        continue
                    parts = [f'"{c[1]}"', c[2]]
                    if c[1] == "id":
                        # 重建时 id 必须带 PRIMARY KEY（rowid alias,自动填充）
                        parts.append("PRIMARY KEY")
                    elif c[3]:  # notnull
                        parts.append("NOT NULL")
                    if c[4] is not None:  # default
                        parts.append(f"DEFAULT {c[4]}")
                    col_defs_full.append(" ".join(parts))
                col_defs_full.append('"project_id" TEXT')
                col_defs_str = ", ".join(col_defs_full)

                # 取老表的 SELECT 列表
                select_cols = ", ".join(f'"{c[1]}"' for c in other_cols) + ', _new_pid AS project_id'

                conn.execute(text(f"CREATE TABLE {tname}__new ({col_defs_str})"))
                conn.execute(text(f"INSERT INTO {tname}__new SELECT {select_cols} FROM {tname}"))
                conn.execute(text(f"DROP TABLE {tname}"))
                conn.execute(text(f"ALTER TABLE {tname}__new RENAME TO {tname}"))

                # 重建索引（如果有 project_id 索引）
                # SQLite 索引在 DROP TABLE 时会一并删除,需要重新创建
                idx_list = conn.execute(text(f"PRAGMA index_list({tname})")).fetchall()
                for idx in idx_list:
                    # idx: (seq, name, unique, origin, partial)
                    idx_name = idx[1]
                    idx_info = conn.execute(text(f"PRAGMA index_info({idx_name})")).fetchall()
                    cols_in_idx = ", ".join(f'"{i[2]}"' for i in idx_info)
                    is_unique = "UNIQUE " if idx[2] else ""
                    try:
                        conn.execute(text(f"CREATE {is_unique}INDEX {idx_name} ON {tname} ({cols_in_idx})"))
                    except Exception:
                        pass  # 索引可能已存在或创建失败,不影响数据
            except Exception as e:
                logger.error(f"[migrate] 更新表 {tname} 失败: {e}")
                # 失败的话这张表保持原状,但 projects 主表已迁移 → 子表的 int FK 悬空
                # 需要让用户知道
                raise

        # 4) Inspiration 表:consumed_into 字段是 "project_id:chapter_id" 格式字符串,
        #    需要替换其中的 old project_id → new project_id
        if insp.has_table("inspirations"):
            insp_cols = {c["name"]: c for c in insp.get_columns("inspirations")}
            if "consumed_into" in insp_cols:
                # 格式 "old_pid:chapter_id" → "new_pid:chapter_id"
                for old_id, new_id in id_map.items():
                    conn.execute(
                        text("UPDATE inspirations SET consumed_into = REPLACE(consumed_into, :prefix, :new_prefix) WHERE consumed_into LIKE :pattern"),
                        {"prefix": f"{old_id}:", "new_prefix": f"{new_id}:", "pattern": f"{old_id}:%"},
                    )

        # 5) Inspiration 的 related_characters / related_chapters JSON 字段:
        #    [{"project_id": 1, "character_id": 2}] → [{"project_id": "hex", ...}]
        #    留待应用层处理(每次读时兼容 int → str),不在迁移脚本改

    logger.info(f"[migrate] 完成: {result}")
    return result
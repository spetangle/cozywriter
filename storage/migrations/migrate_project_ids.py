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
        "chapter_outlines", "review_sessions", "full_review_sessions",
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
        # 不能硬编码老 schema：用旧表实际列 + ORM 当前列的并集，避免丢掉
        # project_type / script_format / script_episode_count 等后加字段。
        from storage.models.project import Project as _ProjectModel

        old_info = conn.execute(text("PRAGMA table_info(projects)")).fetchall()
        old_col_names = {row[1] for row in old_info}

        col_defs = []
        for row in old_info:
            _, name, type_name, notnull, default, _pk = row
            if name in ("_new_id",):
                continue
            if name == "id":
                col_defs.append('"id" TEXT PRIMARY KEY')
                continue
            parts = [f'"{name}"', type_name or "TEXT"]
            if notnull:
                parts.append("NOT NULL")
            if default is not None:
                parts.append(f"DEFAULT {default}")
            col_defs.append(" ".join(parts))

        # 补上 ORM 有、但旧库缺的列（例如 project_type / script_*）。
        for col in _ProjectModel.__table__.columns:
            if col.name in old_col_names or col.name == "id":
                continue
            type_sql = col.type.compile(dialect=eng.dialect)
            parts = [f'"{col.name}"', type_sql]
            if not col.nullable:
                parts.append("NOT NULL")
            col_defs.append(" ".join(parts))

        conn.execute(text(f"CREATE TABLE projects__new ({', '.join(col_defs)})"))

        insert_cols = ["id"] + [row[1] for row in old_info if row[1] not in ("id", "_new_id")]
        insert_col_sql = ", ".join(f'"{name}"' for name in insert_cols)
        select_exprs = ["_new_id"] + [f'"{name}"' for name in insert_cols[1:]]
        conn.execute(text(
            f"INSERT INTO projects__new ({insert_col_sql}) "
            f"SELECT {', '.join(select_exprs)} FROM projects"
        ))
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

                # 必须在 DROP TABLE 之前保存索引 SQL；DROP 后 sqlite_master 里
                # 原索引记录已经消失，旧代码在 DROP 后 PRAGMA index_list 拿不到。
                saved_index_sql = [
                    row[0] for row in conn.execute(text(
                        "SELECT sql FROM sqlite_master WHERE type='index' "
                        "AND tbl_name = :tname AND sql IS NOT NULL"
                    ), {"tname": tname}).fetchall()
                ]

                conn.execute(text(f"CREATE TABLE {tname}__new ({col_defs_str})"))
                conn.execute(text(f"INSERT INTO {tname}__new SELECT {select_cols} FROM {tname}"))
                conn.execute(text(f"DROP TABLE {tname}"))
                conn.execute(text(f"ALTER TABLE {tname}__new RENAME TO {tname}"))

                # 恢复原索引定义
                for idx_sql in saved_index_sql:
                    try:
                        conn.execute(text(idx_sql))
                    except Exception as idx_err:
                        logger.warning(f"[migrate] 重建索引失败 {tname}: {idx_err}")
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
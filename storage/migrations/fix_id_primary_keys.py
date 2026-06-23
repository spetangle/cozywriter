"""修复迁移后丢失 PRIMARY KEY 的 id 列。

背景：
  迁移脚本（migrate_project_ids）在把 child 表 project_id INT → TEXT 时，
  CREATE TABLE __new 的 SQL 漏掉了 id INTEGER PRIMARY KEY。
  SQLite 的 INTEGER PRIMARY KEY 不写就是 rowid alias，加 NOT NULL 但没 PK 就会
  变成普通 NOT NULL 列，无法自动填充。
  还有早期失败的 ALTER 留下的 id_old 残留列。

修复策略：
  1. 检测每个表的"主键列"——找名为 id 的列，且 PRAGMA table_info 的 pk > 0
  2. 如果主键列叫 id_old（残留）,直接 RENAME 回 id
  3. 如果主键列不存在（缺失）,重建表加上 INTEGER PRIMARY KEY
  4. 如果主键列存在但是 NOT NULL 而非 PRIMARY KEY（迁移 bug）,
     重建表把 id 改为 INTEGER PRIMARY KEY
"""
import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def fix_id_primary_keys(engine) -> dict:
    """修复所有丢失 PRIMARY KEY 的 id 列。"""
    insp = inspect(engine)
    result = {"tables_fixed": [], "tables_skipped": [], "tables_errored": []}

    all_tables = insp.get_table_names()
    candidate_tables = [t for t in all_tables if t not in ("projects", "alembic_version")]

    with engine.begin() as conn:
        for tname in candidate_tables:
            try:
                cols = conn.execute(text(f"PRAGMA table_info({tname})")).fetchall()
                if not cols:
                    result["tables_skipped"].append(tname)
                    continue

                # 找名为 id 或 id_old 的列
                id_col = next((c for c in cols if c[1] == "id"), None)
                id_old_col = next((c for c in cols if c[1] == "id_old"), None)

                # 情况 1:有 id_old 残留（之前的失败 ALTER 留下的）→ 先重命名为 id
                if id_old_col and not id_col:
                    conn.execute(text(f"ALTER TABLE {tname} RENAME COLUMN id_old TO id"))
                    # 重新读 schema
                    cols = conn.execute(text(f"PRAGMA table_info({tname})")).fetchall()
                    id_col = next((c for c in cols if c[1] == "id"), None)

                if not id_col:
                    result["tables_skipped"].append(tname)
                    continue

                # 情况 2:id 已经是 PRIMARY KEY（pk > 0）→ 跳过
                if id_col[5]:  # pk 字段
                    result["tables_skipped"].append(tname)
                    continue

                # 情况 3:id 是 NOT NULL 但没 PRIMARY KEY → 重建表
                # 重新构造 schema,把 id 列标记为 PRIMARY KEY
                def col_def(c):
                    cid, name, ctype, notnull, dflt, pk = c
                    parts = [f'"{name}"', ctype]
                    if name == "id":
                        parts.append("PRIMARY KEY")
                    elif notnull:
                        parts.append("NOT NULL")
                    if dflt is not None:
                        parts.append(f"DEFAULT {dflt}")
                    return " ".join(parts)

                col_defs = [col_def(c) for c in cols]
                col_names = [c[1] for c in cols]
                cols_csv = ", ".join(f'"{n}"' for n in col_names)

                row_count = conn.execute(text(f"SELECT COUNT(*) FROM {tname}")).scalar() or 0

                # 重建
                conn.execute(text(f"CREATE TABLE {tname}__new ({', '.join(col_defs)})"))
                if row_count > 0:
                    conn.execute(
                        text(f"INSERT INTO {tname}__new ({cols_csv}) SELECT {cols_csv} FROM {tname}")
                    )
                conn.execute(text(f"DROP TABLE {tname}"))
                conn.execute(text(f"ALTER TABLE {tname}__new RENAME TO {tname}"))

                # 重建索引
                idx_list = conn.execute(text(f"PRAGMA index_list({tname})")).fetchall()
                for idx in idx_list:
                    idx_name = idx[1]
                    if idx_name.startswith("sqlite_"):
                        continue
                    idx_info = conn.execute(text(f"PRAGMA index_info({idx_name})")).fetchall()
                    cols_in_idx = ", ".join(f'"{i[2]}"' for i in idx_info)
                    is_unique = "UNIQUE " if idx[2] else ""
                    try:
                        conn.execute(text(f"CREATE {is_unique}INDEX {idx_name} ON {tname} ({cols_in_idx})"))
                    except Exception:
                        pass

                result["tables_fixed"].append(tname)
                logger.info(f"[fix_pk] {tname}: 修复 PRIMARY KEY (rows={row_count})")
            except Exception as e:
                result["tables_errored"].append({"table": tname, "error": str(e)})
                logger.error(f"[fix_pk] {tname} 失败: {e}")

    return result
"""数据库迁移脚本：对比 ORM model，给老表加缺失列。

用法：
    python migrate.py
"""
import sqlite3

from sqlalchemy import inspect, text

from storage.database import engine
import storage.models  # noqa: F401  确保 metadata 已注册
from storage.models.base import Base


def get_existing_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def render_column_for_add(col) -> str:
    """构造 ADD COLUMN 子句：列名 类型 DEFAULT ... [NOT NULL]"""
    parts = []
    # 列名 + 类型
    parts.append(f'"{col.name}"')
    parts.append(col.type.compile(engine.dialect))

    # 默认值
    default = getattr(col, "default", None)
    if default is not None and default.arg is not None:
        # 把 Python 字面量塞回去（只处理简单值）
        arg = default.arg
        if callable(arg):
            # default=dict / default=list 等 callable default → 调用获取实际值
            try:
                arg = arg()
            except Exception:
                arg = None
        if arg is not None:
            if isinstance(arg, (dict, list)):
                import json
                parts.append(f"DEFAULT '{json.dumps(arg, ensure_ascii=False)}'")
            elif isinstance(arg, str):
                parts.append(f"DEFAULT '{arg.replace(chr(39), chr(39)*2)}'")
            else:
                parts.append(f"DEFAULT {arg}")
    elif not col.nullable and col.name not in ("id",):
        # 非空无默认值 → SQLite 不允许；实际表都是允许 NULL 的情况较多
        pass

    # Server default（datetime.utcnow 等）
    if default is None and col.server_default is not None:
        sd = str(col.server_default.arg)
        parts.append(f"DEFAULT {sd}")

    if not col.nullable:
        parts.append("NOT NULL")

    return " ".join(parts)


def main():
    insp = inspect(engine)
    sqlite_path = engine.url.database
    conn = sqlite3.connect(sqlite_path)

    total_added = 0
    try:
        for table in Base.metadata.sorted_tables:
            tname = table.name
            if not insp.has_table(tname):
                continue

            existing = get_existing_columns(conn, tname)
            missing = [c for c in table.columns if c.name not in existing]
            if not missing:
                continue

            print(f"[{tname}] 缺 {len(missing)} 列: {[c.name for c in missing]}")
            for col in missing:
                col_def = render_column_for_add(col)
                sql = f'ALTER TABLE "{tname}" ADD COLUMN {col_def}'
                try:
                    conn.execute(sql)
                    print(f"  + {col.name}: {col_def}")
                    total_added += 1
                except Exception as e:
                    print(f"  ! {col.name} 失败: {e}")
                    raise
        conn.commit()
        print(f"\n迁移完成，新增 {total_added} 列。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
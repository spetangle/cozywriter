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
            import datetime as _dt
            if isinstance(arg, (dict, list)):
                import json
                parts.append(f"DEFAULT '{json.dumps(arg, ensure_ascii=False)}'")
            elif isinstance(arg, str):
                parts.append(f"DEFAULT '{arg.replace(chr(39), chr(39)*2)}'")
            elif isinstance(arg, (_dt.datetime, _dt.date, _dt.time)):
                # ALTER TABLE ADD COLUMN 不接受 Python datetime 字面量；
                # CURRENT_TIMESTAMP 是 SQLite 允许的常量默认值。
                parts.append("DEFAULT CURRENT_TIMESTAMP")
            elif isinstance(arg, bool):
                parts.append(f"DEFAULT {1 if arg else 0}")
            else:
                parts.append(f"DEFAULT {arg}")
    elif not col.nullable and col.name not in ("id",):
        # 非空无默认值 → SQLite 不允许；实际表都是允许 NULL 的情况较多
        pass

    # Server default（datetime.utcnow 等）
    if default is None and col.server_default is not None:
        sd = str(col.server_default.arg)
        # server_default 可能是 SQL 片段（如 CURRENT_TIMESTAMP）或字符串字面量。
        if sd and not (sd.startswith("'") or sd.startswith('"') or sd.isidentifier()
                       or sd.isdigit() or "(" in sd):
            sd = f"'{sd}'"
        parts.append(f"DEFAULT {sd}")

    # ADD COLUMN 只有在已有默认值时才能安全加 NOT NULL；否则会直接失败。
    if not col.nullable and any(p.startswith("DEFAULT") for p in parts):
        parts.append("NOT NULL")

    return " ".join(parts)


def apply_migrations(db_engine=None):
    """对已有库补 ORM 新列/新表。

    返回 {"added": int, "created": int, "errors": [...]}。启动时调用应捕获
    异常，避免迁移失败阻止服务启动；手动执行 `python migrate.py` 时仍会打印详情。
    """
    db_engine = db_engine or engine
    insp = inspect(db_engine)
    sqlite_path = db_engine.url.database
    conn = sqlite3.connect(sqlite_path)

    total_added = 0
    total_created = 0
    try:
        # 1. 创建不存在的新表
        for table in Base.metadata.sorted_tables:
            tname = table.name
            if not insp.has_table(tname):
                print(f"[新表] {tname} 不存在，创建中...")
                table.create(db_engine, checkfirst=True)
                print(f"  ✓ {tname} 创建成功")
                total_created += 1

        # 2. 给已有表补缺失列
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
        print(f"\n迁移完成: 新增 {total_added} 列, 创建 {total_created} 张新表。")
        return {"added": total_added, "created": total_created, "errors": []}
    finally:
        conn.close()


def main():
    return apply_migrations(engine)


if __name__ == "__main__":
    main()
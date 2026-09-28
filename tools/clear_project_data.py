"""清理旧库中的项目数据，保留系统配置。

保留：providers / system_settings / llm_hyperparam_presets / custom_genres
清除：projects 及其全部关联数据（章节、角色、大纲、主题、伏笔、剧本、道具、
      分镜、工作流、灵感、问卷等），以及项目维度的 token 用量记录。

用法：
    python tools/clear_project_data.py --dry-run          # 只预览，不修改
    python tools/clear_project_data.py --yes              # 备份后执行
    python tools/clear_project_data.py --yes --clear-rag  # 同时清空 data/chroma

安全措施：
- 必须显式传 --yes 才会真正删除；默认 dry-run
- 执行前自动复制一份数据库到 data/backups/
- 删除期间关闭外键约束，完成后重新开启并做 foreign_key_check
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 这些表是纯系统配置，永远保留
KEEP_TABLES = {"providers", "system_settings", "llm_hyperparam_presets", "custom_genres"}
# 无 project_id、但随项目数据一起清除的子表
CHILD_TABLES = ["chapter_outlines", "chapter_versions"]


def _all_tables(conn):
    return [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]


def _columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def _count(conn, table):
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.Error:
        return 0


def plan(conn):
    """返回 (project_scoped_tables, child_tables, other_clear_tables)。"""
    tables = _all_tables(conn)
    project_scoped = []
    for t in tables:
        if t in KEEP_TABLES:
            continue
        if t == "projects":
            continue
        cols = _columns(conn, t)
        if "project_id" in cols:
            project_scoped.append(t)
    child = [t for t in CHILD_TABLES if t in tables]
    other = [t for t in ("creative_questionnaires",) if t in tables]
    return project_scoped, child, other


def backup_db(db_path):
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"cozywriter_before_clear_{stamp}.db")
    shutil.copy2(db_path, dest)
    return dest


def clear_rag():
    rag_dir = os.path.join(ROOT, "data", "chroma")
    if os.path.isdir(rag_dir):
        shutil.rmtree(rag_dir, ignore_errors=True)
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description="清理旧库项目数据，保留系统配置")
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "cozywriter.db"))
    ap.add_argument("--yes", action="store_true", help="确认执行删除（否则仅 dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="只预览")
    ap.add_argument("--clear-rag", action="store_true", help="同时清空 data/chroma 向量库")
    args = ap.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f"[x] 数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    project_scoped, child, other = plan(conn)

    print("=" * 60)
    print(f"数据库: {db_path}")
    print("-" * 60)
    print("【保留的系统配置】")
    for t in sorted(KEEP_TABLES):
        if t in _all_tables(conn):
            print(f"  keep  {t:26} rows={_count(conn, t)}")
    print("【将清除的项目数据】")
    total = 0
    for t in child + other + project_scoped + ["projects"]:
        if t in _all_tables(conn) and t != "llm_usage_records":
            n = _count(conn, t)
            total += n
            print(f"  clear {t:26} rows={n}")

    # 项目维度的 token 用量：只删有 project_id 的，保留全局统计
    usage_tables = []
    if "llm_usage_records" in _all_tables(conn):
        cols = _columns(conn, "llm_usage_records")
        if "project_id" in cols:
            n = conn.execute(
                "SELECT COUNT(*) FROM llm_usage_records WHERE project_id IS NOT NULL"
            ).fetchone()[0]
            total += n
            usage_tables = [("llm_usage_records", n)]
            print(f"  clear {'llm_usage_records(项目)':26} rows={n}")

    print("-" * 60)
    print(f"合计将删除约 {total} 行")
    print("=" * 60)

    if args.dry_run or not args.yes:
        print("\n[dry-run] 未做任何修改。确认无误后加 --yes 执行。")
        conn.close()
        return 0

    backup = backup_db(db_path)
    print(f"\n[✓] 已备份: {backup}")

    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        # 先删子表（它们通过 chapter_id 关联 chapters）
        for t in child:
            conn.execute(f'DELETE FROM "{t}"')
        for t in other:
            conn.execute(f'DELETE FROM "{t}"')
        for t in project_scoped:
            if t == "llm_usage_records":
                conn.execute("DELETE FROM llm_usage_records WHERE project_id IS NOT NULL")
            else:
                conn.execute(f'DELETE FROM "{t}"')
        conn.execute("DELETE FROM projects")
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        # 自增序列归零（sqlite_sequence 可能不存在）
        try:
            for t in child + other + project_scoped + ["projects"]:
                conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (t,))
            conn.commit()
        except sqlite3.Error:
            pass
        conn.execute("VACUUM")
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[x] 清理失败，已回滚: {e}")
        return 1

    print("\n【清理后校验】")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"  外键孤儿: {len(violations)}")
    for t in sorted(KEEP_TABLES):
        if t in _all_tables(conn):
            print(f"  keep  {t:26} rows={_count(conn, t)}")
    for t in child + other + project_scoped + ["projects"]:
        if t in _all_tables(conn):
            print(f"  now   {t:26} rows={_count(conn, t)}")
    if "llm_usage_records" in _all_tables(conn):
        remaining = conn.execute(
            "SELECT COUNT(*) FROM llm_usage_records WHERE project_id IS NOT NULL"
        ).fetchone()[0]
        print(f"  now   {'llm_usage_records(项目)':26} rows={remaining}")
    conn.close()

    if args.clear_rag:
        ok = clear_rag()
        print(f"  RAG 向量库: {'已清空 data/chroma' if ok else '无 data/chroma，跳过'}")

    print("\n[✓] 项目数据清理完成，系统配置已保留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

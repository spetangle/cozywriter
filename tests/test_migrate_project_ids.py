"""项目 ID int → hex 迁移回归：保留旧列、补 ORM 新列、保留外键。

用独立临时 SQLite 库（DATABASE_URL 在 import config 前重定向）。
运行：python tests/test_migrate_project_ids.py
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_migrate_project_ids.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def seed_old_schema():
    conn = sqlite3.connect(_TMP_DB)
    conn.executescript("""
    CREATE TABLE projects (
      id INTEGER PRIMARY KEY,
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
    );
    CREATE TABLE chapters (
      id INTEGER PRIMARY KEY,
      project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      title VARCHAR(255),
      "order" INTEGER DEFAULT 0,
      content TEXT DEFAULT '',
      word_count INTEGER DEFAULT 0
    );
    INSERT INTO projects (id, title) VALUES (1, '旧书');
    INSERT INTO chapters (id, project_id, title, "order") VALUES (1, 1, '第1章', 0);
    """)
    conn.commit()
    conn.close()


def main():
    seed_old_schema()

    from storage.database import engine
    from storage.migrations.migrate_project_ids import migrate_project_ids

    print("\n[1] 执行迁移")
    result = migrate_project_ids(engine)
    check("迁移执行成功", result.get("migrated") is True, str(result))

    conn = sqlite3.connect(_TMP_DB)
    print("\n[2] projects 新列与数据")
    project_cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)")]
    check("补上 project_type", "project_type" in project_cols, str(project_cols))
    check("补上 script_format", "script_format" in project_cols, str(project_cols))
    check("补上 script_episode_count", "script_episode_count" in project_cols, str(project_cols))
    new_pid = conn.execute("SELECT id FROM projects").fetchone()[0]
    check("id 变为 8 位 hex", isinstance(new_pid, str) and len(new_pid) == 8, repr(new_pid))

    print("\n[3] 子表数据与外键")
    chapter_pid = conn.execute("SELECT project_id FROM chapters").fetchone()[0]
    check("子表 project_id 同步为新 id", chapter_pid == new_pid, f"{chapter_pid} != {new_pid}")
    fks = conn.execute("PRAGMA foreign_key_list(chapters)").fetchall()
    check("外键声明保留", any(fk[2] == "projects" for fk in fks), str(fks))
    check("ON DELETE CASCADE 保留", any(fk[6] == "CASCADE" for fk in fks), str(fks))
    conn.close()

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

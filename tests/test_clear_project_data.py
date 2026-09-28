"""旧库项目数据清理工具回归测试。

验证 tools/clear_project_data.py：
- 清除 projects 及其关联数据、问卷
- 保留 providers / system_settings / llm_hyperparam_presets / custom_genres
- 只清除项目维度的 token 用量，保留全局用量

运行：python tests/test_clear_project_data.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "clear_project_data.py")

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def seed(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
    CREATE TABLE projects (id TEXT PRIMARY KEY, title TEXT);
    CREATE TABLE characters (id INTEGER PRIMARY KEY, project_id TEXT, name TEXT);
    CREATE TABLE chapters (id INTEGER PRIMARY KEY, project_id TEXT, title TEXT);
    CREATE TABLE chapter_outlines (id INTEGER PRIMARY KEY, chapter_id INTEGER, key_content TEXT);
    CREATE TABLE creative_questionnaires (id INTEGER PRIMARY KEY, title TEXT);
    CREATE TABLE llm_usage_records (id INTEGER PRIMARY KEY, project_id TEXT, provider TEXT);
    CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT, api_key TEXT, is_default INTEGER);
    CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE llm_hyperparam_presets (id INTEGER PRIMARY KEY, provider TEXT);
    CREATE TABLE custom_genres (id INTEGER PRIMARY KEY, name TEXT, is_system INTEGER);

    INSERT INTO projects VALUES ('p1', '旧书');
    INSERT INTO characters VALUES (1, 'p1', '角色A');
    INSERT INTO chapters VALUES (1, 'p1', '第1章');
    INSERT INTO chapter_outlines VALUES (1, 1, '细纲');
    INSERT INTO creative_questionnaires VALUES (1, '问卷');
    INSERT INTO llm_usage_records VALUES (1, 'p1', 'opencode');
    INSERT INTO llm_usage_records VALUES (2, NULL, 'opencode');
    INSERT INTO providers VALUES ('opencode', 'OpenCode Go', 'key', 1);
    INSERT INTO system_settings VALUES ('default_llm_provider', 'opencode');
    INSERT INTO llm_hyperparam_presets VALUES (1, 'opencode');
    INSERT INTO custom_genres VALUES (1, '自定题材', 0);
    """)
    conn.commit()
    conn.close()


def count(db_path, table):
    conn = sqlite3.connect(db_path)
    n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    conn.close()
    return n


def main():
    tmp = tempfile.mkdtemp(prefix="cozywriter_clear_test_")
    db = os.path.join(tmp, "old.db")
    seed(db)

    print("\n[1] 清理前")
    check("项目 1 个", count(db, "projects") == 1)
    check("角色 1 个", count(db, "characters") == 1)
    check("全局用量 1 条", count(db, "llm_usage_records") == 2)

    print("\n[2] dry-run 不应修改")
    r = subprocess.run([sys.executable, TOOL, "--db", db, "--dry-run"],
                       capture_output=True, text=True)
    check("dry-run 退出码 0", r.returncode == 0, r.stderr[-200:])
    check("dry-run 后项目仍在", count(db, "projects") == 1)

    print("\n[3] 执行清理")
    r = subprocess.run([sys.executable, TOOL, "--db", db, "--yes"],
                       capture_output=True, text=True)
    check("清理退出码 0", r.returncode == 0, r.stderr[-300:])
    check("projects 清空", count(db, "projects") == 0)
    check("characters 清空", count(db, "characters") == 0)
    check("chapters 清空", count(db, "chapters") == 0)
    check("chapter_outlines 清空", count(db, "chapter_outlines") == 0)
    check("creative_questionnaires 清空", count(db, "creative_questionnaires") == 0)

    print("\n[4] 系统配置保留")
    check("providers 保留", count(db, "providers") == 1)
    check("system_settings 保留", count(db, "system_settings") == 1)
    check("llm_hyperparam_presets 保留", count(db, "llm_hyperparam_presets") == 1)
    check("custom_genres 保留", count(db, "custom_genres") == 1)

    print("\n[5] token 用量：项目维度清除，全局保留")
    conn = sqlite3.connect(db)
    remaining = conn.execute("SELECT id, project_id FROM llm_usage_records").fetchall()
    conn.close()
    check("只剩全局 1 条", remaining == [(2, None)], str(remaining))

    print("\n[6] 自动备份已生成")
    backup_dir = os.path.join(tmp, "backups")
    backups = os.listdir(backup_dir) if os.path.isdir(backup_dir) else []
    check("backups 目录有备份", any(b.startswith("cozywriter_before_clear_") for b in backups), str(backups))

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())

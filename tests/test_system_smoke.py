"""系统级 API 冒烟测试：覆盖项目/章节/角色/世界观/主题/剧情点/灵感/问卷/剧本/导出等主链路。

用独立临时 SQLite（DATABASE_URL 在 import config 前重定向），stub 掉异步任务提交和
RAG 写索引，避免真实 LLM 调用与 embedding 模型下载。

运行：python tests/test_system_smoke.py
"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_system_smoke.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import api.tasks as tasks_mod  # noqa: E402
import api.routes.characters as chars_mod  # noqa: E402
import api.routes.worldbuilding as world_mod  # noqa: E402
from storage.database import engine, SessionLocal  # noqa: E402
from storage.models import Base  # noqa: E402

client = TestClient(main.app)

_failures = []
_checks = {"pass": 0, "fail": 0}


def check(name, cond, detail=""):
    ok = bool(cond)
    _checks["pass" if ok else "fail"] += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        _failures.append(name)
    return ok


class _DummyKB:
    def __getattr__(self, _name):
        return lambda *a, **kw: None


def _dummy_submit_llm_task(**kwargs):
    return types.SimpleNamespace(id="smoke-task-1", status="pending", progress=0)


def _install_stubs():
    tasks_mod.submit_llm_task = _dummy_submit_llm_task
    chars_mod.KnowledgeBase = _DummyKB
    world_mod.KnowledgeBase = _DummyKB


def _create_project(project_type="novel", title="冒烟项目"):
    if project_type == "script":
        payload = {
            "title": title,
            "project_type": "script",
            "genre": "悬疑",
            "description": "剧本冒烟",
            "total_scenes": 2,
            "script_format": "movie",
            "auto_commit": False,
        }
    else:
        payload = {
            "title": title,
            "project_type": "novel",
            "chapter_word_count": 3,
            "genre": "玄幻",
            "description": "小说冒烟",
            "total_chapters": 12,
            "auto_commit": False,
        }
    r = client.post("/api/projects", json=payload)
    check(f"创建 {project_type} 项目", r.status_code == 200, r.text[:200])
    data = r.json()
    check(f"返回 project_id 与 run_id", data.get("project_id") and data.get("run_id"), str(data)[:200])
    return data.get("project_id")


def test_health_and_config():
    print("\n[1] 初始化 / 配置 / 模型 / 题材")
    r = client.get("/api/init/status")
    check("GET /api/init/status 200", r.status_code == 200, r.text[:120])
    r = client.get("/api/config/status")
    check("GET /api/config/status 200", r.status_code == 200, r.text[:120])
    r = client.get("/api/models/status")
    check("GET /api/models/status 200", r.status_code == 200, r.text[:120])
    r = client.get("/api/providers")
    check("GET /api/providers 200", r.status_code == 200, r.text[:120])

    r = client.get("/api/genres")
    check("GET /api/genres 200", r.status_code == 200 and len(r.json()) >= 10, r.text[:160])
    r = client.post("/api/genres", json={"name": "冒烟自定义题材"})
    check("POST /api/genres 201/200", r.status_code in (200, 201), r.text[:160])
    gid = r.json().get("id") if r.status_code in (200, 201) else None
    if gid:
        check("DELETE 自定义题材", client.delete(f"/api/genres/{gid}").status_code == 200)


def test_project_crud():
    print("\n[2] 项目 CRUD / 必填校验")
    r = client.post("/api/projects", json={"title": "缺字段"})
    check("缺必填返回 missing_required", r.status_code == 200 and r.json().get("status") == "missing_required", r.text[:200])

    pid = _create_project("novel", "冒烟小说")
    check("GET /api/projects 列表包含新项目",
          any(p["id"] == pid for p in client.get("/api/projects").json()))
    r = client.get(f"/api/projects/{pid}")
    check("GET 项目详情 200", r.status_code == 200 and r.json()["title"] == "冒烟小说")
    r = client.put(f"/api/projects/{pid}", json={"title": "冒烟小说改", "chapter_word_count": 4})
    check("PUT 项目更新 200", r.status_code == 200 and r.json()["title"] == "冒烟小说改"
          and r.json()["target_word_count"] == 4000, r.text[:200])
    r = client.get(f"/api/projects/{pid}/bootstrap-status")
    check("bootstrap-status 200/404", r.status_code in (200, 404), r.text[:160])
    return pid


def test_novel_resources(pid):
    print("\n[3] 角色 / 世界观 / 主题 / 伏笔 / 剧情点")
    r = client.post(f"/api/projects/{pid}/characters", json={
        "name": "林墨白", "role": "主角", "description": "剑客",
        "profile": {"personality": "冷静"}, "appearance": {"height": "180cm"},
    })
    check("POST 角色 200", r.status_code == 200, r.text[:160])
    cid = r.json().get("id")
    r = client.put(f"/api/projects/{pid}/characters/{cid}", json={"description": "青年剑客"})
    check("PUT 角色 200", r.status_code == 200 and r.json()["description"] == "青年剑客")
    r = client.get(f"/api/projects/{pid}/characters")
    check("GET 角色列表", r.status_code == 200 and len(r.json()) == 1)
    r = client.get(f"/api/projects/{pid}/characters/{cid}/references")
    check("GET 角色引用 200", r.status_code == 200, r.text[:120])

    r = client.post(f"/api/projects/{pid}/worldbuilding", json={
        "category": "地理", "title": "荒原", "content": "黄沙", "tags": ["a"],
    })
    check("POST 世界观 200", r.status_code == 200, r.text[:160])
    wid = r.json().get("id")
    r = client.put(f"/api/projects/{pid}/worldbuilding/{wid}", json={"content": "无尽黄沙"})
    check("PUT 世界观 200", r.status_code == 200 and r.json()["content"] == "无尽黄沙")

    r = client.post(f"/api/projects/{pid}/themes", json={
        "theme_type": "core_theme", "title": "复仇", "description": "黑暗",
    })
    check("POST 主题 200", r.status_code == 200, r.text[:160])
    tid = r.json().get("id")
    check("GET 主题列表", len(client.get(f"/api/projects/{pid}/themes").json()) == 1)
    check("PUT 主题 200", client.put(f"/api/projects/{pid}/themes/{tid}", json={"title": "复仇与救赎"}).status_code == 200)
    check("DELETE 主题 200", client.delete(f"/api/projects/{pid}/themes/{tid}").status_code == 200)

    r = client.post(f"/api/projects/{pid}/foreshadowings", json={"title": "断剑", "content": "缺口"})
    check("POST 伏笔 200", r.status_code == 200, r.text[:160])
    fid = r.json().get("id")
    check("DELETE 伏笔 200", client.delete(f"/api/projects/{pid}/foreshadowings/{fid}").status_code == 200)

    r = client.post(f"/api/projects/{pid}/plot-points", json={"title": "相遇", "description": "酒馆"})
    check("POST 剧情点 201/200", r.status_code in (200, 201), r.text[:160])
    ppid = r.json().get("id")
    check("GET 剧情点列表", client.get(f"/api/projects/{pid}/plot-points").status_code == 200)
    if ppid:
        check("PUT 剧情点 200", client.put(f"/api/projects/{pid}/plot-points/{ppid}", json={"status": "developing"}).status_code == 200)
        check("DELETE 剧情点 200", client.delete(f"/api/projects/{pid}/plot-points/{ppid}").status_code == 200)


def test_chapters_and_export(pid):
    print("\n[4] 章节 / 细纲 / 项目大纲 / 导出")
    r = client.post(f"/api/projects/{pid}/outline", json={
        "outline_text": "整体梗概", "structure": {"acts": [{"name": "第一幕"}]},
        "plot_lines": [{"title": "主线", "description": "复仇", "from_chapter": 1, "to_chapter": 12}],
    })
    check("POST 项目大纲 200", r.status_code == 200, r.text[:160])
    r = client.put(f"/api/projects/{pid}/outline", json={"pacing_notes": "前紧后松"})
    check("PUT 项目大纲 200", r.status_code == 200, r.text[:160])

    r = client.post(f"/api/projects/{pid}/chapters", json={
        "title": "第1章", "order": 0, "content": "正文" * 80, "synopsis": "开局",
    })
    check("POST 章节 200", r.status_code == 200, r.text[:200])
    chap = r.json()
    cid = chap.get("id")
    check("章节字数计算", chap.get("word_count", 0) > 0, str(chap.get("word_count")))
    check("GET 章节列表", len(client.get(f"/api/projects/{pid}/chapters").json()) == 1)
    check("GET 章节详情", client.get(f"/api/projects/{pid}/chapters/{cid}").status_code == 200)
    check("PUT 章节 200", client.put(f"/api/projects/{pid}/chapters/{cid}", json={"title": "第1章 改"}).status_code == 200)
    check("GET 章节版本", client.get(f"/api/projects/{pid}/chapters/{cid}/versions").status_code == 200)
    check("GET 章节 prep-info 200/404",
          client.get(f"/api/projects/{pid}/chapters/{cid}/prep-info").status_code in (200, 404))

    r = client.post(f"/api/projects/{pid}/chapters/{cid}/outline", json={
        "chapter_id": cid, "key_content": "主角登场", "chapter_position": "开局",
    })
    check("POST 章节细纲 200", r.status_code == 200, r.text[:160])
    check("GET 章节细纲 200", client.get(f"/api/projects/{pid}/chapters/{cid}/outline").status_code == 200)

    r = client.post("/api/export/chapters", json={
        "project_id": pid, "chapter_ids": [cid], "format": "txt",
    })
    check("POST 导出 TXT 200", r.status_code == 200 and len(r.content) > 0, r.text[:160])
    r = client.post("/api/export/chapters", json={
        "project_id": pid, "chapter_ids": [cid], "format": "markdown", "save_individual": True,
    })
    check("POST 导出 Markdown/ZIP 200", r.status_code == 200 and r.content[:2] == b"PK", str(r.status_code))
    return cid


def test_inspirations_and_questionnaire():
    print("\n[5] 灵感 / 问卷")
    r = client.post("/api/inspirations", json={"title": "灵感A", "content": "一个脑洞", "tags": ["cool"], "source": "脑洞"})
    check("POST 灵感 200", r.status_code == 200, r.text[:160])
    iid = r.json().get("id")
    check("GET 灵感列表", client.get("/api/inspirations").status_code == 200)
    check("GET 灵感标签", client.get("/api/inspirations/tags").status_code == 200)
    check("PUT 灵感 200", client.put(f"/api/inspirations/{iid}", json={"title": "灵感A改"}).status_code == 200)
    check("DELETE 灵感 200", client.delete(f"/api/inspirations/{iid}").status_code == 200)

    r = client.post("/api/questionnaires", json={"title": "冒烟问卷", "answers": {"genre": "玄幻"}})
    check("POST 问卷 200", r.status_code == 200, r.text[:160])
    qid = r.json().get("id")
    check("GET 问卷列表", client.get("/api/questionnaires").status_code == 200)
    check("GET 问卷 questions", client.get("/api/questionnaires/questions").status_code == 200)
    check("GET 问卷 step-questions", client.get("/api/questionnaires/step-questions").status_code == 200)
    check("GET current-step 200", client.get(f"/api/questionnaires/{qid}/current-step").status_code == 200)
    check("POST answer-step 200", client.post(f"/api/questionnaires/{qid}/answer-step",
                                               json={"question_id": "genre", "answer": "玄幻"}).status_code == 200)
    check("POST prev-step 200", client.post(f"/api/questionnaires/{qid}/prev-step").status_code == 200)
    check("PUT 问卷 200", client.put(f"/api/questionnaires/{qid}", json={"answers": {"genre": "科幻"}}).status_code == 200)
    check("DELETE 问卷 200", client.delete(f"/api/questionnaires/{qid}").status_code == 200)


def test_script_subsystem():
    print("\n[6] 剧本：场景 / 分镜 / 道具")
    pid = _create_project("script", "冒烟剧本")
    r = client.post(f"/api/projects/{pid}/screenplays", json={
        "title": "酒馆相遇", "scene_number": 1, "location": "破旧酒馆",
        "characters_present": ["林墨白"], "synopsis": "相遇",
    })
    check("POST 场景 200", r.status_code == 200, r.text[:160])
    sid = r.json().get("id")
    check("GET 场景列表", len(client.get(f"/api/projects/{pid}/screenplays").json()) == 1)
    check("PUT 场景 200", client.put(f"/api/projects/{pid}/screenplays/{sid}", json={"content": "正文"}).status_code == 200)

    r = client.post(f"/api/projects/{pid}/screenplays/{sid}/storyboards", json={
        "shot_number": 1, "shot_type": "全景", "visual_description": "酒馆内景",
    })
    check("POST 分镜 200", r.status_code == 200, r.text[:160])
    sbid = r.json().get("id")
    check("分镜回填场景地点", r.json().get("location") == "破旧酒馆", str(r.json().get("location")))
    check("GET 项目分镜列表", len(client.get(f"/api/projects/{pid}/storyboards").json()) == 1)
    check("PUT 分镜 200", client.put(f"/api/projects/{pid}/storyboards/{sbid}", json={"shot_type": "特写"}).status_code == 200)

    r = client.post(f"/api/projects/{pid}/properties", json={
        "name": "青冥剑", "type": "武器", "description": "祖传长剑",
    })
    check("POST 道具 200", r.status_code == 200, r.text[:160])
    prop_id = r.json().get("id")
    r = client.post(f"/api/projects/{pid}/properties/{prop_id}/history", json={"action": "获得", "description": "师父赠剑"})
    check("POST 道具流转 200", r.status_code == 200 and len(r.json()["history"]) == 1, r.text[:160])
    check("GET 道具列表", len(client.get(f"/api/projects/{pid}/properties").json()) == 1)
    check("DELETE 分镜 200", client.delete(f"/api/projects/{pid}/storyboards/{sbid}").status_code == 200)
    check("DELETE 道具 200", client.delete(f"/api/projects/{pid}/properties/{prop_id}").status_code == 200)
    check("DELETE 场景 200", client.delete(f"/api/projects/{pid}/screenplays/{sid}").status_code == 200)
    return pid


def test_workflow_and_usage(pid):
    print("\n[7] 工作流 / Token 用量 / 任务")
    check("GET workflow latest 200", client.get(f"/api/workflow/project/{pid}/latest").status_code == 200)
    check("GET bootstrap-data 200", client.get(f"/api/workflow/project/{pid}/bootstrap-data").status_code == 200)
    check("GET token-usage project 200", client.get(f"/api/token-usage/project/{pid}").status_code == 200)
    check("GET token-usage recent 200", client.get(f"/api/token-usage/project/{pid}/recent").status_code == 200)
    check("GET tasks all 200", client.get("/api/tasks/all").status_code == 200)


def test_cleanup(pid):
    print("\n[8] 项目删除")
    r = client.delete(f"/api/projects/{pid}")
    check("DELETE 项目 200", r.status_code == 200, r.text[:160])
    check("删除后 404", client.get(f"/api/projects/{pid}").status_code == 404)


def main():
    _install_stubs()
    Base.metadata.create_all(bind=engine)
    try:
        test_health_and_config()
        pid = test_project_crud()
        test_novel_resources(pid)
        test_chapters_and_export(pid)
        test_inspirations_and_questionnaire()
        test_script_subsystem()
        test_workflow_and_usage(pid)
        test_cleanup(pid)
    finally:
        db = SessionLocal()
        db.close()

    print(f"\n结果：{_checks['pass']} passed, {_checks['fail']} failed")
    if _failures:
        print("FAILED:", _failures)
    else:
        print("ALL PASS")
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    engine.dispose()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

"""剧本相关 API 集成测试：分镜 CRUD、道具流转历史、角色外貌生成入口。

用独立临时 SQLite 库（DATABASE_URL 在 import config 前重定向），不碰 data/cozywriter.db。

运行：python tests/test_script_api.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_script_api.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from storage.database import engine, SessionLocal  # noqa: E402
from storage.models import Base, Project, Character  # noqa: E402
from storage.models.screenplay import Screenplay, Storyboard, Property  # noqa: E402

client = TestClient(main.app)
PID = "apitest0001"

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(Project(id=PID, title="测试剧本", description="少年剑客复仇",
                   project_type="script", script_format="movie"))
    db.add(Character(id=1, project_id=PID, name="林墨白", role="主角",
                     description="青年剑客", appearance={"height": "180cm"}))
    db.add(Screenplay(id=1, project_id=PID, title="酒馆相遇", scene_number=1,
                      location="破旧酒馆", content="（正文）", characters_present=["林墨白"]))
    db.commit()
    db.close()


def main_test():
    seed()

    # characters 的写接口会触发 RAG 索引（可能加载 embedding 模型，慢且与本机缓存状态相关）。
    # 这里 stub 掉，让测试快速且确定；RAG 行为不在本测试范围内。
    import api.routes.characters as chars_mod

    class _DummyKB:
        def add_character(self, *a, **kw):
            pass

        def update_character(self, *a, **kw):
            pass

        def delete_character(self, *a, **kw):
            pass

    chars_mod.KnowledgeBase = _DummyKB

    print("\n[1] 分镜：项目级列表")
    r = client.get(f"/api/projects/{PID}/storyboards")
    check("GET /storyboards 200", r.status_code == 200, r.text[:120])
    check("初始为空", r.json() == [])

    r = client.get("/api/projects/nonexistent/storyboards")
    check("未知项目 404", r.status_code == 404)

    print("\n[2] 分镜：手动新增")
    r = client.post(f"/api/projects/{PID}/screenplays/1/storyboards", json={
        "shot_number": 1, "shot_type": "全景", "camera_angle": "平视",
        "camera_movement": "推", "duration_estimate": "5-10秒",
        "visual_description": "酒馆内景，众人喧闹", "dialogue": "客官打尖还是住店？",
    })
    check("POST 创建 200", r.status_code == 200, r.text[:160])
    body = r.json()
    sb_id = body.get("id")
    check("返回完整字段", body.get("visual_description") == "酒馆内景，众人喧闹"
          and body.get("camera_movement") == "推")
    check("location 从场景回填", body.get("location") == "破旧酒馆", str(body.get("location")))
    check("characters 从场景回填", body.get("characters") == ["林墨白"], str(body.get("characters")))

    r = client.post(f"/api/projects/{PID}/screenplays/1/storyboards", json={"shot_number": 2})
    sb2_id = r.json().get("id")
    check("第二个分镜创建成功", r.status_code == 200 and sb2_id)

    r = client.post(f"/api/projects/{PID}/screenplays/999/storyboards", json={"shot_number": 1})
    check("未知场景 404", r.status_code == 404)

    print("\n[3] 分镜：列表 / 过滤 / 排序")
    r = client.get(f"/api/projects/{PID}/storyboards")
    check("项目级列出 2 条", len(r.json()) == 2, str(len(r.json())))
    check("按镜号排序", [s["shot_number"] for s in r.json()] == [1, 2])

    r = client.get(f"/api/projects/{PID}/storyboards?screenplay_id=1")
    check("按场景过滤生效", len(r.json()) == 2)
    r = client.get(f"/api/projects/{PID}/storyboards?screenplay_id=999")
    check("过滤到不存在的场景返回空", r.json() == [])

    r = client.get(f"/api/projects/{PID}/screenplays/1/storyboards")
    check("场景级列表仍可用（screenplays.py）", r.status_code == 200 and len(r.json()) == 2)

    print("\n[4] 分镜：更新")
    r = client.put(f"/api/projects/{PID}/storyboards/{sb_id}", json={
        "shot_type": "特写", "visual_description": "剑柄上的缺口", "notes": "补拍",
    })
    check("PUT 200", r.status_code == 200, r.text[:160])
    body = r.json()
    check("部分更新：改动字段生效", body["shot_type"] == "特写"
          and body["visual_description"] == "剑柄上的缺口" and body["notes"] == "补拍")
    check("部分更新：未传字段保留", body["camera_movement"] == "推"
          and body["dialogue"] == "客官打尖还是住店？",
          f"movement={body['camera_movement']} dialogue={body['dialogue']!r}")

    r = client.put(f"/api/projects/{PID}/storyboards/{sb_id}", json={"characters": ["林墨白", "顾临风"]})
    check("characters(JSON列) 可更新", r.json()["characters"] == ["林墨白", "顾临风"])

    db = SessionLocal()
    persisted = db.query(Storyboard).filter(Storyboard.id == sb_id).first()
    check("更新确实落库", persisted.shot_type == "特写"
          and persisted.characters == ["林墨白", "顾临风"])
    db.close()

    r = client.put(f"/api/projects/{PID}/storyboards/999999", json={"shot_type": "特写"})
    check("更新未知分镜 404", r.status_code == 404)
    r = client.put("/api/projects/otherproject/storyboards/%d" % sb_id, json={"shot_type": "远景"})
    check("跨项目更新被拒（项目隔离）", r.status_code == 404)

    print("\n[5] 分镜：删除")
    r = client.delete(f"/api/projects/{PID}/storyboards/{sb2_id}")
    check("DELETE 200", r.status_code == 200)
    check("删除后剩 1 条", len(client.get(f"/api/projects/{PID}/storyboards").json()) == 1)
    r = client.delete(f"/api/projects/{PID}/storyboards/{sb2_id}")
    check("重复删除 404", r.status_code == 404)

    print("\n[6] 道具：流转历史追加（JSON 列变更检测）")
    r = client.post(f"/api/projects/{PID}/properties", json={
        "name": "青冥剑", "type": "武器", "description": "祖传长剑", "status": "完好",
    })
    check("创建道具", r.status_code == 200, r.text[:120])
    prop_id = r.json()["id"]

    for i, (action, desc) in enumerate([("获得", "师父赠剑"), ("使用", "酒馆出鞘"),
                                        ("损坏", "剑刃缺口"), ("转手", "交给顾临风")], 1):
        r = client.post(f"/api/projects/{PID}/properties/{prop_id}/history",
                        json={"action": action, "description": desc})
        check(f"追加第 {i} 条", r.status_code == 200 and len(r.json()["history"]) == i,
              r.text[:120])

    db = SessionLocal()
    db.expire_all()
    p = db.query(Property).filter(Property.id == prop_id).first()
    check("4 条历史全部落库（原地 append 的老写法会丢）",
          len(p.history) == 4 and [h["action"] for h in p.history]
          == ["获得", "使用", "损坏", "转手"], str(p.history))

    r = client.post(f"/api/projects/{PID}/properties/{prop_id}/history",
                    json={"action": "转手", "description": "归属变更",
                          "owner": "顾临风", "status": "失去"})
    check("追加时可同步 owner/status",
          r.json()["owner"] == "顾临风" and r.json()["status"] == "失去")
    db.close()

    r = client.post(f"/api/projects/{PID}/properties/999999/history", json={"action": "使用"})
    check("未知道具 404", r.status_code == 404)

    print("\n[7] 角色外貌生成入口（禁用任务执行，绝不触发真实 LLM 调用）")
    # 若 .env 里配了真实 provider，submit_llm_task 会真的发请求并产生费用。
    # 这里把执行器换成 no-op，只验证路由命中、入参校验与任务创建。
    import api.tasks as tasks_mod
    submitted = []
    orig_run = tasks_mod.run_task_async
    tasks_mod.run_task_async = lambda task_id, fn, *a, **kw: submitted.append(task_id)
    try:
        r = client.post(f"/api/projects/{PID}/characters/1/generate-appearance")
        check("POST generate-appearance 命中并返回 task_id",
              r.status_code == 200 and "task_id" in r.json(), r.text[:160])
        check("任务已提交但未执行", len(submitted) == 1, str(submitted))
        if r.status_code == 200:
            task_id = r.json()["task_id"]
            r2 = client.get(f"/api/tasks/{task_id}")
            check("任务可轮询", r2.status_code == 200 and "status" in r2.json(), r2.text[:120])

        r = client.post(f"/api/projects/{PID}/characters/999999/generate-appearance")
        check("未知角色 404", r.status_code == 404)
        check("未知角色不提交任务", len(submitted) == 1)
        r = client.post("/api/projects/nonexistent/characters/1/generate-appearance")
        check("未知项目 404", r.status_code == 404)
    finally:
        tasks_mod.run_task_async = orig_run

    print("\n[8] 外貌字段经 PUT 读写（面板保存路径）")
    appearance = {"height": "180cm", "build": "匀称", "clothing": "青衫", "other": "左眉有疤"}
    r = client.put(f"/api/projects/{PID}/characters/1", json={"appearance": appearance})
    check("PUT appearance 200", r.status_code == 200, r.text[:160])
    check("回读一致", r.json()["appearance"] == appearance)

    db = SessionLocal()
    c = db.query(Character).filter(Character.id == 1).first()
    check("appearance 落库", c.appearance == appearance)
    check("appearance_text 渲染为中文标签",
          "身高: 180cm" in c.appearance_text and "{" not in c.appearance_text,
          c.appearance_text)
    db.close()

    print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    code = main_test()
    engine.dispose()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

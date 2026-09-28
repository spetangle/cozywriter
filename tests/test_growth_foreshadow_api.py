"""角色成长 / 本章伏笔 / 角色关系图谱 / 相似小说 相关接口回归测试。

覆盖：
  1. character_growths 表随 init_db 建立
  2. GET /chapters/{id}/foreshadowings（本章埋设/回收/状态变化）
  3. GET /chapters/{id}/character-growth（优先 growth 表，回退 fingerprint）
  4. GET /characters/{id}/growth（成长时间线）
  5. GET /character-relations（关系图谱数据）
  6. llm.similar_novels 的信息拼接与 JSON 容错解析

运行：python tests/test_growth_foreshadow_api.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"

from storage.database import init_db, SessionLocal, engine  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

init_db()

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if (detail and not cond) else ''}")
    if not cond:
        failures.append(name)


print("[1] character_growths 表")
insp = inspect(engine)
check("表已创建", insp.has_table("character_growths"))
cols = {c["name"] for c in insp.get_columns("character_growths")} if insp.has_table("character_growths") else set()
check("关键列齐全", {"project_id", "character_id", "chapter_id", "status_after", "gains", "summary"} <= cols)

# ─── seed ───
from storage.models import (  # noqa: E402
    Project, Chapter, Character, CharacterRelation, Foreshadowing, CharacterGrowth,
)

PID = "gtest001"
db = SessionLocal()
db.add(Project(id=PID, title="成长测试", total_chapters=10, project_type="novel",
               target_word_count=3000, word_count_min=2700, word_count_max=3300))
ch = Chapter(project_id=PID, title="第1章", order=0, content="正文" * 50, word_count=100,
             fingerprint={"post_processing": {
                 "arc_updates": [{"character": "男主", "new_state": "得到地图"}],
                 "foreshadow_updates": [{"title": "神秘纸条", "new_status": "planted", "evidence": "桌上的纸条"}],
             }})
db.add(ch)
db.commit()
db.refresh(ch)

p = Character(project_id=PID, name="男主", role="主角", description="主角")
s = Character(project_id=PID, name="配角", role="配角", description="配角")
db.add_all([p, s])
db.commit()
db.refresh(p)
db.refresh(s)

db.add(CharacterRelation(project_id=PID, from_character_id=p.id, to_character_id=s.id,
                         relation_type="师徒", strength=7, status="developing"))
db.add(Foreshadowing(project_id=PID, title="神秘纸条", content="纸条内容", cycle="短伏笔",
                     plant_order=0, status="planted"))
db.add(Foreshadowing(project_id=PID, title="古老预言", content="预言内容", cycle="长伏笔",
                     plant_order=0, status="active"))
db.commit()

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
client = TestClient(main.app)

print("\n[2] 本章伏笔")
r = client.get(f"/api/projects/{PID}/chapters/{ch.id}/foreshadowings")
check("200", r.status_code == 200, str(r.status_code))
d = r.json()
check("本章埋设 2 条", len(d.get("planted_here", [])) == 2, str(len(d.get("planted_here", []))))
check("状态变化 1 条", len(d.get("updates", [])) == 1)
check("进行中 >= 2", len(d.get("active_pending", [])) >= 2)

print("\n[3] 本章角色成长（回退 fingerprint）")
r = client.get(f"/api/projects/{PID}/chapters/{ch.id}/character-growth")
check("200", r.status_code == 200)
items = r.json().get("items", [])
check("回退返回 1 条", len(items) == 1, str(items))
check("含主角标识", bool(items) and items[0].get("is_protagonist") is True)

print("\n[4] growth 表优先")
db.add(CharacterGrowth(project_id=PID, character_id=p.id, chapter_id=ch.id, chapter_order=0,
                       chapter_title="第1章", status_after="得到地图", gains="地图",
                       summary="主角得到地图", is_protagonist=True))
db.commit()
r = client.get(f"/api/projects/{PID}/chapters/{ch.id}/character-growth")
items = r.json().get("items", [])
check("growth 表命中", len(items) == 1 and items[0].get("source") == "auto")
check("收获字段", items[0].get("gains") == "地图")

print("\n[5] 角色成长时间线")
r = client.get(f"/api/projects/{PID}/characters/{p.id}/growth")
check("200", r.status_code == 200)
check("1 条记录", len(r.json().get("items", [])) == 1)
r = client.get(f"/api/projects/{PID}/characters/999999/growth")
check("不存在角色 404", r.status_code == 404)

print("\n[6] 角色关系")
r = client.get(f"/api/projects/{PID}/character-relations")
check("200 且 1 条", r.status_code == 200 and len(r.json()) == 1)

print("\n[7] 相似小说工具函数")
from llm.similar_novels import build_novel_info, _parse_json  # noqa: E402
info = build_novel_info({"novel_title": "测试书", "genre": "玄幻", "theme": ["成长", "救赎"]})
check("信息包含书名", "测试书" in info)
check("列表字段拼接", "成长、救赎" in info)
data = _parse_json('```json\n{"verdict": "novel", "similar_works": []}\n```')
check("解析带围栏 JSON", data.get("verdict") == "novel")
data = _parse_json('前言 {"verdict": "some_overlap"} 后记')
check("解析夹带文本 JSON", data.get("verdict") == "some_overlap")

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {', '.join(failures)}"))
try:
    os.unlink(_tmp_db.name)
except OSError:
    pass
sys.exit(1 if failures else 0)

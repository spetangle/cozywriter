"""剧本后处理 (_apply_post_process) 与角色外貌渲染的回归测试。

覆盖三个曾经静默失效的路径：
  1. 角色弧光更新按不存在的 CharacterArc.character_name / arc_description 查询，
     AttributeError 被 try/except 吞掉 → 弧光永远不更新；
  2. 外貌变化写进 description 文本，appearance / appearance_changes 两个专用
     JSON 列从未被写入；
  3. Property.history 是普通 JSON 列（未包 Mutable），原地 append 后赋回同一
     对象，SQLAlchemy 检测不到变更 → 流转历史永不落库。

无 pytest 依赖，直接运行：
    python tests/test_script_post_process.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须在 import config / storage 之前重定向数据库，避免碰真实的 data/cozywriter.db
_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_postprocess.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from storage.database import engine, SessionLocal  # noqa: E402
from storage.models import Base, Project, Character, CharacterArc  # noqa: E402
from storage.models.screenplay import Property  # noqa: E402
from llm.script_pipeline import (  # noqa: E402
    _apply_post_process,
    storyboard_density_prompt,
)

PROJECT_ID = "testproj0001"

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def seed(db):
    db.add(Project(id=PROJECT_ID, title="测试剧本", project_type="script",
                   script_format="movie"))
    db.add(Character(id=1, project_id=PROJECT_ID, name="林墨白", role="主角",
                     description="青年剑客",
                     appearance={"height": "180cm", "hair": "墨色长发"}))
    db.add(Character(id=2, project_id=PROJECT_ID, name="顾临风", role="反派",
                     description="黑衣楼主", appearance={}))
    db.add(Property(id=1, project_id=PROJECT_ID, name="青冥剑", type="武器",
                    description="祖传长剑", status="完好", history=[]))
    db.commit()


PP_RESULT = {
    "appearance_changes": [
        {
            "character_name": "林墨白",
            "has_change": True,
            "change_description": "左臂被划开一道伤口，衣袖染血",
            "change_reason": "与顾临风交手",
            "before": "青衫完好",
            "after": "青衫左袖破损带血",
            "new_appearance": {"clothing": "青衫左袖破损", "other": "左臂缠布带"},
        },
        # has_change=False 必须被忽略
        {"character_name": "顾临风", "has_change": False,
         "change_description": "不应写入"},
        # 未知角色名不应炸掉整批
        {"character_name": "不存在的人", "has_change": True,
         "change_description": "孤儿记录"},
    ],
    "arc_updates": [
        {"character_name": "林墨白", "arc_progress": "开始质疑师门",
         "new_state": "动摇"},
        {"character_name": "不存在的人", "arc_progress": "x", "new_state": "y"},
    ],
    "property_changes": [
        {"property_name": "青冥剑", "action": "使用", "description": "首次出鞘"},
        {"property_name": "玉佩", "action": "获得", "description": "母亲遗物"},
    ],
}


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)

        print("\n[1] 首次后处理")
        _apply_post_process(db, PROJECT_ID, PP_RESULT, screenplay_id=101)
        db.expire_all()  # 强制从库里重读，确认真的落盘了

        lin = db.query(Character).filter(Character.name == "林墨白").first()
        gu = db.query(Character).filter(Character.name == "顾临风").first()

        check("appearance 合并了新字段且保留旧字段",
              lin.appearance.get("clothing") == "青衫左袖破损"
              and lin.appearance.get("other") == "左臂缠布带"
              and lin.appearance.get("height") == "180cm"
              and lin.appearance.get("hair") == "墨色长发",
              f"got={lin.appearance}")

        check("appearance_changes 落库且带 scene_id",
              isinstance(lin.appearance_changes, list)
              and len(lin.appearance_changes) == 1
              and lin.appearance_changes[0]["scene_id"] == 101
              and "伤口" in lin.appearance_changes[0]["description"],
              f"got={lin.appearance_changes}")

        check("has_change=False 的角色未被写入",
              not gu.appearance and not gu.appearance_changes,
              f"appearance={gu.appearance} changes={gu.appearance_changes}")

        check("外貌变化不再污染 description",
              lin.description == "青年剑客", f"got={lin.description!r}")

        arcs = db.query(CharacterArc).filter(
            CharacterArc.project_id == PROJECT_ID).all()
        check("弧光按 character_id 建档（含 arc_type 非空约束）",
              len(arcs) == 1 and arcs[0].character_id == 1
              and arcs[0].arc_type == "成长"
              and arcs[0].current_state == "动摇"
              and arcs[0].key_behavior == "开始质疑师门",
              f"got={[(a.character_id, a.arc_type, a.current_state, a.key_behavior) for a in arcs]}")

        sword = db.query(Property).filter(Property.name == "青冥剑").first()
        check("已有道具的 history 首次落库",
              len(sword.history or []) == 1
              and sword.history[0]["action"] == "使用",
              f"got={sword.history}")

        jade = db.query(Property).filter(Property.name == "玉佩").first()
        check("新道具被创建", jade is not None and jade.status == "获得")

        print("\n[2] 第二次后处理（验证 JSON 列可重复追加）")
        _apply_post_process(db, PROJECT_ID, {
            "appearance_changes": [{
                "character_name": "林墨白", "has_change": True,
                "change_description": "换上白衣", "change_reason": "伤愈",
                "before": "青衫破损", "after": "白衣",
                "new_appearance": {"clothing": "白衣"},
            }],
            "arc_updates": [{
                "character_name": "林墨白",
                "arc_progress": "决意离开师门", "new_state": "决断",
            }],
            "property_changes": [{
                "property_name": "青冥剑", "action": "损坏", "description": "剑刃缺口",
            }],
        }, screenplay_id=102)
        db.expire_all()

        lin = db.query(Character).filter(Character.name == "林墨白").first()
        check("appearance_changes 累积到 2 条且各自带 scene_id",
              len(lin.appearance_changes) == 2
              and [c["scene_id"] for c in lin.appearance_changes] == [101, 102],
              f"got={[c['scene_id'] for c in lin.appearance_changes]}")

        check("appearance 字段被覆盖更新",
              lin.appearance.get("clothing") == "白衣"
              and lin.appearance.get("height") == "180cm",
              f"got={lin.appearance}")

        arc = db.query(CharacterArc).filter(CharacterArc.character_id == 1).first()
        check("已有弧光被更新而非新建",
              db.query(CharacterArc).filter(
                  CharacterArc.project_id == PROJECT_ID).count() == 1
              and arc.current_state == "决断"
              and arc.key_behavior == "决意离开师门",
              f"got={arc.current_state}/{arc.key_behavior}")

        sword = db.query(Property).filter(Property.name == "青冥剑").first()
        check("history 累积到 2 条（原地 append 的老写法会停在 1 条）",
              len(sword.history) == 2
              and [h["action"] for h in sword.history] == ["使用", "损坏"],
              f"got={sword.history}")
        check("道具状态随『损坏』更新", sword.status == "损坏", f"got={sword.status}")

        print("\n[3] appearance_text 渲染（不再输出 dict repr）")
        text = lin.appearance_text
        check("输出中文标签而非字典字面量",
              "{" not in text and "'" not in text and "身高: 180cm" in text,
              f"got={text!r}")
        check("profile_text 也使用渲染后的外貌",
              "外貌: " in lin.profile_text and "{" not in lin.profile_text.split("外貌: ")[1],
              f"got={lin.profile_text!r}")

        empty = Character(name="x", appearance={})
        check("空外貌返回空串（触发 description 回退）", empty.appearance_text == "")
        legacy = Character(name="x", appearance="一身白衣")
        check("字符串型外貌向后兼容", legacy.appearance_text == "一身白衣")

        print("\n[4] 分镜密度映射")
        check("coarse/standard/fine 各自映射",
              storyboard_density_prompt("coarse").startswith("粗略")
              and storyboard_density_prompt("fine").startswith("精细")
              and storyboard_density_prompt("standard").startswith("标准"))
        check("None 与未知值回退 standard",
              storyboard_density_prompt(None) == storyboard_density_prompt("standard")
              and storyboard_density_prompt("bogus") == storyboard_density_prompt("standard"))

        print("\n[5] 非法输入不抛异常")
        try:
            _apply_post_process(db, PROJECT_ID, "不是字典")
            _apply_post_process(db, PROJECT_ID, {"appearance_changes": ["字符串项", None],
                                                 "arc_updates": [None],
                                                 "property_changes": [{}]})
            _apply_post_process(db, PROJECT_ID, {"appearance_changes": [
                {"character_name": "林墨白", "has_change": True,
                 "new_appearance": "不是字典"}]})
            check("脏数据被安全跳过", True)
        except Exception as e:
            check("脏数据被安全跳过", False, f"raised {type(e).__name__}: {e}")
    finally:
        db.close()

    print("\n" + ("ALL PASS" if not _failures
                  else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    engine.dispose()  # 释放 SQLite 句柄，否则 Windows 下删不掉临时库
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

"""剧本 bootstrap 回归测试：planner 类型分支、locked 构造、script commit、JSON 兜底。

用独立临时 SQLite 库（DATABASE_URL 在 import config 前重定向），不碰 data/cozywriter.db。
commit 里会调用 RAG 重建索引，测试把 llm.chapter_pipeline 替换成 no-op，避免加载
embedding 模型。

运行：python tests/test_script_bootstrap.py
"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_script_bootstrap.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

# commit_bootstrap 成功后会调用 chapter_pipeline.reindex_project_rag；这里只测
# bootstrap 落库，stub 掉 RAG，避免首次下载 embedding 模型。
_FAKE_PIPELINE = types.ModuleType("llm.chapter_pipeline")
_FAKE_PIPELINE.reindex_project_rag = lambda *a, **kw: None
_FAKE_PIPELINE._find_existing_character = lambda *a, **kw: None
sys.modules["llm.chapter_pipeline"] = _FAKE_PIPELINE

from storage.database import engine, SessionLocal  # noqa: E402
from storage.models import (  # noqa: E402
    Base, Project, WorkflowRun, Theme, WorldEntry, Character, CharacterArc,
    CharacterRelation, ProjectOutline, Foreshadowing,
)
from storage.models.screenplay import Screenplay  # noqa: E402
from llm.workflow import (  # noqa: E402
    SCRIPT_STAGE_DEFS, plan_bootstrap_stages, _build_bootstrap_locked,
    commit_bootstrap, run_bootstrap_sync,
)
from llm.script_pipeline import _parse_json, _normalize_storyboard_data  # noqa: E402

PID = "scriptboot01"

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _stage(data):
    return {"status": "ok", "data": data}


SCRIPT_STAGE_RESULTS = {
    "script_stage_1_base": _stage({"total_acts": 3, "total_scenes": 2, "est_duration_minutes": 100}),
    "script_stage_2a_theme": _stage({"theme": "复仇与救赎", "tone": "黑暗"}),
    "script_stage_2b_style": _stage({"style": "冷峻", "pacing": "快节奏"}),
    "script_stage_2c_world": _stage({"world_entries": [
        {"category": "地理", "title": "荒原", "content": "黄沙", "tags": ["a"]},
    ]}),
    "script_stage_3a_protagonist": _stage({"characters": [
        {"name": "林墨白", "role": "主角", "description": "剑客",
         "profile": {"personality": "冷"}, "appearance": {"height": "180cm"}},
    ]}),
    "script_stage_3b_antagonist": _stage({"characters": [
        {"name": "顾临风", "role": "反派", "description": "楼主",
         "profile": {}, "appearance": {}},
    ]}),
    "script_stage_3c_supporting": _stage({
        "characters": [
            {"name": "小七", "role": "配角", "description": "侍从",
             "profile": {}, "appearance": {}},
        ],
        "relations": [
            {"from": "林墨白", "to": "顾临风", "type": "仇敌",
             "description": "杀父", "strength": 9},
        ],
    }),
    "script_stage_3d_arcs": _stage({"arcs": [
        {"character_name": "林墨白", "arc_type": "成长", "start_state": "隐忍",
         "end_state": "释然", "key_behavior": "放下刀", "appearance_shifts": ["后期素服"]},
    ]}),
    "script_stage_4a_outline": _stage({
        "outline_text": "梗概", "pacing_notes": "前紧后松",
        "acts": [{"act": "第一幕", "goal": "相遇"}],
        "scenes": [
            {"scene_number": 2, "title": "酒馆", "act": "第一幕",
             "scene_type": "对话场景", "location": "酒馆", "time_of_day": "夜晚",
             "characters_present": ["林墨白"], "synopsis": "相遇"},
            {"scene_number": 1, "title": "荒原", "act": "第一幕",
             "scene_type": "动作场景", "location": "荒原", "time_of_day": "白天",
             "characters_present": ["林墨白"], "synopsis": "开场"},
        ],
    }),
    "script_stage_4b_foreshadow": _stage({"foreshadowings": [
        {"title": "断剑", "content": "剑上缺口", "type": "长伏笔",
         "suggested_plant_scene": 1, "importance": "high", "visual_motif": "特写"},
    ]}),
}


def test_planner_and_locked():
    print("\n[1] planner / locked 按 project_type 分支")
    novel_ids = {s["id"] for s in plan_bootstrap_stages({}, {}, project_type="novel")}
    script_ids = {s["id"] for s in plan_bootstrap_stages({}, {}, project_type="script")}
    check("script planner 不含小说 stage", not (novel_ids & script_ids), str(novel_ids & script_ids))
    check("script planner 全部来自 SCRIPT_STAGE_DEFS", script_ids <= set(SCRIPT_STAGE_DEFS))
    script_stages = plan_bootstrap_stages({}, {}, project_type="script")
    check("3d/4a/4b 必跑", all(
        next(s for s in script_stages if s["id"] == sid)["needs_llm"]
        for sid in ("script_stage_3d_arcs", "script_stage_4a_outline", "script_stage_4b_foreshadow")
    ))

    script_locked = _build_bootstrap_locked(
        {"title": "t", "chapter_word_count": 3, "total_chapters": 100,
         "script_format": "short_drama", "script_episode_count": 12,
         "total_scenes": 30}, "script")
    check("script locked 含剧本字段", script_locked["script_format"] == "short_drama"
          and script_locked["script_episode_count"] == 12 and script_locked["total_scenes"] == 30)
    check("script locked 不含章节字段", "chapter_word_count" not in script_locked
          and "total_chapters" not in script_locked)
    novel_locked = _build_bootstrap_locked({"chapter_word_count": 3, "total_chapters": 100}, "novel")
    check("novel locked 保持章节字段", novel_locked["chapter_word_count"] == 3
          and novel_locked["total_chapters"] == 100)


def test_json_parser():
    print("\n[2] JSON 兜底 / 分镜规范化")
    check("markdown 对象", _parse_json('```json\n{"a": 1}\n```') == {"a": 1})
    check("前后解释且字符串含括号", _parse_json('说明：\n{"a": "含 } 字符", "b": [1,2]}\n结束')["a"] == "含 } 字符")
    check("尾逗号", _parse_json('{"a": 1,}') == {"a": 1})
    check("数组", _parse_json('[{"shot_number": 1}]') == [{"shot_number": 1}])
    check("字符串内换行", _parse_json('{"a": "x\ny"}') == {"a": "x\ny"})
    check("分镜去重/补号", [s["shot_number"] for s in _normalize_storyboard_data(
        [{"shot_number": 1}, {"shot_number": 1}, {"visual_description": "x"}])] == [1, 2, 3])


def test_script_commit():
    print("\n[3] script commit 落库")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        project = Project(id=PID, title="测试剧本", description="少年复仇",
                          project_type="script", script_format="movie")
        db.add(project)
        db.commit()

        run = WorkflowRun(project_id=PID, name="bootstrap",
                          stages=list(SCRIPT_STAGE_DEFS.values()), status="completed")
        db.add(run)
        db.commit()
        run.stage_results = {
            "_meta": {"user_input": {"title": "测试剧本", "script_format": "movie",
                                     "script_episode_count": 2}},
            **SCRIPT_STAGE_RESULTS,
        }
        db.commit()

        result = commit_bootstrap(PID, run.id, db)
        check("commit 成功", result["status"] == "committed", str(result))
        db.expire_all()
        check("Theme 落库", db.query(Theme).filter_by(project_id=PID).count() == 1)
        check("WorldEntry 落库", db.query(WorldEntry).filter_by(project_id=PID).count() == 1)
        lin = db.query(Character).filter_by(project_id=PID, name="林墨白").first()
        check("角色 appearance 落库", lin is not None and lin.appearance.get("height") == "180cm")
        check("关系落库", db.query(CharacterRelation).filter_by(project_id=PID).count() == 1)
        arc = db.query(CharacterArc).filter_by(project_id=PID).first()
        check("弧光保留造型变化", arc is not None and "造型变化" in (arc.end_state or ""))
        outline = db.query(ProjectOutline).filter_by(project_id=PID).first()
        check("大纲 acts 落库", outline is not None and bool(outline.structure.get("acts")))
        scenes = db.query(Screenplay).filter_by(project_id=PID).order_by(Screenplay.scene_number).all()
        check("场景去重排序落库", [s.scene_number for s in scenes] == [1, 2])
        check("伏笔落库", db.query(Foreshadowing).filter_by(project_id=PID).count() == 1)
        check("不创建小说章节", outline.chapter_outlines == [])

        result2 = commit_bootstrap(PID, run.id, db)
        db.expire_all()
        check("重复 commit 成功", result2["status"] == "committed", str(result2))
        check("重复 commit 幂等", db.query(Theme).filter_by(project_id=PID).count() == 1
              and db.query(Character).filter_by(project_id=PID).count() == 3
              and db.query(Screenplay).filter_by(project_id=PID).count() == 2)

        other = Project(id="otherproj01", title="x", project_type="script")
        db.add(other)
        db.commit()
        check("run/project 不匹配被拒", commit_bootstrap(other.id, run.id, db)["status"] == "failed")
    finally:
        db.close()


def test_run_bootstrap_sync():
    print("\n[4] 完整 bootstrap 状态为 completed（_meta 不参与 all_done）")
    from llm import workflow as wf

    db = SessionLocal()
    try:
        project = Project(id="scriptboot02", title="同步剧本", description="x",
                          project_type="script", script_format="movie")
        db.add(project)
        db.commit()
        run = WorkflowRun(
            project_id=project.id, name="bootstrap",
            stages=plan_bootstrap_stages({}, {}, project_type="script"),
            status="pending",
        )
        db.add(run)
        db.commit()

        original = wf._run_single_stage

        def fake_run_single_stage(stage_id, locked, user_filled, prev_outputs, db=None, project_id=None):
            if stage_id in SCRIPT_STAGE_RESULTS:
                return SCRIPT_STAGE_RESULTS[stage_id]["data"]
            # 用户已填 stage 不会走到这里；needs_llm_if_missing 为 false 时由
            # run_bootstrap_sync 直接标 user_filled。
            return {}

        wf._run_single_stage = fake_run_single_stage
        try:
            result = run_bootstrap_sync(
                run.id,
                {"title": "同步剧本", "description": "x", "genre": "悬疑",
                 "project_type": "script", "script_format": "movie"},
                db=db,
            )
        finally:
            wf._run_single_stage = original

        check("run 状态 completed", result["status"] == "completed", str(result["status"]))
        check("_meta 不导致 partial", result["stage_results"].get("_meta", {}).get("project_type") == "script")
    finally:
        db.close()


def main():
    test_planner_and_locked()
    test_json_parser()
    test_script_commit()
    test_run_bootstrap_sync()

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    engine.dispose()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

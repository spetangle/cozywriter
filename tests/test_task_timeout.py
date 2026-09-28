"""任务超时逻辑回归测试。

背景：推理模型（opencode/deepseek-v4.1-flash）单章 9 步流水线可达 10~20 分钟，
原先 chapter_pipeline 软超时只有 600s，导致任务其实已完成（章节已保存），
却被标记为 failed，前端据此提示"生成失败"并丢弃结果。

本测试确保：
  1. chapter_pipeline / chapter_revise / word_adjust 等 LLM 任务超时足够长
  2. fn 正常返回时，即使超过软超时，任务也标记 completed（不判 failed）

运行：python tests/test_task_timeout.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 用临时 SQLite，避免碰 data/cozywriter.db（必须在 import config 之前设置）
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"

from api import tasks as tasks_mod  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if (detail and not cond) else ''}")
    if not cond:
        failures.append(name)


print("[1] LLM 任务超时阈值")
check("chapter_pipeline >= 3600s",
      tasks_mod._task_timeout_seconds("chapter_pipeline") >= 3600,
      str(tasks_mod._task_timeout_seconds("chapter_pipeline")))
check("chapter_revise >= 3600s",
      tasks_mod._task_timeout_seconds("chapter_revise") >= 3600)
check("batch_pipeline >= 7200s",
      tasks_mod._task_timeout_seconds("batch_pipeline") >= 7200)
check("bootstrap >= 7200s",
      tasks_mod._task_timeout_seconds("bootstrap") >= 7200)

print("\n[2] fn 正常返回但超过软超时 → 仍算完成")
# 注册一个极短超时，模拟"超过阈值但函数已完成"
tasks_mod._TASK_TIMEOUTS["unit_timeout_test"] = 0.05


def _slow_but_ok(task_id, marker=None):
    time.sleep(0.3)  # 远超过 0.05s 软超时
    return {"ok": True, "marker": marker}


task = tasks_mod.submit_llm_task(
    task_type="unit_timeout_test",
    llm_call_fn=_slow_but_ok,
    project_id="unitproj",
    description="unit timeout regression",
    marker="hello",
)

deadline = time.time() + 10
while time.time() < deadline and task.status in ("pending", "running", "queued"):
    time.sleep(0.05)

check("任务最终为 completed", task.status == "completed", f"status={task.status} error={task.error}")
check("结果保留", bool(task.result) and task.result.get("marker") == "hello", str(task.result))
check("错误为空", not task.error, task.error)

if not failures:
    print("\nALL PASS")
else:
    print(f"\n{len(failures)} FAILED: {', '.join(failures)}")

try:
    os.unlink(_tmp_db.name)
except OSError:
    pass

sys.exit(1 if failures else 0)

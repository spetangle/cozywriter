"""字数收敛逻辑单元测试（无需真实 LLM）。

覆盖：
- adjust_word_count 的候选选择优先级（优先入区间 → 次选未过冲 → 最后兜底）
- 过冲候选被标记
- opencode provider 仅在开启时可用

运行：python tests/test_word_adjust.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_word_adjust.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

import llm.chapter_pipeline as cp  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _make_text(n):
    return "字" * n


def run_adjust(outputs, target=800, min_w=720, max_w=880):
    """用固定的 LLM 输出序列驱动 adjust_word_count。"""
    calls = {"i": 0}

    def fake_call(role_name, ctx, user_msg, provider=None, db=None, task_id="", **kw):
        idx = min(calls["i"], len(outputs) - 1)
        calls["i"] += 1
        return {
            "text": outputs[idx],
            "fingerprint": {"role_name": role_name},
        }

    orig = cp._call_llm_with_fingerprint
    cp._call_llm_with_fingerprint = fake_call
    try:
        return cp.adjust_word_count(
            _make_text(1200), target, min_w, max_w,
            {"key_content": "x"}, "mimo", task_id="t",
        )
    finally:
        cp._call_llm_with_fingerprint = orig


def main():
    print("\n[1] 过冲候选不参与优先选择")
    # 第一轮过冲到 500（< min*0.9=648），第二轮命中 800
    import json
    hit = json.dumps({"compressed_text": _make_text(800), "final_word_count": 800})
    overshoot = json.dumps({"compressed_text": _make_text(500), "final_word_count": 500})
    result = run_adjust([overshoot, hit])
    check("命中区间的候选被选中", len(result) == 800, f"got {len(result)}")

    print("\n[2] 全部未达标时优先选未过冲")
    # 两轮都未命中但未过冲：950（>max 但 <max*1.1=968）与 980（过冲）
    near = json.dumps({"compressed_text": _make_text(950), "final_word_count": 950})
    over = json.dumps({"compressed_text": _make_text(980), "final_word_count": 980})
    result = run_adjust([near, over, over])
    check("选择未过冲的 950", len(result) == 950, f"got {len(result)}")

    print("\n[3] 过冲保护阈值")
    check("min*0.9 以下算过冲", 500 < 720 * 0.9)
    check("max*1.1 以上算过冲", 980 > 880 * 1.1)

    print("\n[4] opencode provider 开关")
    from config import settings
    from llm.factory import LLMFactory
    check("工厂已注册 opencode", "opencode" in LLMFactory._providers)
    import llm.opencode_provider as op
    check("opencode 默认模型存在", op.OpencodeProvider.DEFAULT_MODEL == "big-pickle")
    check("opencode 默认关闭", getattr(settings, "opencode_enabled", None) is False)
    try:
        LLMFactory.create(provider="opencode", db=None)
        ok = False
    except ValueError as e:
        ok = "未启用" in str(e)
    except Exception:
        ok = False
    check("未开启时拒绝创建 opencode", ok)

    print("\n[5] opencode provider 注册到服务商与模型列表")
    from fastapi.testclient import TestClient
    import main
    from storage.database import engine as _engine
    from storage.models import Base
    Base.metadata.create_all(bind=_engine)
    client = TestClient(main.app)
    prov_ids = [p["id"] for p in client.get("/api/providers").json()]
    check("服务商列表包含 opencode", "opencode" in prov_ids, str(prov_ids))
    body = client.post("/api/providers/list-models", json={"provider_id": "opencode"}).json()
    check("未启用时返回内置模型", body.get("ok") is True and body.get("fallback") is True, str(body)[:160])
    check("内置模型含 big-pickle", any(m["id"] == "big-pickle" for m in body.get("models", [])))

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

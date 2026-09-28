"""续写章节号字段归一化测试（无需真实 LLM）。"""
import os
import sys
import tempfile
import types

ROOT = "/mnt/g/BaiduSyncdisk/py/cozywriter"
sys.path.insert(0, ROOT)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.gettempdir(), "cozywriter_norm.db")

import llm.workflow as wf  # noqa: E402

_fail = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _fail.append(name)


def main():
    print("\n[1] _normalize_chapter_outlines 兼容多种字段名")
    items = [
        {"chapter_num": 1, "title": "a"},
        {"chapter_number": 2, "title": "b"},
        {"chapter": 3, "title": "c"},
        {"chapter_no": 4, "title": "d"},
        {"num": 5, "title": "e"},
        {"number": "6", "title": "f"},
        {"index": 7, "title": "g"},
        {"title": "no-number-should-skip"},
        {"chapter_num": None, "title": "null-skip"},
        "not-a-dict",
    ]
    out = wf._normalize_chapter_outlines(items)
    nums = [c["chapter_num"] for c in out]
    check("归一化出 7 条", len(out) == 7, str(nums))
    check("编号为 1..7 且全为 int", nums == [1, 2, 3, 4, 5, 6, 7] and all(isinstance(n, int) for n in nums), str(nums))
    check("保留原始其它字段", out[0]["title"] == "a" and out[2]["title"] == "c")

    print("\n[2] 续写用 chapter_number 不再算作 0 新增")
    locked = {"total_chapters": 150, "title": "t"}
    first = {
        "chapter_outlines": [
            {"chapter_num": i, "title": f"第{i}章", "key_content": f"事件{i}"}
            for i in range(1, 101)
        ]
    }
    # 第一次续写返回 chapter_number（此前会被判为 0 新增）
    round1 = [{"chapter_number": i, "title": f"第{i}章", "key_content": f"事件{i}"}
              for i in range(101, 151)]
    calls = {"n": 0}

    def fake_generate(**kwargs):
        calls["n"] += 1
        # 第一轮后即给全，后续不应再调用
        return '{"chapter_outlines": ' + _dump(round1) + "}"

    class _FakeLLM:
        def generate(self, **kwargs):
            return fake_generate(**kwargs)

    orig_factory = None
    try:
        from llm import factory as factory_mod
        orig_factory = factory_mod.LLMFactory.create
        factory_mod.LLMFactory.create = classmethod(lambda cls, *a, **kw: _FakeLLM())
        result = wf._continue_chapter_outlines_if_needed(
            first, locked, {}, {}, db=None, target_total=150,
        )
    finally:
        if orig_factory is not None:
            from llm import factory as factory_mod
            factory_mod.LLMFactory.create = orig_factory

    got = sorted(int(c["chapter_num"]) for c in result["chapter_outlines"])
    check("最终 150 章齐全", len(got) == 150 and got[0] == 1 and got[-1] == 150, f"count={len(got)}")
    check("只调用 1 次续写", calls["n"] == 1, f"calls={calls['n']}")

    print("\n" + ("ALL PASS" if not _fail else f"{len(_fail)} FAILED: {_fail}"))
    return 1 if _fail else 0


def _dump(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())

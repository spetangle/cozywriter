"""DeepSeek JSON 空响应降级 / JSON 开关单元测试（无需真实 LLM）。

覆盖（对应 docs/FIX_PLAN_NOVEL_FLOW.md §5 P1-5）：
- JSON 模式返回空 → 降级重试：去掉 response_format、追加 JSON 强约束、抬高 max_tokens 下限
- use_json_output=False → 不传 response_format，且不再触发降级
- 降级重试 max_tokens 下限
- 每服务商 use_json_output 配置（DB 字段 / 工厂透传 / API 显式置空恢复默认）

运行：python tests/test_deepseek_json_fallback.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DB = os.path.join(tempfile.gettempdir(), "cozywriter_test_ds_json.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

from llm.deepseek_provider import DeepSeekProvider  # noqa: E402

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15

    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]
        self.usage = _Usage()


class _Completions:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self.outputs) - 1)
        content, finish = self.outputs[idx]
        return _Response(content, finish)


class _Client:
    def __init__(self, outputs):
        self.chat = type("C", (), {"completions": _Completions(outputs)})()


def _provider(outputs, use_json=True, max_tokens=100):
    p = DeepSeekProvider(api_key="x", use_json_output=use_json)
    client = _Client(outputs)
    p._get_client = lambda: client
    p._calls = client.chat.completions
    return p


def _gen(provider, prompt, max_tokens):
    return provider.generate(
        prompt, system_prompt="你是助手", use_json=provider.use_json_output,
        max_tokens=max_tokens, task_type="unit_test",
    )


def main():
    print("\n[1] JSON 空响应 → 降级重试（去 response_format + 追加约束 + 抬高 token）")
    p = _provider([("", "stop"), ('{"ok": true}', "stop")], use_json=True)
    result = _gen(p, "请输出 JSON", max_tokens=100)
    calls = p._calls.calls
    check("共调用两次", len(calls) == 2, f"got {len(calls)}")
    check("首次带 response_format", calls[0].get("response_format") == {"type": "json_object"})
    check("降级去掉 response_format", "response_format" not in calls[1])
    check("降级 max_tokens 提升到下限",
          calls[1].get("max_tokens") == DeepSeekProvider.JSON_MIN_MAX_TOKENS,
          f"got {calls[1].get('max_tokens')}")
    check("降级追加了 JSON 强约束消息",
          any(DeepSeekProvider.JSON_RETRY_HINT == m.get("content")
              for m in calls[1].get("messages", []) if isinstance(m, dict)))
    check("返回降级后的文本", result == '{"ok": true}', f"got {result!r}")

    print("\n[2] max_tokens 已高于下限时保持不变")
    p = _provider([("", "stop"), ("{}", "stop")], use_json=True)
    _gen(p, "请输出 JSON", max_tokens=4096)
    check("保留较大 max_tokens", p._calls.calls[1].get("max_tokens") == 4096,
          f"got {p._calls.calls[1].get('max_tokens')}")

    print("\n[3] use_json_output=False → 不传 response_format、不降级")
    p = _provider([("", "stop"), ("fallback", "stop")], use_json=False)
    result = _gen(p, "普通文本", max_tokens=100)
    check("只调用一次", len(p._calls.calls) == 1, f"got {len(p._calls.calls)}")
    check("无 response_format", "response_format" not in p._calls.calls[0])
    check("返回首次（空）内容", result == "", f"got {result!r}")

    print("\n[4] DB 字段 to_dict 包含 use_json_output")
    from storage.models.provider import Provider as _P
    row = _P(id="deepseek", name="DeepSeek", api_key="x", use_json_output=False)
    check("to_dict 暴露 use_json_output", row.to_dict().get("use_json_output") is False)

    print("\n[5] 工厂按 DB 配置透传 use_json_output")
    from storage.database import engine, SessionLocal
    from storage.models import Base
    Base.metadata.create_all(bind=engine)
    from llm.factory import LLMFactory
    db = SessionLocal()
    try:
        db.query(_P).filter(_P.id == "deepseek").delete()
        db.add(_P(id="deepseek", name="DeepSeek", api_key="x", model="deepseek-chat",
                  use_json_output=False))
        db.commit()
        inst = LLMFactory.create(provider="deepseek", db=db)
        check("工厂实例读取到 use_json_output=False",
              getattr(inst, "use_json_output", None) is False,
              str(getattr(inst, "use_json_output", None)))
    finally:
        db.close()

    print("\n[6] API：显式 null 恢复默认，false 覆盖生效")
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)
    # 置为 false
    r = client.put("/api/providers/deepseek", json={"use_json_output": False})
    check("PUT false 返回 200", r.status_code == 200, str(r.status_code))
    check("读取为 false", client.get("/api/providers/deepseek").json().get("use_json_output") is False)
    # 显式 null 恢复 auto
    r = client.put("/api/providers/deepseek", json={"use_json_output": None})
    check("PUT null 返回 200", r.status_code == 200, str(r.status_code))
    check("读取恢复为 null", client.get("/api/providers/deepseek").json().get("use_json_output") is None)
    # 未传该字段不应改动已有值
    client.put("/api/providers/deepseek", json={"use_json_output": True})
    client.put("/api/providers/deepseek", json={"model": "deepseek-chat"})
    check("未传字段保持 true", client.get("/api/providers/deepseek").json().get("use_json_output") is True)

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass
    sys.exit(code)

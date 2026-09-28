"""RAG 本地 / 在线 embedding 切换回归测试（无需真实网络）。

覆盖：
- 默认 local；配置 online 后 get_embedder 返回 OnlineEmbedder
- OnlineEmbedder.embed 参数与顺序正确（OpenAI 兼容 /embeddings）
- /api/config/rag 读写、/rag/test、/rag/reset
- KnowledgeBase.reset_all_collections

运行：python tests/test_rag_online.py
"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP_DIR = tempfile.mkdtemp(prefix="cozywriter_rag_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'rag.db')}"
os.environ["CHROMA_PERSIST_DIR"] = os.path.join(_TMP_DIR, "chroma")

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


class _Data:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        inputs = kwargs.get("input") or []
        # 故意倒序返回，验证 embed() 会按 index 重新排序
        return _Resp([_Data(i, [float(i), 0.0, 1.0]) for i in reversed(range(len(inputs)))])


class _FakeClient:
    def __init__(self):
        self.embeddings = _FakeEmbeddings()


def main():
    from storage.database import engine, SessionLocal
    from storage.models import Base
    from storage.models.system_setting import SystemSetting
    from rag.embedder import get_embedder, LocalEmbedder
    from rag.online_embedder import OnlineEmbedder

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("\n[1] 默认使用本地 embedding")
    check("默认 get_embedder 为 LocalEmbedder", isinstance(get_embedder(db=db), LocalEmbedder))

    print("\n[2] 配置 online 后切换为在线 embedding")
    SystemSetting.set(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, "online")
    SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, "https://api.example.com/v1")
    SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, "sk-test")
    SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "text-embedding-3-small")
    emb = get_embedder(db=db)
    check("返回 OnlineEmbedder", isinstance(emb, OnlineEmbedder), type(emb).__name__)
    check("模型名正确", emb.model_name == "text-embedding-3-small", emb.model_name)

    print("\n[3] OnlineEmbedder 请求参数与顺序")
    fake = _FakeClient()
    emb._client = fake
    vecs = emb.embed(["a", "b", "c"])
    check("调用 1 次", len(fake.embeddings.calls) == 1, str(len(fake.embeddings.calls)))
    call = fake.embeddings.calls[0]
    check("model 正确", call.get("model") == "text-embedding-3-small", str(call.get("model")))
    check("input 正确", call.get("input") == ["a", "b", "c"], str(call.get("input")))
    check("结果按 index 排序", vecs == [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [2.0, 0.0, 1.0]], str(vecs))

    print("\n[4] 在线配置不完整时回退本地")
    SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "")
    check("缺模型名回退 LocalEmbedder", isinstance(get_embedder(db=db), LocalEmbedder))
    SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "text-embedding-3-small")

    print("\n[5] /api/config/rag 读写")
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)
    r = client.get("/api/config/rag")
    body = r.json()
    check("GET 200 且 mode=online", r.status_code == 200 and body.get("mode") == "online", str(body))
    check("has_api_key=True", body.get("has_api_key") is True, str(body))
    check("api_key 不明文返回", "api_key" not in body and "sk-test" not in r.text, r.text[:120])

    r = client.put("/api/config/rag", json={"mode": "local"})
    check("PUT 切回 local", r.status_code == 200 and r.json()["settings"]["mode"] == "local", r.text[:160])
    r = client.put("/api/config/rag", json={"mode": "bogus"})
    check("非法 mode 返回 400", r.status_code == 400, str(r.status_code))

    print("\n[6] /api/config/rag/test（mock 在线实现）")
    import rag.online_embedder as oe

    class _FakeOnline:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model")

        def test(self):
            return {"ok": True, "dimension": 8, "model": self.model}

    orig = oe.OnlineEmbedder
    oe.OnlineEmbedder = _FakeOnline
    try:
        r = client.post("/api/config/rag/test", json={"mode": "online", "api_key": "x", "model": "m"})
        body = r.json()
        check("在线测试 ok", body.get("ok") is True and body.get("dimension") == 8, str(body))
    finally:
        oe.OnlineEmbedder = orig

    print("\n[7] /api/config/rag/reset")
    r = client.post("/api/config/rag/reset")
    check("reset 200", r.status_code == 200 and r.json().get("status") == "ok", r.text[:160])

    print("\n[8] reset_all_collections 存在")
    from rag.knowledge_base import KnowledgeBase
    check("静态方法存在", callable(getattr(KnowledgeBase, "reset_all_collections", None)))

    db.close()
    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    code = main()
    try:
        import shutil
        shutil.rmtree(_TMP_DIR, ignore_errors=True)
    except Exception:
        pass
    sys.exit(code)

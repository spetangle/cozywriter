"""CPU 版 RAG 回归测试（无需真实 torch / sentence-transformers）。

覆盖：
- ModelManager.load_model 强制 device="cpu"
- 未安装 sentence-transformers 时给出可操作提示
- CPU 安装脚本存在且可执行

运行：python tests/test_rag_cpu.py
"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def main():
    print("\n[1] load_model 强制 CPU")
    captured = {}
    fake = types.ModuleType("sentence_transformers")

    class _FakeST:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    fake.SentenceTransformer = _FakeST
    sys.modules["sentence_transformers"] = fake
    try:
        from rag.model_manager import ModelManager
        mgr = ModelManager("moka-ai/m3e-base")
        mgr.load_model()
        check("device=cpu", captured.get("kwargs", {}).get("device") == "cpu", str(captured))
        check("传入本地模型目录", bool(captured.get("args")), str(captured))
    finally:
        sys.modules.pop("sentence_transformers", None)

    print("\n[2] 缺 sentence-transformers 时提示安装方式")
    try:
        from rag.model_manager import ModelManager
        import importlib
        mgr = ModelManager("moka-ai/m3e-base")
        mgr.unload_model()
        try:
            mgr.load_model()
            check("应抛出 RuntimeError", False, "未抛异常")
        except RuntimeError as e:
            msg = str(e)
            check("提示 requirements-rag.txt", "requirements-rag.txt" in msg, msg[:160])
            check("提示 CPU torch 安装", "download.pytorch.org/whl/cpu" in msg, msg[:200])
    except Exception as e:
        check("缺库路径可测试", False, repr(e))

    print("\n[3] CPU 安装脚本存在")
    for rel in ("tools/install_rag_cpu.sh", "tools/install_rag_cpu.bat", "tools/install_rag_cpu.ps1"):
        check(f"存在 {rel}", os.path.exists(os.path.join(ROOT, rel)))
    sh = os.path.join(ROOT, "tools/install_rag_cpu.sh")
    check("install_rag_cpu.sh 可执行", os.access(sh, os.X_OK), sh)

    print("\n[4] requirements-rag 说明包含 CPU 指引")
    with open(os.path.join(ROOT, "requirements-rag.txt"), encoding="utf-8") as f:
        content = f.read()
    check("提及 CPU torch 源", "download.pytorch.org/whl/cpu" in content)

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""依赖拆分回归测试。

目的：确保核心 requirements.txt 不再包含 sentence-transformers（它会连带
安装 torch / nvidia-* CUDA 库），RAG 依赖单独放在 requirements-rag.txt。

运行：python tests/test_requirements_split.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CORE = os.path.join(ROOT, "requirements.txt")
RAG = os.path.join(ROOT, "requirements-rag.txt")

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _packages(path):
    """解析 requirements 文件里的顶层包名（小写，忽略 -r/-e/注释）。"""
    names = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name = re.split(r"[<>=!\[; ]", line)[0].strip().lower()
            if name:
                names.append(name)
    return names


def main():
    check("核心 requirements.txt 存在", os.path.exists(CORE))
    check("requirements-rag.txt 存在", os.path.exists(RAG))

    core = _packages(CORE)
    rag = _packages(RAG)

    print("\n[1] 核心依赖不含 RAG / 重型库")
    for banned in ("sentence-transformers", "torch", "torchvision", "transformers"):
        check(f"核心不含 {banned}", banned not in core, str(core))
    check("核心不含 nvidia-*", not any(n.startswith("nvidia") for n in core), str(core))

    print("\n[2] 核心仍包含主流程必需库")
    for required in ("fastapi", "uvicorn", "sqlalchemy", "chromadb",
                     "huggingface-hub", "anthropic", "openai", "pydantic",
                     "pydantic-settings", "json_repair"):
        check(f"核心含 {required}", required in core, str(core))

    print("\n[3] RAG 依赖文件")
    check("rag 含 sentence-transformers", "sentence-transformers" in rag, str(rag))

    print("\n[4] requirements-rag 继承核心")
    with open(RAG, encoding="utf-8") as f:
        content = f.read()
    check("rag 引用 -r requirements.txt", "-r requirements.txt" in content, content[:200])

    print("\n[5] 未安装 sentence-transformers 时核心模块可导入")
    try:
        import rag.model_manager as mm  # noqa: F401
        import rag.vector_store as vs  # noqa: F401
        check("rag 模块可导入（懒加载 sentence-transformers）", True)
    except Exception as e:
        check("rag 模块可导入（懒加载 sentence-transformers）", False, repr(e))

    print("\n" + ("ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}"))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())

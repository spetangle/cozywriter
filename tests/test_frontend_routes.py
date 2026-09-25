"""前端 ↔ 后端 路由一致性测试。

扫描 web/static/js 下所有 `/api/...` 字面量，与 FastAPI 实际注册的路由比对，
防止再出现「前端调了一个不存在的接口、被 if (!res.ok) return 静默吞掉」的情况
（本项目曾同时存在 7 处这类 404）。

已知误报白名单：模板字符串拼接导致正则截断的 URL。

运行：python tests/test_frontend_routes.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402

# 字符串拼接（'/api/projects/' + id + '/export'）会让正则只截到前半段，
# 这些前缀本身是合法的，不算缺失。
ALLOWED_PREFIXES = (
    "/api/projects/",          # '/api/projects/' + project.id + '/export'
)

JS_DIR = os.path.join(ROOT, "web", "static", "js")
CALL_RE = re.compile(r"/api/[A-Za-z0-9\-_/$.{}]*")


def iter_routes(routes):
    """递归展开 FastAPI 路由。

    旧版 FastAPI 直接返回 APIRoute；0.141+ 会把 include_router 的结果包成
    `_IncludedRouter`，需要用 original_router.routes 展开，否则测试会误判
    所有业务路由都不存在。
    """
    for r in routes:
        path = getattr(r, "path", None)
        if path:
            yield r
        nested = getattr(r, "routes", None)
        if nested:
            yield from iter_routes(nested)
        original = getattr(r, "original_router", None)
        if original is not None:
            yield from iter_routes(getattr(original, "routes", []) or [])


def backend_routes() -> set[str]:
    out = set()
    for r in iter_routes(main.app.routes):
        p = getattr(r, "path", None)
        if p:
            out.add(re.sub(r"\{[^}]+\}", "{}", p))
    return out


def frontend_calls() -> list[tuple[str, int, str]]:
    routes = backend_routes()
    found = []
    for root, _dirs, files in os.walk(JS_DIR):
        for fn in sorted(files):
            if not fn.endswith(".js"):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, JS_DIR).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    for m in CALL_RE.findall(line):
                        cand = re.sub(r"\$\{[^}]*\}", "{}", m).split("?")[0].rstrip("`,")
                        if cand in routes:
                            continue
                        if any(cand.startswith(p) for p in ALLOWED_PREFIXES):
                            continue
                        found.append((rel, i, cand))
    return found


def main_check() -> int:
    routes = backend_routes()
    print(f"后端路由: {len(routes)} 条")

    # 本轮新增/修复的接口必须存在
    required = [
        "POST /api/projects/{}/characters/{}/generate-appearance",
        "POST /api/projects/{}/properties/{}/history",
        "GET /api/projects/{}/storyboards",
        "POST /api/projects/{}/screenplays/{}/storyboards",
        "PUT /api/projects/{}/storyboards/{}",
        "DELETE /api/projects/{}/storyboards/{}",
        "GET /api/projects/{}/screenplays/{}/storyboards",
        "POST /api/projects/{}/screenplays/{}/storyboards/generate",
        "GET /api/projects/{}/worldbuilding",
        "GET /api/projects/{}/chapters/{}/outline",
        "POST /api/projects/{}/chapters/{}/rollback/{}",
    ]
    by_method: dict[str, set[str]] = {}
    for r in iter_routes(main.app.routes):
        p = getattr(r, "path", None)
        if not p:
            continue
        norm = re.sub(r"\{[^}]+\}", "{}", p)
        for meth in getattr(r, "methods", None) or []:
            by_method.setdefault(meth, set()).add(norm)

    print("\n[必需接口]")
    failures = []
    for entry in required:
        meth, path = entry.split(" ", 1)
        ok = path in by_method.get(meth, set())
        print(f"  {'PASS' if ok else 'FAIL'}  {entry}")
        if not ok:
            failures.append(entry)

    print("\n[前端调用了但后端不存在的接口]")
    orphans = frontend_calls()
    if orphans:
        for rel, ln, url in orphans:
            print(f"  FAIL  {rel}:{ln}  {url}")
        failures.extend(f"{rel}:{ln} {url}" for rel, ln, url in orphans)
    else:
        print("  PASS  无孤儿调用")

    # 曾经出现过、必须不再复现的错误路径（按字面特征片段判断）
    print("\n[历史错误路径不得复现]")
    js_blob = []
    for root, _d, files in os.walk(JS_DIR):
        for fn in files:
            if fn.endswith(".js"):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    js_blob.append(f.read())
    blob = "\n".join(js_blob)

    forbidden = [
        ("/world-settings", "世界观应为 /worldbuilding"),
        ("/outlines/${", "章节细纲应为 /chapters/{id}/outline"),
        ("/api/inspirations/count", "接口不存在，死调用已移除"),
        ("chapters/${this.currentChapter.id}/rollback`",
         "回滚应把 version_num 放在路径里"),
        ("sb.description ||", "分镜字段应为 visual_description"),
        ("sb.duration\"", "分镜字段应为 duration_estimate"),
    ]
    for snippet, why in forbidden:
        present = snippet in blob
        print(f"  {'FAIL' if present else 'PASS'}  不含 {snippet!r}  ({why})")
        if present:
            failures.append(snippet)

    print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_check())

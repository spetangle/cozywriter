"""联网搜索工具（可选）。

「搜索相似小说」功能会先尝试联网搜索，把候选作品喂给 LLM 分析。
搜索服务需要用户在「全局设置」里配置（system_settings）：

  search_provider = tavily | serper
  search_api_key  = <对应服务的 API Key>

未配置时不联网，`web_search()` 返回 None，调用方降级为「仅基于模型知识」。
"""
from __future__ import annotations

from logger import logger
from storage.models.system_setting import SystemSetting


def _get_config(db) -> tuple[str, str]:
    if db is None:
        return "", ""
    provider = (SystemSetting.get(db, SystemSetting.KEY_SEARCH_PROVIDER, "") or "").strip().lower()
    api_key = (SystemSetting.get(db, SystemSetting.KEY_SEARCH_API_KEY, "") or "").strip()
    return provider, api_key


def is_search_configured(db) -> bool:
    provider, api_key = _get_config(db)
    return bool(provider and api_key)


def web_search(query: str, db=None, max_results: int = 5) -> list[dict] | None:
    """执行一次联网搜索。

    Returns:
        list[dict] | None：命中结果列表（title/url/content），未配置或失败返回 None。
    """
    provider, api_key = _get_config(db)
    if not provider or not api_key:
        return None
    query = (query or "").strip()
    if not query:
        return None

    try:
        import httpx
    except ImportError:
        logger.warning("[SearchTool] 缺少 httpx，跳过联网搜索")
        return None

    try:
        if provider == "tavily":
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max(1, min(max_results, 10)),
                    "search_depth": "basic",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": (r.get("content") or "")[:500],
                }
                for r in (data.get("results") or [])
            ]

        if provider == "serper":
            resp = httpx.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max(1, min(max_results, 10))},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "content": (r.get("snippet") or "")[:500],
                }
                for r in (data.get("organic") or [])
            ]

        logger.warning(f"[SearchTool] 未知搜索服务: {provider}")
        return None
    except Exception as e:
        logger.warning(f"[SearchTool] 联网搜索失败（将降级为模型知识）: {e}")
        return None


def format_search_results(results: list[dict] | None) -> str:
    if not results:
        return "（无联网结果）"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r.get('title', '')}\n   URL: {r.get('url', '')}\n   摘要: {r.get('content', '')}"
        )
    return "\n".join(lines)

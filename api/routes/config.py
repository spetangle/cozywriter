"""Provider 配置保存 API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pathlib import Path
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.system_setting import SystemSetting


router = APIRouter(prefix="/api/config", tags=["配置"])


class SaveProviderRequest(BaseModel):
    provider: str  # anthropic / openai / ollama / minimax / mimo
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None

    # 是否同时设为默认 LLM provider
    set_as_default: bool = True


class SetDefaultProviderRequest(BaseModel):
    provider: str  # minimax / mimo / anthropic / openai / ollama


class ConfigStatusResponse(BaseModel):
    anthropic_configured: bool
    openai_configured: bool
    ollama_configured: bool
    minimax_configured: bool
    mimo_configured: bool
    deepseek_configured: bool
    opencode_configured: bool = False
    default_provider: str
    # 当前激活的 provider 实际使用的模型名（用于前端工具栏展示）
    current_model: str = ""
    # RAG（embedding 模型）是否已就绪；未就绪时事件去重/相似度拦截会跳过
    rag_enabled: bool = False
    rag_model: str = ""
    # RAG 模式：local（本地 CPU 模型）/ online（在线 embedding API）
    rag_mode: str = "local"
    rag_online_configured: bool = False


class RagSettingsUpdate(BaseModel):
    mode: str | None = None                 # "local" | "online"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class RagTestRequest(BaseModel):
    mode: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


def _load_env() -> dict[str, str]:
    """读取当前 .env 内容"""
    env_path = Path(".env")
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
    else:
        content = ""
    env_vars = {}
    for line in content.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip()
    return env_vars


def _save_env(updates: dict[str, str]):
    """更新 .env 文件（不再写 DEFAULT_LLM_PROVIDER）"""
    env_path = Path(".env")
    env_vars = _load_env()
    # 去掉旧的 DEFAULT_LLM_PROVIDER（如果还有残留）
    env_vars.pop("DEFAULT_LLM_PROVIDER", None)
    env_vars.update(updates)

    lines = []
    for key, value in env_vars.items():
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines), encoding="utf-8")


@router.get("/status", response_model=ConfigStatusResponse)
async def get_config_status(db: Session = Depends(get_db)):
    """查询当前 provider 配置状态 + 当前默认模型名"""
    env_vars = _load_env()
    default_provider = SystemSetting.get(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER, "")

    # 当前模型名：优先 DB provider 记录的 model，其次环境变量，最后内置默认
    default_models = {
        "anthropic": lambda e: e.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        "openai": lambda e: e.get("OPENAI_MODEL", "gpt-4o"),
        "ollama": lambda e: e.get("OLLAMA_MODEL", "llama3.1"),
        "minimax": lambda e: e.get("MINIMAX_MODEL", "MiniMax-Text-01"),
        "mimo": lambda e: e.get("MIMO_MODEL", "mimo-vl-7b"),
        "deepseek": lambda e: e.get("DEEPSEEK_MODEL", "deepseek-chat-v4-flash"),
        "opencode": lambda e: e.get("OPENCODE_MODEL", "deepseek-v4.1-flash"),
    }
    current_model = ""
    try:
        from storage.models.provider import Provider
        row = db.query(Provider).filter(Provider.id == default_provider).first()
        if row and row.model:
            current_model = row.model
    except Exception:
        pass
    if not current_model:
        resolver = default_models.get(default_provider.lower())
        current_model = resolver(env_vars) if resolver else ""

    # RAG 状态：按当前模式判断是否可用
    rag_enabled = False
    rag_model = ""
    rag_mode = SystemSetting.get(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, "local") or "local"
    online_base = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, "")
    online_key = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, "")
    online_model = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "")
    rag_online_configured = bool(online_key and online_model)
    try:
        if rag_mode == "online":
            rag_model = online_model or "(未配置在线 embedding 模型)"
            rag_enabled = rag_online_configured
        else:
            import importlib.util
            from rag.model_manager import ModelManager
            mgr = ModelManager()
            rag_model = mgr.model_name
            has_st = importlib.util.find_spec("sentence_transformers") is not None
            rag_enabled = bool(mgr.is_model_downloaded() and has_st)
    except Exception:
        pass

    # 是否已配置：DB provider 有 key 或 .env 有 key
    def _configured(provider_id: str, env_key: str) -> bool:
        try:
            from storage.models.provider import Provider
            row = db.query(Provider).filter(Provider.id == provider_id).first()
            if row and row.api_key:
                return True
        except Exception:
            pass
        return bool(env_vars.get(env_key, ""))

    return ConfigStatusResponse(
        anthropic_configured=_configured("anthropic", "ANTHROPIC_API_KEY"),
        openai_configured=_configured("openai", "OPENAI_API_KEY"),
        ollama_configured=bool(env_vars.get("OLLAMA_BASE_URL", "")) or bool(_configured("ollama", "OLLAMA_BASE_URL")),
        minimax_configured=_configured("minimax", "MINIMAX_API_KEY"),
        mimo_configured=_configured("mimo", "MIMO_API_KEY"),
        deepseek_configured=_configured("deepseek", "DEEPSEEK_API_KEY"),
        opencode_configured=_configured("opencode", "OPENCODE_API_KEY"),
        default_provider=default_provider,
        current_model=current_model,
        rag_enabled=rag_enabled,
        rag_model=rag_model,
        rag_mode=rag_mode,
        rag_online_configured=rag_online_configured,
    )


@router.post("/save-provider")
async def save_provider(req: SaveProviderRequest, db: Session = Depends(get_db)):
    """保存用户选择的 provider 和 API Key 到 .env"""
    provider = req.provider.lower()

    if provider == "anthropic":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is required")
        _save_env({"ANTHROPIC_API_KEY": req.api_key})
    elif provider == "openai":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")
        _save_env({"OPENAI_API_KEY": req.api_key})
    elif provider == "ollama":
        base_url = req.base_url or "http://localhost:11434"
        _save_env({"OLLAMA_BASE_URL": base_url})
    elif provider == "minimax":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="MINIMAX_API_KEY is required")
        updates = {"MINIMAX_API_KEY": req.api_key}
        if req.base_url:
            updates["MINIMAX_BASE_URL"] = req.base_url
        if req.model:
            updates["MINIMAX_MODEL"] = req.model
        _save_env(updates)
    elif provider == "mimo":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="MIMO_API_KEY is required")
        updates = {"MIMO_API_KEY": req.api_key}
        if req.base_url:
            updates["MIMO_BASE_URL"] = req.base_url
        if req.model:
            updates["MIMO_MODEL"] = req.model
        _save_env(updates)
    elif provider == "deepseek":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="DEEPSEEK_API_KEY is required")
        updates = {"DEEPSEEK_API_KEY": req.api_key}
        if req.base_url:
            updates["DEEPSEEK_BASE_URL"] = req.base_url
        if req.model:
            updates["DEEPSEEK_MODEL"] = req.model
        _save_env(updates)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    # 写入默认 provider 到数据库
    if req.set_as_default:
        SystemSetting.set(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER, provider)

    return {"status": "ok", "provider": provider}


@router.post("/set-default-provider")
async def set_default_provider(req: SetDefaultProviderRequest, db: Session = Depends(get_db)):
    """单独修改默认 LLM 供应商（不改 API Key）"""
    provider = req.provider.lower()
    available = {"anthropic", "openai", "ollama", "minimax", "mimo", "deepseek", "opencode"}
    if provider not in available:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    SystemSetting.set(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER, provider)
    return {"status": "ok", "default_provider": provider}


# ─── RAG Embedding 设置（本地 / 在线切换）────────────────

def _mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:6] + "..." + key[-4:] if len(key) > 12 else "***"


@router.get("/rag")
async def get_rag_settings(db: Session = Depends(get_db)):
    """读取 RAG embedding 设置（api_key 只返回是否已配置与掩码）"""
    mode = SystemSetting.get(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, "local") or "local"
    base_url = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, "")
    api_key = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, "")
    model = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "")
    return {
        "mode": mode,
        "base_url": base_url,
        "api_key_masked": _mask_key(api_key),
        "has_api_key": bool(api_key),
        "model": model,
    }


@router.put("/rag")
async def update_rag_settings(req: RagSettingsUpdate, db: Session = Depends(get_db)):
    """更新 RAG embedding 设置。

    - mode: "local" | "online"
    - api_key 传空字符串表示清空；不传则该字段保持不变
    """
    if req.mode is not None:
        mode = req.mode.strip().lower()
        if mode not in ("local", "online"):
            raise HTTPException(status_code=400, detail="mode 必须是 local 或 online")
        SystemSetting.set(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, mode)
    if req.base_url is not None:
        SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, req.base_url.strip())
    if req.model is not None:
        SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_MODEL, req.model.strip())
    if req.api_key is not None:
        SystemSetting.set(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, req.api_key.strip())

    return {"status": "ok", "settings": await get_rag_settings(db)}


@router.post("/rag/test")
async def test_rag_settings(req: RagTestRequest, db: Session = Depends(get_db)):
    """测试 embedding 是否可用；不传字段则用已保存的值。"""
    mode = (req.mode or SystemSetting.get(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, "local") or "local").lower()

    if mode == "online":
        base_url = req.base_url if req.base_url is not None else SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, "")
        api_key = req.api_key if req.api_key is not None else SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, "")
        model = req.model if req.model is not None else SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "")
        if not api_key or not model:
            return {"ok": False, "mode": "online", "message": "请先填写在线 embedding 的 API Key 与模型名"}
        try:
            from rag.online_embedder import OnlineEmbedder
            embedder = OnlineEmbedder(base_url=base_url, api_key=api_key, model=model)
            info = embedder.test()
            return {"ok": True, "mode": "online", "message": f"连接成功（维度 {info['dimension']}）", "dimension": info["dimension"], "model": model}
        except Exception as e:
            return {"ok": False, "mode": "online", "message": f"连接失败: {e}"}

    # local
    try:
        import importlib.util
        from rag.model_manager import ModelManager
        mgr = ModelManager()
        if importlib.util.find_spec("sentence_transformers") is None:
            return {"ok": False, "mode": "local", "message": "未安装 sentence-transformers，请运行 tools/install_rag_cpu 脚本"}
        if not mgr.is_model_downloaded():
            return {"ok": False, "mode": "local", "message": "本地 embedding 模型未下载，请在模型管理里下载 moka-ai/m3e-base"}
        from rag.embedder import LocalEmbedder
        vec = LocalEmbedder().embed_single("CozyWriter RAG 连通性测试")
        return {"ok": True, "mode": "local", "message": f"本地模型可用（维度 {len(vec)}）", "dimension": len(vec), "model": mgr.model_name}
    except Exception as e:
        return {"ok": False, "mode": "local", "message": f"本地模型不可用: {e}"}


@router.post("/rag/reset")
async def reset_rag_collections():
    """清空 RAG 向量库。

    切换 embedding 模式/模型后向量维度会变化，旧向量无法混用，需要重置；
    下次写入时会自动重建空 collection。
    """
    try:
        from rag.knowledge_base import KnowledgeBase
        deleted = KnowledgeBase.reset_all_collections()
        return {"status": "ok", "deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置失败: {e}")

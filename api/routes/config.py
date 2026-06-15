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
    default_provider: str
    # 当前激活的 provider 实际使用的模型名（用于前端工具栏展示）
    current_model: str = ""


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

    # 根据 default_provider 找到当前实际使用的模型名
    # 优先级：xxx_MODEL 环境变量 > provider 内置默认模型名
    default_models = {
        "anthropic": lambda e: "claude-sonnet-4-5",
        "openai": lambda e: e.get("OPENAI_MODEL", "gpt-4o"),
        "ollama": lambda e: e.get("OLLAMA_MODEL", "llama3.1"),
        "minimax": lambda e: e.get("MINIMAX_MODEL", "MiniMax-Text-01"),
        "mimo": lambda e: e.get("MIMO_MODEL", "mimo-vl-7b"),
    }
    resolver = default_models.get(default_provider.lower())
    current_model = resolver(env_vars) if resolver else ""

    return ConfigStatusResponse(
        anthropic_configured=bool(env_vars.get("ANTHROPIC_API_KEY", "")),
        openai_configured=bool(env_vars.get("OPENAI_API_KEY", "")),
        ollama_configured=bool(env_vars.get("OLLAMA_BASE_URL", "")),
        minimax_configured=bool(env_vars.get("MINIMAX_API_KEY", "")),
        mimo_configured=bool(env_vars.get("MIMO_API_KEY", "")),
        default_provider=default_provider,
        current_model=current_model,
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
    available = {"anthropic", "openai", "ollama", "minimax", "mimo"}
    if provider not in available:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    SystemSetting.set(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER, provider)
    return {"status": "ok", "default_provider": provider}

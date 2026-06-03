"""Provider 配置保存 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path


router = APIRouter(prefix="/api/config", tags=["配置"])


class SaveProviderRequest(BaseModel):
    provider: str  # anthropic / openai / ollama / MiniMax
    api_key: str | None = None
    base_url: str | None = None  # 仅 ollama / MiniMax 可选
    model: str | None = None     # MiniMax 可选


class ConfigStatusResponse(BaseModel):
    anthropic_configured: bool
    openai_configured: bool
    ollama_configured: bool
    MiniMax_configured: bool
    default_provider: str


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
    """更新 .env 文件"""
    env_path = Path(".env")
    env_vars = _load_env()
    env_vars.update(updates)

    lines = []
    for key, value in env_vars.items():
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines), encoding="utf-8")


@router.get("/status", response_model=ConfigStatusResponse)
async def get_config_status():
    """查询当前 provider 配置状态"""
    env_vars = _load_env()
    return ConfigStatusResponse(
        anthropic_configured=bool(env_vars.get("ANTHROPIC_API_KEY", "")),
        openai_configured=bool(env_vars.get("OPENAI_API_KEY", "")),
        ollama_configured=bool(env_vars.get("OLLAMA_BASE_URL", "")),
        MiniMax_configured=bool(env_vars.get("MINIMAX_API_KEY", "")),
        default_provider=env_vars.get("DEFAULT_LLM_PROVIDER", "anthropic"),
    )


@router.post("/save-provider")
async def save_provider(req: SaveProviderRequest):
    """保存用户选择的 provider 和 API Key 到 .env"""
    if req.provider == "anthropic":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is required")
        _save_env({
            "ANTHROPIC_API_KEY": req.api_key,
            "DEFAULT_LLM_PROVIDER": "anthropic",
        })
    elif req.provider == "openai":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")
        _save_env({
            "OPENAI_API_KEY": req.api_key,
            "DEFAULT_LLM_PROVIDER": "openai",
        })
    elif req.provider == "ollama":
        base_url = req.base_url or "http://localhost:11434"
        _save_env({
            "OLLAMA_BASE_URL": base_url,
            "DEFAULT_LLM_PROVIDER": "ollama",
        })
    elif req.provider == "MiniMax":
        if not req.api_key:
            raise HTTPException(status_code=400, detail="MINIMAX_API_KEY is required")
        updates = {
            "MINIMAX_API_KEY": req.api_key,
            "DEFAULT_LLM_PROVIDER": "MiniMax",
        }
        if req.base_url:
            updates["MINIMAX_BASE_URL"] = req.base_url
        if req.model:
            updates["MINIMAX_MODEL"] = req.model
        _save_env(updates)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    return {"status": "ok", "provider": req.provider}

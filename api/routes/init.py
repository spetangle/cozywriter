"""初始化状态检查 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from config import settings
from rag.model_manager import ModelManager


router = APIRouter(prefix="/api/init", tags=["初始化"])


class InitStatusResponse(BaseModel):
    needs_setup: bool
    provider_configured: bool
    model_downloaded: bool
    providers_available: list[str]


def _check_provider_configured() -> bool:
    """检查是否至少配置了一个 LLM provider"""
    if settings.anthropic_api_key:
        return True
    if settings.openai_api_key:
        return True
    # Ollama 不需要 key，只要有 URL 就行
    if settings.ollama_base_url:
        return True
    return False


@router.get("/status", response_model=InitStatusResponse)
async def get_init_status():
    """
    查询初始化状态
    前端每次加载页面时调用，决定是否显示 Setup Wizard
    """
    provider_configured = _check_provider_configured()
    model_downloaded = ModelManager().is_model_downloaded()

    needs_setup = not (provider_configured and model_downloaded)

    return InitStatusResponse(
        needs_setup=needs_setup,
        provider_configured=provider_configured,
        model_downloaded=model_downloaded,
        providers_available=["anthropic", "openai", "ollama"],
    )

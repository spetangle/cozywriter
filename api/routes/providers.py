"""服务商管理 CRUD API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.provider import Provider
from storage.models.system_setting import SystemSetting
from logger import logger

router = APIRouter(prefix="/api/providers", tags=["服务商"])


# ─── Pydantic 模型 ────────────────────────────────────

class ProviderCreate(BaseModel):
    id: str          # slug
    name: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    set_as_default: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class SetDefaultRequest(BaseModel):
    provider_id: str


# ─── 内置默认服务商配置（首次写入 DB 时的种子数据） ───

SEED_PROVIDERS: list[dict] = [
    {
        "id": "minimax",
        "name": "MiniMax",
        "base_url": "https://api.minimaxi.com/anthropic",
        "model": "MiniMax-M2.7",
    },
    {
        "id": "mimo",
        "name": "Xiaomi MiMo",
        "base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "model": "mimo-v2.5-pro",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "base_url": "",
        "model": "claude-sonnet-4-20250514",
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "base_url": "",
        "model": "gpt-4o",
    },
    {
        "id": "ollama",
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434",
        "model": "",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat-v4-flash",
    },
]


def _ensure_seeded(db: Session):
    """确保种子数据存在，从 .env 补全 api_key / base_url"""
    try:
        from config import settings as app_settings
    except Exception:
        app_settings = None

    for seed in SEED_PROVIDERS:
        existing = db.query(Provider).filter(Provider.id == seed["id"]).first()
        if existing:
            continue

        api_key = ""
        base_url = seed.get("base_url", "")
        model = seed.get("model", "")
        if app_settings:
            pid = seed["id"]
            if pid == "anthropic":
                api_key = app_settings.anthropic_api_key or ""
            elif pid == "openai":
                api_key = app_settings.openai_api_key or ""
            elif pid == "minimax":
                api_key = app_settings.minimax_api_key or ""
                base_url = base_url or app_settings.minimax_base_url
                model = model or app_settings.minimax_model
            elif pid == "mimo":
                api_key = app_settings.mimo_api_key or ""
                base_url = base_url or app_settings.mimo_base_url
                model = model or app_settings.mimo_model
            elif pid == "ollama":
                base_url = base_url or app_settings.ollama_base_url
            elif pid == "deepseek":
                api_key = app_settings.deepseek_api_key or ""
                base_url = base_url or app_settings.deepseek_base_url
                model = model or app_settings.deepseek_model

        db.add(Provider(
            id=seed["id"],
            name=seed["name"],
            api_key=api_key,
            base_url=base_url,
            model=model,
            is_default=False,
        ))

    if db.dirty:
        default = ""
        if app_settings:
            default = (app_settings.default_llm_provider or "").strip().lower()
        if not default:
            default = "minimax"
        target = db.query(Provider).filter(Provider.id == default).first()
        if target:
            target.is_default = True
        else:
            first = db.query(Provider).first()
            if first:
                first.is_default = True
        db.commit()


# ─── API 端点 ─────────────────────────────────────────

@router.get("")
def list_providers(db: Session = Depends(get_db)):
    """获取全部服务商（含当前默认）"""
    _ensure_seeded(db)
    providers = db.query(Provider).order_by(Provider.id).all()
    return [p.to_dict() for p in providers]


@router.get("/{provider_id}")
def get_provider(provider_id: str, db: Session = Depends(get_db)):
    """获取单个服务商详情"""
    _ensure_seeded(db)
    p = db.query(Provider).filter(Provider.id == provider_id).first()
    if not p:
        raise HTTPException(404, f"服务商 {provider_id} 不存在")
    return p.to_dict()


@router.post("")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    """新建服务商"""
    _ensure_seeded(db)
    existing = db.query(Provider).filter(Provider.id == body.id).first()
    if existing:
        raise HTTPException(409, f"服务商 {body.id} 已存在")
    p = Provider(
        id=body.id,
        name=body.name,
        api_key=body.api_key or "",
        base_url=body.base_url or "",
        model=body.model or "",
        is_default=False,
    )
    db.add(p)
    if body.set_as_default:
        db.query(Provider).update({Provider.is_default: False})
        p.is_default = True
    db.commit()
    db.refresh(p)
    return p.to_dict()


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: ProviderUpdate, db: Session = Depends(get_db)):
    """更新服务商信息"""
    _ensure_seeded(db)
    p = db.query(Provider).filter(Provider.id == provider_id).first()
    if not p:
        raise HTTPException(404, f"服务商 {provider_id} 不存在")
    if body.name is not None:
        p.name = body.name
    if body.api_key is not None:
        p.api_key = body.api_key
    if body.base_url is not None:
        p.base_url = body.base_url
    if body.model is not None:
        p.model = body.model
    db.commit()
    db.refresh(p)
    return p.to_dict()


@router.post("/set-default")
def set_default_provider(body: SetDefaultRequest, db: Session = Depends(get_db)):
    """切换默认服务商"""
    _ensure_seeded(db)
    target = db.query(Provider).filter(Provider.id == body.provider_id).first()
    if not target:
        raise HTTPException(404, f"服务商 {body.provider_id} 不存在")
    db.query(Provider).update({Provider.is_default: False})
    target.is_default = True
    # 同步写 SystemSetting，保持向后兼容
    SystemSetting.set(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER, body.provider_id)
    db.commit()
    return {"ok": True, "default": body.provider_id}


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    """删除服务商（不能删除当前默认）"""
    _ensure_seeded(db)
    p = db.query(Provider).filter(Provider.id == provider_id).first()
    if not p:
        raise HTTPException(404, f"服务商 {provider_id} 不存在")
    if p.is_default:
        raise HTTPException(400, "不能删除当前默认服务商，请先切换默认")
    db.delete(p)
    db.commit()
    return {"ok": True}


class TestConnectionRequest(BaseModel):
    provider_id: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ListModelsRequest(BaseModel):
    provider_id: str
    api_key: str | None = None
    base_url: str | None = None


@router.post("/list-models")
def list_available_models(body: ListModelsRequest, db: Session = Depends(get_db)):
    """获取服务商的可用模型列表（支持 DeepSeek 等提供 list_models 接口的服务商）"""
    _ensure_seeded(db)
    p = db.query(Provider).filter(Provider.id.ilike(body.provider_id)).first()
    if not p:
        raise HTTPException(404, f"服务商 {body.provider_id} 不存在")

    api_key = body.api_key if body.api_key is not None else p.api_key
    base_url = body.base_url if body.base_url is not None else p.base_url

    if not api_key and p.id != "ollama":
        return {"ok": False, "message": "API Key 为空，请先配置", "models": []}

    from llm.factory import LLMFactory

    try:
        provider_cls = LLMFactory._providers.get(p.id.lower())
        if not provider_cls:
            return {"ok": False, "message": f"不支持的服务商类型: {p.id}", "models": []}

        if not hasattr(provider_cls, "list_models"):
            # 对于不支持 list_models 的服务商，返回硬编码的常用模型列表
            fallback_models = []
            if p.id.lower() == "deepseek":
                from llm.deepseek_provider import DeepSeekProvider
                fallback_models = [{"id": m, "name": m} for m in DeepSeekProvider.SUPPORTED_MODELS]
            elif p.id.lower() == "openai":
                fallback_models = [
                    {"id": "gpt-4o", "name": "gpt-4o"},
                    {"id": "gpt-4o-mini", "name": "gpt-4o-mini"},
                    {"id": "gpt-4-turbo", "name": "gpt-4-turbo"},
                    {"id": "gpt-4", "name": "gpt-4"},
                    {"id": "gpt-3.5-turbo", "name": "gpt-3.5-turbo"},
                ]
            elif p.id.lower() == "anthropic":
                fallback_models = [
                    {"id": "claude-sonnet-4-20250514", "name": "claude-sonnet-4-20250514"},
                    {"id": "claude-opus-4-20250514", "name": "claude-opus-4-20250514"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "claude-3-5-sonnet-20241022"},
                    {"id": "claude-3-opus-20240229", "name": "claude-3-opus-20240229"},
                    {"id": "claude-3-sonnet-20240229", "name": "claude-3-sonnet-20240229"},
                    {"id": "claude-3-haiku-20240307", "name": "claude-3-haiku-20240307"},
                ]
            elif p.id.lower() == "minimax":
                fallback_models = [
                    {"id": "MiniMax-M2.7", "name": "MiniMax-M2.7"},
                    {"id": "MiniMax-M3", "name": "MiniMax-M3"},
                ]
            elif p.id.lower() == "mimo":
                fallback_models = [
                    {"id": "mimo-v2.5-pro", "name": "mimo-v2.5-pro"},
                ]
            return {
                "ok": True,
                "message": "使用内置推荐模型列表（该服务商暂未提供动态获取接口）",
                "models": fallback_models,
                "fallback": True,
            }

        pid_lower = p.id.lower()
        if pid_lower == "deepseek":
            provider_instance = provider_cls(
                api_key=api_key, base_url=base_url, check_balance=False, use_json_output=False
            )
        elif pid_lower == "ollama":
            provider_instance = provider_cls(base_url=base_url)
        elif pid_lower in ("anthropic", "openai"):
            provider_instance = provider_cls(api_key=api_key)
        else:
            provider_instance = provider_cls(api_key=api_key, base_url=base_url)

        models = provider_instance.list_models()
        formatted_models = []
        for m in models:
            mid = m.get("id", m.get("name", ""))
            mname = m.get("name", mid)
            formatted_models.append({"id": mid, "name": mname})
        return {
            "ok": True,
            "message": f"成功获取 {len(formatted_models)} 个可用模型",
            "models": formatted_models,
            "fallback": False,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"获取模型列表失败: {e}")
        return {
            "ok": False,
            "message": f"获取模型列表失败: {str(e)}",
            "models": [],
            "error": str(e),
        }


@router.post("/test-connection")
def test_connection(body: TestConnectionRequest, db: Session = Depends(get_db)):
    """测试服务商连通性"""
    _ensure_seeded(db)
    p = db.query(Provider).filter(Provider.id.ilike(body.provider_id)).first()
    if not p:
        raise HTTPException(404, f"服务商 {body.provider_id} 不存在")

    api_key = body.api_key if body.api_key is not None else p.api_key
    base_url = body.base_url if body.base_url is not None else p.base_url
    model = body.model if body.model is not None else p.model

    if not api_key and p.id != "ollama":
        return {"ok": False, "message": "API Key 为空，请先配置"}

    import time
    from llm.factory import LLMFactory

    try:
        provider_cls = LLMFactory._providers.get(p.id.lower())
        if not provider_cls:
            return {"ok": False, "message": f"不支持的服务商类型: {p.id}"}

        if p.id.lower() == "deepseek":
            provider_instance = provider_cls(api_key=api_key, base_url=base_url, model=model, check_balance=False, use_json_output=False)
        else:
            provider_instance = provider_cls(api_key=api_key, base_url=base_url, model=model)

        extra_info = {}

        if p.id.lower() == "deepseek":
            balance_info = provider_instance.get_balance()
            extra_info["balance"] = balance_info

        if hasattr(provider_instance, "list_models"):
            try:
                models = provider_instance.list_models()
                if models:
                    model_names = [m.get("id", m.get("name", str(m))) for m in models[:10]]
                    extra_info["models"] = {
                        "count": len(models),
                        "available": model_names,
                    }
            except Exception as e:
                logger.error(f"获取模型列表失败: {e}")

        t0 = time.time()
        response = provider_instance.generate(
            prompt="你好",
            system_prompt="用中文回复，不超过10个字",
            max_tokens=200,
            temperature=0,
        )
        duration_ms = (time.time() - t0) * 1000

        result = {
            "ok": True,
            "message": f"连接成功！延迟 {duration_ms:.0f}ms",
            "duration_ms": duration_ms,
            "response": response.strip(),
        }
        if extra_info:
            result.update(extra_info)

        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "message": f"连接失败: {str(e)}",
            "error": str(e),
        }

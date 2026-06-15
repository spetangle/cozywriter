"""服务商管理 CRUD API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.provider import Provider
from storage.models.system_setting import SystemSetting

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
]


def _ensure_seeded(db: Session):
    """如果 providers 表为空，写入种子数据并从 .env 补全 api_key / base_url"""
    if db.query(Provider).count() > 0:
        return
    try:
        from config import settings as app_settings
    except Exception:
        app_settings = None

    for seed in SEED_PROVIDERS:
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

        db.add(Provider(
            id=seed["id"],
            name=seed["name"],
            api_key=api_key,
            base_url=base_url,
            model=model,
            is_default=False,
        ))
    # 把当前 .env 中的 default_llm_provider 设为默认
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

"""LLM 超参数配置 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from storage.database import get_db
from storage.models.llm_hyperparams import LLMHyperparamPreset
from llm.hyperparam_service import HyperparamService
from llm.factory import LLMFactory

router = APIRouter(prefix="/api/llm-hyperparams", tags=["LLM 超参数配置"])


class HyperparamPresetCreate(BaseModel):
    provider: str
    task_type: str
    name: str
    description: str = ""
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    top_k: int = 0
    repetition_penalty: float = 1.0
    extra_params: dict = {}
    is_active: bool = True


class HyperparamPresetUpdate(HyperparamPresetCreate):
    id: int


@router.get("/presets")
def list_presets(provider: str = None, db=Depends(get_db)):
    """列出所有超参配置"""
    return HyperparamService.list_presets(db, provider)


@router.get("/presets/{provider}/{task_type}")
def get_preset(provider: str, task_type: str, db=Depends(get_db)):
    """获取指定 provider 和 task_type 的超参配置"""
    preset = HyperparamService.get_preset(db, provider, task_type)
    if not preset:
        raise HTTPException(status_code=404, detail="超参配置不存在")
    return preset.to_dict()


@router.post("/presets")
def create_preset(data: HyperparamPresetCreate, db=Depends(get_db)):
    """创建超参配置"""
    if data.provider not in LLMFactory.available_providers():
        raise HTTPException(status_code=400, detail=f"不支持的 provider: {data.provider}")
    if data.task_type not in ["default"] + [tt for tt in LLMHyperparamPreset.TASK_TYPES]:
        raise HTTPException(status_code=400, detail=f"不支持的 task_type: {data.task_type}")
    existing = db.query(LLMHyperparamPreset).filter(
        LLMHyperparamPreset.provider == data.provider,
        LLMHyperparamPreset.task_type == data.task_type,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{data.provider} 的 {data.task_type} 配置已存在")
    preset = HyperparamService.save_preset(db, data.dict())
    return preset.to_dict()


@router.put("/presets")
def update_preset(data: HyperparamPresetUpdate, db=Depends(get_db)):
    """更新超参配置"""
    if data.provider not in LLMFactory.available_providers():
        raise HTTPException(status_code=400, detail=f"不支持的 provider: {data.provider}")
    preset = HyperparamService.save_preset(db, data.dict())
    return preset.to_dict()


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, db=Depends(get_db)):
    """删除超参配置"""
    if not HyperparamService.delete_preset(db, preset_id):
        raise HTTPException(status_code=404, detail="超参配置不存在")
    return {"message": "删除成功"}


@router.post("/initialize")
def initialize_defaults(db=Depends(get_db)):
    """初始化默认超参配置"""
    HyperparamService.initialize_defaults(db)
    return {"message": "初始化完成"}


@router.get("/task-types")
def get_task_types():
    """获取所有支持的任务类型"""
    return {"task_types": LLMHyperparamPreset.TASK_TYPES}


@router.get("/providers")
def get_providers():
    """获取所有支持的 provider"""
    return {"providers": LLMFactory.available_providers()}
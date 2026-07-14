"""LLM 超参数配置服务"""
import json
from typing import Optional
from logger import logger
from storage.models.llm_hyperparams import LLMHyperparamPreset


class HyperparamService:
    """超参数配置服务"""

    DEFAULT_PRESETS = [
        # ========== OpenAI ==========
        {"provider": "openai", "task_type": "generate_character", "name": "角色生成", "description": "生成人物设定，需要丰富细节和创意", "temperature": 0.85, "top_p": 0.9, "max_tokens": 2048},
        {"provider": "openai", "task_type": "generate_outline", "name": "大纲生成", "description": "生成小说大纲，需要逻辑性和结构", "temperature": 0.7, "top_p": 0.95, "max_tokens": 4096},
        {"provider": "openai", "task_type": "generate_chapter_outline", "name": "细纲生成", "description": "生成章节细纲，需要详细场景设计", "temperature": 0.75, "top_p": 0.92, "max_tokens": 3072},
        {"provider": "openai", "task_type": "generate_chapter_text", "name": "正文生成", "description": "生成小说正文，需要流畅的叙事", "temperature": 0.8, "top_p": 0.9, "max_tokens": 8192},
        {"provider": "openai", "task_type": "review", "name": "评审", "description": "评审章节内容，需要客观分析", "temperature": 0.3, "top_p": 0.8, "max_tokens": 2048},
        {"provider": "openai", "task_type": "consistency_check", "name": "一致性检查", "description": "检查前后一致性，需要严谨", "temperature": 0.2, "top_p": 0.7, "max_tokens": 2048},
        {"provider": "openai", "task_type": "revision", "name": "修订", "description": "修订章节内容，需要保持风格一致", "temperature": 0.5, "top_p": 0.85, "max_tokens": 8192},
        {"provider": "openai", "task_type": "golden_3_check", "name": "黄金三章检查", "description": "检查开局质量，需要专业分析", "temperature": 0.3, "top_p": 0.8, "max_tokens": 2048},
        {"provider": "openai", "task_type": "post_chapter", "name": "章节后处理", "description": "弧光/关系/伏笔更新，需要细致分析", "temperature": 0.4, "top_p": 0.85, "max_tokens": 3072},
        {"provider": "openai", "task_type": "foreshadow_updater", "name": "伏笔更新", "description": "更新伏笔状态，需要逻辑判断", "temperature": 0.3, "top_p": 0.8, "max_tokens": 1024},
        {"provider": "openai", "task_type": "event_signature_extractor", "name": "事件签名抽取", "description": "抽取事件签名，需要简洁准确", "temperature": 0.2, "top_p": 0.7, "max_tokens": 512},
        {"provider": "openai", "task_type": "expander", "name": "扩写", "description": "扩写正文内容，需要丰富细节", "temperature": 0.7, "top_p": 0.9, "max_tokens": 6144},
        {"provider": "openai", "task_type": "compressor", "name": "缩写", "description": "缩写正文内容，需要保留核心", "temperature": 0.4, "top_p": 0.8, "max_tokens": 4096},
        {"provider": "openai", "task_type": "revision_decider", "name": "修订决策", "description": "决定是否修订，需要客观判断", "temperature": 0.2, "top_p": 0.7, "max_tokens": 512},
        {"provider": "openai", "task_type": "outline_reviewer", "name": "细纲评审", "description": "评审细纲，需要严格把关", "temperature": 0.3, "top_p": 0.8, "max_tokens": 1536},
        {"provider": "openai", "task_type": "default", "name": "默认配置", "description": "通用默认配置", "temperature": 0.7, "top_p": 0.9, "max_tokens": 4096},
        
        # ========== Anthropic ==========
        {"provider": "anthropic", "task_type": "generate_character", "name": "角色生成", "description": "生成人物设定，需要丰富细节和创意", "temperature": 0.85, "top_p": 0.9, "max_tokens": 2048},
        {"provider": "anthropic", "task_type": "generate_outline", "name": "大纲生成", "description": "生成小说大纲，需要逻辑性和结构", "temperature": 0.7, "top_p": 0.95, "max_tokens": 4096},
        {"provider": "anthropic", "task_type": "generate_chapter_outline", "name": "细纲生成", "description": "生成章节细纲，需要详细场景设计", "temperature": 0.75, "top_p": 0.92, "max_tokens": 3072},
        {"provider": "anthropic", "task_type": "generate_chapter_text", "name": "正文生成", "description": "生成小说正文，需要流畅的叙事", "temperature": 0.8, "top_p": 0.9, "max_tokens": 8192},
        {"provider": "anthropic", "task_type": "review", "name": "评审", "description": "评审章节内容，需要客观分析", "temperature": 0.3, "top_p": 0.8, "max_tokens": 2048},
        {"provider": "anthropic", "task_type": "consistency_check", "name": "一致性检查", "description": "检查前后一致性，需要严谨", "temperature": 0.2, "top_p": 0.7, "max_tokens": 2048},
        {"provider": "anthropic", "task_type": "revision", "name": "修订", "description": "修订章节内容，需要保持风格一致", "temperature": 0.5, "top_p": 0.85, "max_tokens": 8192},
        {"provider": "anthropic", "task_type": "default", "name": "默认配置", "description": "通用默认配置", "temperature": 0.7, "top_p": 0.9, "max_tokens": 4096},
        
        # ========== Ollama ==========
        {"provider": "ollama", "task_type": "generate_character", "name": "角色生成", "description": "生成人物设定，需要丰富细节和创意", "temperature": 0.85, "top_p": 0.9, "max_tokens": 2048, "repetition_penalty": 1.1},
        {"provider": "ollama", "task_type": "generate_outline", "name": "大纲生成", "description": "生成小说大纲，需要逻辑性和结构", "temperature": 0.7, "top_p": 0.95, "max_tokens": 4096, "repetition_penalty": 1.05},
        {"provider": "ollama", "task_type": "generate_chapter_outline", "name": "细纲生成", "description": "生成章节细纲，需要详细场景设计", "temperature": 0.75, "top_p": 0.92, "max_tokens": 3072, "repetition_penalty": 1.05},
        {"provider": "ollama", "task_type": "generate_chapter_text", "name": "正文生成", "description": "生成小说正文，需要流畅的叙事", "temperature": 0.8, "top_p": 0.9, "max_tokens": 8192, "repetition_penalty": 1.1},
        {"provider": "ollama", "task_type": "review", "name": "评审", "description": "评审章节内容，需要客观分析", "temperature": 0.3, "top_p": 0.8, "max_tokens": 2048},
        {"provider": "ollama", "task_type": "consistency_check", "name": "一致性检查", "description": "检查前后一致性，需要严谨", "temperature": 0.2, "top_p": 0.7, "max_tokens": 2048},
        {"provider": "ollama", "task_type": "revision", "name": "修订", "description": "修订章节内容，需要保持风格一致", "temperature": 0.5, "top_p": 0.85, "max_tokens": 8192, "repetition_penalty": 1.05},
        {"provider": "ollama", "task_type": "default", "name": "默认配置", "description": "通用默认配置", "temperature": 0.7, "top_p": 0.9, "max_tokens": 4096, "repetition_penalty": 1.05},
        
        # ========== MiniMax ==========
        {"provider": "minimax", "task_type": "generate_character", "name": "角色生成", "description": "生成人物设定", "temperature": 0.85, "top_p": 0.9, "max_tokens": 2048},
        {"provider": "minimax", "task_type": "generate_chapter_text", "name": "正文生成", "description": "生成小说正文", "temperature": 0.8, "top_p": 0.9, "max_tokens": 8192},
        {"provider": "minimax", "task_type": "default", "name": "默认配置", "description": "通用默认配置", "temperature": 0.7, "top_p": 0.9, "max_tokens": 4096},
        
        # ========== Mimo ==========
        {"provider": "mimo", "task_type": "generate_character", "name": "角色生成", "description": "生成人物设定", "temperature": 0.85, "top_p": 0.9, "max_tokens": 2048},
        {"provider": "mimo", "task_type": "generate_chapter_text", "name": "正文生成", "description": "生成小说正文", "temperature": 0.8, "top_p": 0.9, "max_tokens": 8192},
        {"provider": "mimo", "task_type": "default", "name": "默认配置", "description": "通用默认配置", "temperature": 0.7, "top_p": 0.9, "max_tokens": 4096},
    ]

    @classmethod
    def initialize_defaults(cls, db) -> None:
        """初始化默认超参配置"""
        for preset in cls.DEFAULT_PRESETS:
            existing = db.query(LLMHyperparamPreset).filter(
                LLMHyperparamPreset.provider == preset["provider"],
                LLMHyperparamPreset.task_type == preset["task_type"],
            ).first()
            if not existing:
                preset_obj = LLMHyperparamPreset(**preset)
                db.add(preset_obj)
                logger.info(f"[Hyperparam] 初始化预设: {preset['provider']} / {preset['task_type']}")
        db.commit()

    @classmethod
    def get_preset(cls, db, provider: str, task_type: str) -> Optional[LLMHyperparamPreset]:
        """获取指定 provider 和 task_type 的超参配置"""
        preset = db.query(LLMHyperparamPreset).filter(
            LLMHyperparamPreset.provider == provider,
            LLMHyperparamPreset.task_type == task_type,
            LLMHyperparamPreset.is_active == 1,
        ).first()
        if preset:
            return preset
        return db.query(LLMHyperparamPreset).filter(
            LLMHyperparamPreset.provider == provider,
            LLMHyperparamPreset.task_type == "default",
            LLMHyperparamPreset.is_active == 1,
        ).first()

    @classmethod
    def get_params(cls, db, provider: str, task_type: str) -> dict:
        """获取指定 provider 和 task_type 的参数字典"""
        preset = cls.get_preset(db, provider, task_type)
        if preset:
            return preset.get_params()
        return {"temperature": 0.7, "top_p": 0.9, "max_tokens": 4096}

    @classmethod
    def list_presets(cls, db, provider: str = None) -> list[dict]:
        """列出所有超参配置"""
        query = db.query(LLMHyperparamPreset)
        if provider:
            query = query.filter(LLMHyperparamPreset.provider == provider)
        return [p.to_dict() for p in query.all()]

    @classmethod
    def save_preset(cls, db, data: dict) -> LLMHyperparamPreset:
        """保存超参配置（新增或更新）"""
        preset_id = data.get("id")
        if preset_id:
            preset = db.query(LLMHyperparamPreset).filter(LLMHyperparamPreset.id == preset_id).first()
            if preset:
                for key, value in data.items():
                    if hasattr(preset, key) and key != "id":
                        setattr(preset, key, value)
                db.commit()
                logger.info(f"[Hyperparam] 更新预设: id={preset_id}")
                return preset
        preset = LLMHyperparamPreset(**{k: v for k, v in data.items() if k != "id"})
        db.add(preset)
        db.commit()
        logger.info(f"[Hyperparam] 新增预设: {preset.provider} / {preset.task_type}")
        return preset

    @classmethod
    def delete_preset(cls, db, preset_id: int) -> bool:
        """删除超参配置"""
        preset = db.query(LLMHyperparamPreset).filter(LLMHyperparamPreset.id == preset_id).first()
        if preset:
            db.delete(preset)
            db.commit()
            logger.info(f"[Hyperparam] 删除预设: id={preset_id}")
            return True
        return False
"""Xiaomi MiMo Provider (小米 MiMo 大模型)

小米 MiMo 大模型支持两种协议：
1. OpenAI 兼容协议：https://token-plan-cn.xiaomimimo.com/v1
2. Anthropic 兼容协议：https://token-plan-cn.xiaomimimo.com/anthropic

可用模型：
- mimo-v2.5-pro
- mimo-v2.5
- mimo-v2.5-asr
- mimo-v2.5-tts-voiceclone
- mimo-v2.5-tts-voicedesign
- mimo-v2.5-tts
- mimo-v2-pro
- mimo-v2-omni
- mimo-v2-tts

我们选择使用 Anthropic 兼容协议，与 MiniMax 保持一致。
"""
import time
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
import anthropic


class MimoProvider(LLMProvider):
    # MiMo Anthropic 兼容接口
    DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/anthropic"
    # 默认模型：mimo-v2.5-pro
    DEFAULT_MODEL = "mimo-v2.5-pro"
    # 上下文窗口：根据 MiMo 文档，v2.5 系列支持 128K 上下文
    CONTEXT_WINDOW = 128_000

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.mimo_api_key
        self.model = model or getattr(settings, "mimo_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "mimo_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "mimo"

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=600.0,  # 10 分钟，LLM 长文本兜底
                max_retries=2,  # SDK 内置重试
            )
        return self._client

    def _recommended_max_tokens(self) -> int:
        """根据模型返回推荐的 max_tokens"""
        # MiMo v2.5 系列支持 128K 上下文
        return 131072

    def _build_thinking_param(self) -> dict | None:
        """
        构建 thinking 参数：MiMo 可能支持 thinking，但为了兼容性，统一传 disabled
        """
        return {"type": "disabled"}

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        max_tokens = kwargs.get("max_tokens") or self._recommended_max_tokens()
        temperature = kwargs.get("temperature", 1.0)
        task_type = kwargs.get("task_type", "generate")
        messages = [{"role": "user", "content": prompt}]

        # 日志：记录完整 prompt（之前只截断 80 字会导致请求信息不全）
        #    超过 500 字符仍截断避免刷屏；完整内容另会通过 log_llm_payload() 入 log
        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:mimo] → {self.model} max_tokens={max_tokens} "
            f"base={self.base_url} task={task_type} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            # 构建请求参数
            create_kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
                "thinking": self._build_thinking_param(),  # 显式关 thinking
            }
            if system_prompt:
                create_kwargs["system"] = system_prompt

            response = client.messages.create(**create_kwargs)

            # 提取所有 type=text 的块，按顺序拼接
            # 跳过 type=thinking / type=tool_use 等非文本块
            parts = []
            for block in (response.content or []):
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    parts.append(getattr(block, "text", "") or "")
                # thinking/tool_use/tool_result 块直接跳过

            if not parts:
                # 模型只返回了 thinking 而无 text
                block_types = [getattr(b, "type", "?") for b in (response.content or [])]
                logger.error(
                    f"[LLM:mimo] 返回无 text 块，块类型={block_types} "
                    f"stop_reason={getattr(response, 'stop_reason', '?')}"
                )
                raise RuntimeError(
                    f"MiMo 返回无 text 块（可能 thinking 占满 max_tokens）。"
                    f"块类型: {block_types}, stop_reason: {getattr(response, 'stop_reason', '?')}"
                )

            text = "".join(parts)
            duration_ms = (time.time() - t0) * 1000
            # 响应预览：压缩空白后不超 300 字符，避免 log 一行被拆成多行
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:mimo] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} stop_reason={getattr(response, 'stop_reason', '?')} "
                f"response={response_preview_oneline!r}"
            )
            # 完整 payload 入 log 文件
            log_llm_payload(
                provider=self.provider_name,
                model=self.model,
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=prompt,
                response_text=text,
                duration_ms=duration_ms,
                success=True,
                extra={
                    "stop_reason": getattr(response, "stop_reason", None),
                    "input_tokens": getattr(getattr(response, "usage", None), "input_tokens", None),
                    "output_tokens": getattr(getattr(response, "usage", None), "output_tokens", None),
                    "content_blocks": [
                        getattr(b, "type", "?") for b in (response.content or [])
                    ],
                },
            )
            return text
        except anthropic.AuthenticationError as e:
            logger.error(f"[LLM:mimo] 401 鉴权失败: {e}")
            raise RuntimeError(
                "MiMo 鉴权失败 (401)。请检查 .env 中 MIMO_API_KEY 是否正确。"
            ) from e
        except anthropic.PermissionDeniedError as e:
            logger.error(f"[LLM:mimo] 403 模型无权访问: {self.model} ({e})")
            raise RuntimeError(
                f"MiMo 403: 无权访问模型 '{self.model}'。"
                f"请确认模型名称正确，可用模型：mimo-v2.5-pro, mimo-v2.5, mimo-v2.5-asr, "
                f"mimo-v2.5-tts-voiceclone, mimo-v2.5-tts-voicedesign, mimo-v2.5-tts, "
                f"mimo-v2-pro, mimo-v2-omni, mimo-v2-tts"
            ) from e
        except anthropic.NotFoundError as e:
            logger.error(f"[LLM:mimo] 404 模型/URL 错误: {self.model} @ {self.base_url} ({e})")
            raise RuntimeError(
                f"MiMo 404: 模型 '{self.model}' 不存在或 base_url '{self.base_url}' 错误。"
                f"请确认 base_url 是否正确：{self.DEFAULT_BASE_URL}"
            ) from e
        except anthropic.RateLimitError as e:
            logger.warning(f"[LLM:mimo] 429 限流: {e}")
            raise RuntimeError("MiMo 触发限流 (429)，请稍后重试。") from e
        except anthropic.APIStatusError as e:
            # 其他 4xx/5xx
            logger.error(
                f"[LLM:mimo] ← {self.model} API 错误 status={e.status_code} body={e.body}"
            )
            raise RuntimeError(
                f"MiMo API 错误 (status={e.status_code}): {e.message or e.body}"
            ) from e
        except anthropic.APIConnectionError as e:
            logger.error(
                f"[LLM:mimo] 网络异常 duration={(time.time()-t0)*1000:.0f}ms err={e}",
                exc_info=True,
            )
            raise RuntimeError(
                f"MiMo 网络请求失败（{self.base_url}）: {e}"
            ) from e
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:mimo] ← {self.model} FAIL duration={duration_ms:.0f}ms: {e}",
                exc_info=True,
            )
            # 失败也记 payload
            log_llm_payload(
                provider=self.provider_name,
                model=self.model,
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=prompt,
                response_text="",
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )
            raise

    def get_context_window(self) -> int:
        return self.CONTEXT_WINDOW
"""OpenCode Provider

OpenCode 提供 Anthropic Messages API 兼容接口，可直接复用 anthropic SDK。
仅在用户显式开启 OpenCode Go 时可用（见 config.opencode_enabled）。

配置（.env）：
- OPENCODE_API_KEY     API Key
- OPENCODE_BASE_URL    默认 https://opencode.ai/anthropic
- OPENCODE_MODEL       默认 big-pickle
- OPENCODE_ENABLED     是否启用（true/false，默认 false）
"""
import time

from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
from llm.usage_tracker import record_llm_usage, extract_usage_from_anthropic_response

try:
    import anthropic
except ImportError:  # pragma: no cover - 依赖缺失时给出清晰错误
    anthropic = None


class OpencodeProvider(LLMProvider):
    DEFAULT_BASE_URL = "https://opencode.ai/anthropic"
    DEFAULT_MODEL = "big-pickle"
    CONTEXT_WINDOW = 200_000

    SUPPORTED_MODELS = [
        "big-pickle",
        "claude-sonnet-4-5",
        "claude-opus-4-1",
        "gpt-5",
        "gpt-5-mini",
        "gemini-2.5-pro",
        "qwen3-coder",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        if anthropic is None:
            raise RuntimeError(
                "opencode provider 需要 anthropic SDK，请先安装：pip install anthropic"
            )

        self.api_key = api_key or getattr(settings, "opencode_api_key", "") or ""
        self.model = model or getattr(settings, "opencode_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "opencode_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "opencode"

    def _get_client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=600.0,
                max_retries=2,
            )
        return self._client

    def _recommended_max_tokens(self) -> int:
        return 131072

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        max_tokens = kwargs.get("max_tokens") or self._recommended_max_tokens()
        temperature = kwargs.get("temperature", 1.0)
        top_p = kwargs.get("top_p")
        task_type = kwargs.get("task_type", "generate")
        llm_call_id = kwargs.get("llm_call_id")
        task_id = kwargs.get("task_id")
        project_id = kwargs.get("project_id")
        messages = [{"role": "user", "content": prompt}]

        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:opencode] → {self.model} max_tokens={max_tokens} "
            f"base={self.base_url} task={task_type} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )

        usage_recorded = False
        t0 = time.time()
        try:
            create_kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if top_p is not None:
                create_kwargs["top_p"] = top_p
            if system_prompt:
                create_kwargs["system"] = system_prompt

            response = client.messages.create(**create_kwargs)

            parts = []
            for block in (response.content or []):
                if getattr(block, "type", None) == "text":
                    parts.append(getattr(block, "text", "") or "")

            if not parts:
                block_types = [getattr(b, "type", "?") for b in (response.content or [])]
                raise RuntimeError(
                    f"OpenCode 返回无 text 块（可能 thinking 占满 max_tokens）。"
                    f"块类型: {block_types}, stop_reason: {getattr(response, 'stop_reason', '?')}"
                )

            text = "".join(parts)
            duration_ms = (time.time() - t0) * 1000
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            logger.info(
                f"[LLM:opencode] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} stop_reason={getattr(response, 'stop_reason', '?')} "
                f"response={response_preview!r}"
            )
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
                    "content_blocks": [
                        getattr(b, "type", "?") for b in (response.content or [])
                    ],
                },
            )
            usage = extract_usage_from_anthropic_response(response)
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=True, project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id, **usage,
            )
            usage_recorded = True
            return text
        except anthropic.AuthenticationError as e:
            logger.error(f"[LLM:opencode] 401 鉴权失败: {e}")
            raise RuntimeError(
                "OpenCode 鉴权失败 (401)。请检查 .env 中 OPENCODE_API_KEY 是否正确。"
            ) from e
        except anthropic.PermissionDeniedError as e:
            logger.error(f"[LLM:opencode] 403 模型无权访问: {self.model} ({e})")
            raise RuntimeError(
                f"OpenCode 403: 无权访问模型 '{self.model}'，请确认模型名与账户权限。"
            ) from e
        except anthropic.NotFoundError as e:
            logger.error(f"[LLM:opencode] 404 模型/URL 错误: {self.model} @ {self.base_url} ({e})")
            raise RuntimeError(
                f"OpenCode 404: 模型 '{self.model}' 不存在或 base_url '{self.base_url}' 错误。"
            ) from e
        except anthropic.RateLimitError as e:
            logger.warning(f"[LLM:opencode] 429 限流: {e}")
            raise RuntimeError("OpenCode 触发限流 (429)，请稍后重试。") from e
        except anthropic.APIStatusError as e:
            logger.error(
                f"[LLM:opencode] ← {self.model} API 错误 status={e.status_code} body={e.body}"
            )
            raise RuntimeError(
                f"OpenCode API 错误 (status={e.status_code}): {e.message or e.body}"
            ) from e
        except anthropic.APIConnectionError as e:
            logger.error(
                f"[LLM:opencode] 网络异常 duration={(time.time()-t0)*1000:.0f}ms err={e}",
                exc_info=True,
            )
            raise RuntimeError(f"OpenCode 网络请求失败（{self.base_url}）: {e}") from e
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:opencode] ← {self.model} FAIL duration={duration_ms:.0f}ms: {e}",
                exc_info=True,
            )
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
        finally:
            if not usage_recorded:
                try:
                    elapsed_ms = (time.time() - t0) * 1000
                    record_llm_usage(
                        provider=self.provider_name, model=self.model, task_type=task_type,
                        duration_ms=elapsed_ms, success=False,
                        error="OpenCode request failed", project_id=project_id,
                        task_id=task_id, llm_call_id=llm_call_id,
                    )
                except Exception:
                    pass

    def get_context_window(self) -> int:
        return self.CONTEXT_WINDOW

    def list_models(self) -> list[dict]:
        """OpenCode 暂无稳定的模型列表接口，返回内置推荐列表。"""
        return [{"id": m, "name": m} for m in self.SUPPORTED_MODELS]

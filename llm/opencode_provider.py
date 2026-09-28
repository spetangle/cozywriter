"""OpenCode Go Provider

OpenCode Go 提供 OpenAI 兼容的 Chat Completions 接口：
    base_url = https://opencode.ai/zen/go/v1
需要：
- API Key（OPENCODE_API_KEY，形如 oc_sk_...）
- 会话头 x-opencode-session / x-opencode-client / x-opencode-caller，
  否则网关会返回 MissingSessionID

注意：OpenCode Go 上多为推理模型（如 deepseek-v4.1-flash），
reasoning 内容会占用 max_tokens。这里把 max_tokens 下限抬高，
并优先取 content；若只有 reasoning，则回退使用 reasoning 文本。

配置（.env）：
- OPENCODE_ENABLED     是否启用（true/false，默认 false）
- OPENCODE_API_KEY     API Key
- OPENCODE_BASE_URL    默认 https://opencode.ai/zen/go/v1
- OPENCODE_MODEL       默认 deepseek-v4.1-flash
"""
import time
import uuid

from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
from llm.usage_tracker import record_llm_usage, extract_usage_from_openai_response

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


class OpencodeProvider(LLMProvider):
    DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
    DEFAULT_MODEL = "deepseek-v4.1-flash"
    CONTEXT_WINDOW = 256_000
    # 推理模型会先消耗 reasoning tokens，给足预算避免 content 为空。
    MIN_MAX_TOKENS = 4096
    # JSON 任务失败重试时的下限（reasoning 占用后仍需留出 JSON 输出空间）。
    JSON_MIN_MAX_TOKENS = 8192

    SUPPORTED_MODELS = [
        "deepseek-v4.1-flash",
        "deepseek-v4-flash",
        "deepseek-v4.1",
        "minimax-m2.7",
        "qwen3-coder",
        "gpt-5",
        "claude-sonnet-4-5",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        if OpenAI is None:
            raise RuntimeError(
                "opencode provider 需要 openai SDK，请先安装：pip install openai"
            )

        self.api_key = api_key or getattr(settings, "opencode_api_key", "") or ""
        self.model = model or getattr(settings, "opencode_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "opencode_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = None
        # 复用同一个 session id，便于网关按会话路由/计费
        self.session_id = f"ses_{uuid.uuid4().hex[:24]}"

    @property
    def provider_name(self) -> str:
        return "opencode"

    def _get_client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=600.0,
                max_retries=2,
                default_headers={
                    "x-opencode-session": self.session_id,
                    "x-opencode-client": "cozywriter",
                    "x-opencode-caller": "cozywriter",
                },
            )
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        requested = kwargs.get("max_tokens") or self.MIN_MAX_TOKENS
        # JSON 任务 + 推理模型：给更高下限，避免 reasoning 占满导致 content 为空。
        floor = self.JSON_MIN_MAX_TOKENS if kwargs.get("use_json") else self.MIN_MAX_TOKENS
        max_tokens = max(int(requested), floor)
        temperature = kwargs.get("temperature", 0.7)
        task_type = kwargs.get("task_type", "generate")
        llm_call_id = kwargs.get("llm_call_id")
        task_id = kwargs.get("task_id")
        project_id = kwargs.get("project_id")
        use_json = kwargs.get("use_json")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:opencode] → {self.model} max_tokens={max_tokens} "
            f"base={self.base_url} task={task_type} json={use_json} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )

        usage_recorded = False
        t0 = time.time()
        try:
            api_kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if use_json:
                api_kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**api_kwargs)
            duration_ms = (time.time() - t0) * 1000

            choice = response.choices[0] if response.choices else None
            message = getattr(choice, "message", None) if choice else None
            text = (getattr(message, "content", None) or "") if message else ""
            reasoning = (getattr(message, "reasoning_content", None) or "") if message else ""
            finish_reason = getattr(choice, "finish_reason", None) if choice else None

            # 推理模型可能把 max_tokens 全用在 reasoning 上，content 为空。
            if not text.strip() and use_json:
                # JSON 任务绝不能把 reasoning 文本当结果返回；用更大预算 +
                # 明确约束重试一次。
                logger.warning(
                    f"[LLM:opencode] JSON 模式 content 为空，放大 max_tokens 重试 "
                    f"(finish={finish_reason}, 原 max_tokens={max_tokens}, reasoning_chars={len(reasoning)})"
                )
                retry_kwargs = dict(api_kwargs)
                retry_kwargs["max_tokens"] = max(max_tokens * 2, self.JSON_MIN_MAX_TOKENS)
                retry_kwargs["messages"] = messages + [{
                    "role": "user",
                    "content": "请不要输出任何思考过程，直接输出合法的 JSON（以 { 开头，以 } 结尾）。",
                }]
                response = client.chat.completions.create(**retry_kwargs)
                duration_ms = (time.time() - t0) * 1000
                choice = response.choices[0] if response.choices else None
                message = getattr(choice, "message", None) if choice else None
                text = (getattr(message, "content", None) or "") if message else ""
                reasoning = (getattr(message, "reasoning_content", None) or "") if message else ""
                finish_reason = getattr(choice, "finish_reason", None) if choice else None

            if not text.strip():
                if use_json:
                    raise RuntimeError(
                        f"OpenCode JSON 模式返回空响应（finish_reason={finish_reason}）。"
                        f"该模型可能为推理模型，请增大 max_tokens。"
                    )
                # 非 JSON 任务：允许回退 reasoning 文本，避免整条链路拿到空响应。
                if reasoning.strip():
                    logger.warning(
                        f"[LLM:opencode] content 为空，回退使用 reasoning 文本 "
                        f"(finish_reason={finish_reason}, reasoning_chars={len(reasoning)})"
                    )
                    text = reasoning

            if not text.strip():
                raise RuntimeError(
                    f"OpenCode 返回空响应（finish_reason={finish_reason}）。"
                    f"若为推理模型，请增大 max_tokens（当前 {max_tokens}）。"
                )

            response_preview = text if len(text) <= 300 else text[:300] + "..."
            logger.info(
                f"[LLM:opencode] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} finish={finish_reason} response={response_preview!r}"
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
                    "finish_reason": finish_reason,
                    "reasoning_chars": len(reasoning),
                    "usage": response.usage.model_dump() if response.usage else None,
                },
            )
            usage = extract_usage_from_openai_response(response)
            usage.pop("total_tokens", None)
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=True, project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id, **usage,
            )
            usage_recorded = True
            return text
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
        return [{"id": m, "name": m} for m in self.SUPPORTED_MODELS]

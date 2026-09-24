"""DeepSeek Provider (深度求索大模型)

官方文档：https://api.deepseek.com/zh-cn/
Anthropic API：https://api.deepseek.com/zh-cn/guides/anthropic_api

支持两种接入方式：
1. OpenAI 兼容协议 (默认)：通过官方 `openai` SDK 调用
   - Base URL：https://api.deepseek.com/v1
2. Anthropic Messages API 兼容协议：通过官方 `anthropic` SDK 调用
   - Base URL：https://api.deepseek.com/anthropic

- 模型：
    * deepseek-chat           (通用对话模型)
    * deepseek-chat-v2
    * deepseek-chat-v3
    * deepseek-chat-v3-preview
    * deepseek-chat-v4
    * deepseek-chat-v4-preview
    * deepseek-chat-v4-flash
    * deepseek-r1-chat        (R1 对话模型)
    * deepseek-r1-chat-preview (R1 预览版)
    * deepseek-llm-7b-chat
    * deepseek-llm-7b-chat-v1.5
    * deepseek-mo-v1-chat
    * deepseek-coder
    * deepseek-coder-v2
- 默认温度：0.7
- max_tokens 推荐：4096
- JSON Output：支持 response_format={"type": "json_object"}，强制返回 JSON
- 余额查询：GET https://api.deepseek.com/user/balance (独立接口)
- 模型列表：GET https://api.deepseek.com/v1/models (独立接口)
"""
import time
import httpx
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
from llm.usage_tracker import (
    record_llm_usage,
    extract_usage_from_openai_response,
    extract_usage_from_anthropic_response,
)


class DeepSeekProvider(LLMProvider):
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
    DEFAULT_MODEL = "deepseek-chat"
    CONTEXT_WINDOW = 128_000
    USE_JSON_OUTPUT = True
    MIN_BALANCE_WARNING = 10.0

    SUPPORTED_MODELS = [
        "deepseek-chat",
        "deepseek-chat-v2",
        "deepseek-chat-v3",
        "deepseek-chat-v3-preview",
        "deepseek-chat-v4",
        "deepseek-chat-v4-preview",
        "deepseek-chat-v4-flash",
        "deepseek-r1-chat",
        "deepseek-r1-chat-preview",
        "deepseek-llm-7b-chat",
        "deepseek-llm-7b-chat-v1.5",
        "deepseek-mo-v1-chat",
        "deepseek-coder",
        "deepseek-coder-v2",
    ]

    MODEL_ALIASES = {
        "deepseek-chat-v4-flash": "deepseek-v4-flash",
        "deepseek-chat-v4": "deepseek-v4-pro",
        "deepseek-chat-v4-preview": "deepseek-v4-pro",
        "deepseek-chat-v3": "deepseek-v4-flash",
        "deepseek-chat-v3-preview": "deepseek-v4-flash",
        "deepseek-chat-v2": "deepseek-v4-flash",
        "deepseek-chat": "deepseek-v4-flash",
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        use_json_output: bool = None,
        check_balance: bool = True,
    ):
        self.api_key = api_key or settings.deepseek_api_key
        self.model = model or getattr(settings, "deepseek_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "deepseek_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self.use_json_output = use_json_output if use_json_output is not None else self.USE_JSON_OUTPUT
        self.check_balance = check_balance
        self._client = None
        self._http_client = None
        self._use_anthropic = self.base_url.endswith("/anthropic")

        if not self._use_anthropic:
            self.model = self.MODEL_ALIASES.get(self.model, self.model)

    @property
    def provider_name(self) -> str:
        return "deepseek"

    def _get_client(self):
        if self._client is None:
            if self._use_anthropic:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=600.0,
                    max_retries=2,
                )
            else:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=600.0,
                    max_retries=2,
                )
        return self._client

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http_client

    def get_balance(self) -> dict:
        """查询账户余额

        返回格式：
        {
            "balance": 100.50,
            "currency": "CNY",
            "warning": False,
            "message": ""
        }
        """
        if not self.api_key:
            return {"balance": 0, "currency": "CNY", "warning": True, "message": "API Key 为空"}

        http_client = self._get_http_client()
        try:
            response = http_client.get("https://api.deepseek.com/user/balance")
            response.raise_for_status()
            data = response.json()
            balance = 0.0
            currency = "CNY"
            balance_infos = data.get("balance_infos", [])
            if balance_infos:
                for info in balance_infos:
                    if info.get("currency") == "CNY":
                        balance = float(info.get("total_balance", 0))
                        currency = "CNY"
                        break
                if not balance and balance_infos[0]:
                    balance = float(balance_infos[0].get("total_balance", 0))
                    currency = balance_infos[0].get("currency", "CNY")
            else:
                balance = float(data.get("balance", 0))
                currency = data.get("currency", "CNY")
            warning = balance < self.MIN_BALANCE_WARNING
            message = f"余额不足 {self.MIN_BALANCE_WARNING} 元" if warning else ""
            return {
                "balance": balance,
                "currency": currency,
                "warning": warning,
                "message": message,
            }
        except Exception as e:
            logger.error(f"[LLM:deepseek] 余额查询失败: {e}")
            return {"balance": 0, "currency": "CNY", "warning": True, "message": f"查询失败: {str(e)}"}

    def list_models(self) -> list[dict]:
        """获取可用模型列表"""
        if not self.api_key:
            return []

        http_client = self._get_http_client()
        try:
            response = http_client.get("https://api.deepseek.com/v1/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"[LLM:deepseek] 模型列表获取失败: {e}")
            return []

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        if self.check_balance:
            balance_info = self.get_balance()
            if balance_info.get("warning", False) and "查询失败" not in balance_info.get("message", ""):
                raise RuntimeError(
                    f"DeepSeek 余额不足：当前余额 {balance_info['balance']} 元，"
                    f"低于警告阈值 {self.MIN_BALANCE_WARNING} 元，请及时充值。"
                )

        client = self._get_client()
        task_type = kwargs.get("task_type", "generate")
        llm_call_id = kwargs.get("llm_call_id")
        task_id = kwargs.get("task_id")
        project_id = kwargs.get("project_id")
        use_json = self.use_json_output
        if "use_json" in kwargs:
            use_json = kwargs["use_json"]

        api_kwargs = {k: v for k, v in kwargs.items() if k not in ("task_type", "use_json", "project_id", "llm_call_id", "task_id")}

        if self._use_anthropic:
            return self._generate_anthropic(client, prompt, system_prompt, use_json, task_type, project_id, llm_call_id=llm_call_id, task_id=task_id, **api_kwargs)
        else:
            return self._generate_openai(client, prompt, system_prompt, use_json, task_type, project_id, llm_call_id=llm_call_id, task_id=task_id, **api_kwargs)

    def _generate_openai(self, client, prompt, system_prompt, use_json, task_type, project_id=None, llm_call_id=None, task_id=None, **kwargs):
        messages = []

        if system_prompt:
            if use_json and "json" not in system_prompt.lower():
                system_prompt += "\n\n请始终以 JSON 格式输出结果，不要包含任何额外的文字说明。"
            messages.append({"role": "system", "content": system_prompt})

        if use_json and "json" not in prompt.lower():
            prompt += "\n\n请以 JSON 格式输出结果。"
        messages.append({"role": "user", "content": prompt})

        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:deepseek] → {self.model} task={task_type} "
            f"json={use_json} max_tokens={kwargs.get('max_tokens', 4096)} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            kwargs_for_api = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 1.0),
            }

            if use_json:
                kwargs_for_api["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs_for_api)

            duration_ms = (time.time() - t0) * 1000
            text = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason

            # 如果 JSON 模式返回空响应，自动降级重试一次（不用 response_format）
            if use_json and not text.strip():
                logger.warning(
                    f"[LLM:deepseek] JSON模式返回空响应，降级为纯文本重试... "
                    f"model={self.model} prompt_chars={len(prompt)}"
                )
                kwargs_for_api_fallback = {
                    k: v for k, v in kwargs_for_api.items()
                    if k != "response_format"
                }
                t1 = time.time()
                response = client.chat.completions.create(**kwargs_for_api_fallback)
                duration_ms = (time.time() - t0) * 1000  # 累计耗时
                text = response.choices[0].message.content or ""
                finish_reason = response.choices[0].finish_reason
                logger.info(
                    f"[LLM:deepseek] ← fallback(no-json) {self.model} duration={duration_ms:.0f}ms "
                    f"chars={len(text)}"
                )
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:deepseek] ← {self.model} ok json={use_json} duration={duration_ms:.0f}ms "
                f"chars={len(text)} response={response_preview_oneline!r}"
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
                    "usage": (
                        response.usage.model_dump() if response.usage else None
                    ),
                    "response_format": "json_object" if use_json else None,
                },
            )
            usage = extract_usage_from_openai_response(response)
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=True, project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id, **usage,
            )
            return text
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:deepseek] ← {self.model} FAIL json={use_json} duration={duration_ms:.0f}ms: {e}",
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
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=False, error=str(e), project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id,
            )
            raise

    def _generate_anthropic(self, client, prompt, system_prompt, use_json, task_type, project_id=None, llm_call_id=None, task_id=None, **kwargs):
        messages = [{"role": "user", "content": prompt}]
        max_tokens = kwargs.get("max_tokens", 4096)
        temperature = kwargs.get("temperature", 0.7)

        if use_json and "json" not in prompt.lower():
            prompt += "\n\n请以 JSON 格式输出结果。"
            messages = [{"role": "user", "content": prompt}]

        system_text = system_prompt
        if use_json and system_text and "json" not in system_text.lower():
            system_text += "\n\n请始终以 JSON 格式输出结果，不要包含任何额外的文字说明。"

        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:deepseek] → {self.model} task={task_type} "
            f"json={use_json} max_tokens={max_tokens} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            create_kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if system_text:
                create_kwargs["system"] = system_text

            response = client.messages.create(**create_kwargs)

            parts = []
            block_types = []
            for block in (response.content or []):
                block_type = getattr(block, "type", None)
                block_types.append(block_type)
                if block_type == "text":
                    parts.append(getattr(block, "text", "") or "")
                elif block_type == "thinking":
                    logger.debug(f"[LLM:deepseek] 跳过 thinking 块")

            if not parts:
                logger.error(
                    f"[LLM:deepseek] 返回无 text 块，块类型={block_types} "
                    f"stop_reason={getattr(response, 'stop_reason', '?')}"
                )
                raise RuntimeError(
                    f"DeepSeek 返回无 text 块。块类型: {block_types}, stop_reason: {getattr(response, 'stop_reason', '?')}"
                )

            text = "".join(parts)
            duration_ms = (time.time() - t0) * 1000
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:deepseek] ← {self.model} ok json={use_json} duration={duration_ms:.0f}ms "
                f"chars={len(text)} response={response_preview_oneline!r}"
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
                    "input_tokens": getattr(getattr(response, "usage", None), "input_tokens", None),
                    "output_tokens": getattr(getattr(response, "usage", None), "output_tokens", None),
                },
            )
            usage = extract_usage_from_anthropic_response(response)
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=True, project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id, **usage,
            )
            return text
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:deepseek] ← {self.model} FAIL json={use_json} duration={duration_ms:.0f}ms: {e}",
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
            record_llm_usage(
                provider=self.provider_name, model=self.model, task_type=task_type,
                duration_ms=duration_ms, success=False, error=str(e), project_id=project_id,
                task_id=task_id, llm_call_id=llm_call_id,
            )
            raise

    def get_context_window(self) -> int:
        return self.CONTEXT_WINDOW

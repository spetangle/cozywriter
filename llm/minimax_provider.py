"""MiniMax Provider (MiniMax / MiniMax 大模型)

官方文档：https://platform.minimaxi.com/docs/api-reference/anthropic-api

接入方式：Anthropic Messages 兼容协议，通过官方 `anthropic` SDK 调用。
- Base URL：https://api.minimaxi.com/anthropic
- 模型：
    * MiniMax-M3         (多模态：文本+图片+视频，1M 上下文，Coding/Agentic SOTA)
    * MiniMax-M2.7       (文本+工具，~60 TPS)
    * MiniMax-M2.7-highspeed
    * MiniMax-M2.5
    * MiniMax-M2.5-highspeed
    * MiniMax-M2.1
    * MiniMax-M2.1-highspeed
    * MiniMax-M2
- 默认温度：1.0
- max_tokens 推荐：M3=131072 (128K)，M2.x=65536 (64K)
- ⚠️ thinking 必须关闭：M3 可通过 thinking={"type": "disabled"} 关，
  M2.x 系列无法关闭（SDK 仍接受该参数，模型会忽略）。
- 响应：content 是块数组 [{type:text, text:"..."}, {type:thinking, thinking:"..."}, ...]
  → 只提取 type=text 的块拼接，跳过 thinking/tool_use 等

为什么用 Anthropic SDK 而不是直接 httpx：
- 官方 Anthropic SDK 天然支持 base_url 切换和 Authorization/x-api-key 双认证
- 未来若 MiniMax 调整协议，SDK 升级可复用
- 代码量少一半，错误处理更稳（SDK 内置重试 / 超时 / 类型化异常）
"""
import time
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
import anthropic


class MiniMaxProvider(LLMProvider):
    # 官方 Anthropic 兼容 base（注意：以 /anthropic 结尾，不带 /v1）
    DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"
    # 缺省模型：M2.7 文本主力（兼容所有用户账号；M3 可能需单独开通多模态权限）
    DEFAULT_MODEL = "MiniMax-M2.7"
    # 上下文窗口：M3=1M, M2.x=128K，统一按 128K 报
    CONTEXT_WINDOW = 128_000

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.minimax_api_key
        self.model = model or getattr(settings, "minimax_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "minimax_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "minimax"

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            # Anthropic SDK 会自动读 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY 环境变量，
            # 但用户配置在 settings.minimax_api_key（来自 .env 的 MINIMAX_API_KEY），
            # 所以显式传入 base_url + api_key，确保不被 env 覆盖。
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=600.0,  # 10 分钟，LLM 长文本兜底
                max_retries=2,  # SDK 内置重试（指数退避）
            )
        return self._client

    def _recommended_max_tokens(self) -> int:
        """根据模型返回推荐的 max_tokens"""
        if "M3" in self.model:
            return 131072
        return 65536  # M2.x

    def _build_thinking_param(self) -> dict | None:
        """
        构建 thinking 参数：M3 显式关闭，M2.x 也传 disabled（被忽略即可，不影响行为）。
        不传 thinking 时 M3 默认关闭，M2.x 永远开启——为了显式一致，统一传 disabled。
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
        # task_type 透传（调用方可在 kwargs 里指定，如 "stage_1_base"）
        task_type = kwargs.get("task_type", "generate")
        messages = [{"role": "user", "content": prompt}]

        # 日志：记录完整 prompt（之前只截断 80 字会导致请求信息不全）
        #    原因：用户排查问题时需看到完整 prompt（system 提示 + schema）
        #    完整响应/请求另外会通过 log_llm_payload() 写入 log 文件
        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:minimax] → {self.model} max_tokens={max_tokens} "
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
                "thinking": self._build_thinking_param(),  # ⚠️ 必须显式关 thinking
            }
            if system_prompt:
                create_kwargs["system"] = system_prompt

            response = client.messages.create(**create_kwargs)

            # 提取所有 type=text 的块，按顺序拼接
            # 跳过 type=thinking / type=tool_use 等非文本块
            parts = []
            for block in (response.content or []):
                # SDK 块对象：block.type == "text" 时有 .text；== "thinking" 时有 .thinking
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    parts.append(getattr(block, "text", "") or "")
                # thinking/tool_use/tool_result 块直接跳过

            if not parts:
                # 模型只返回了 thinking 而无 text（开了 thinking 且 max_tokens 不够 / 被强制开了）
                # 把响应的块类型列出来辅助诊断
                block_types = [getattr(b, "type", "?") for b in (response.content or [])]
                logger.error(
                    f"[LLM:minimax] 返回无 text 块，块类型={block_types} "
                    f"stop_reason={getattr(response, 'stop_reason', '?')}"
                )
                raise RuntimeError(
                    f"MiniMax 返回无 text 块（可能 thinking 占满 max_tokens）。"
                    f"块类型: {block_types}, stop_reason: {getattr(response, 'stop_reason', '?')}"
                )

            text = "".join(parts)
            duration_ms = (time.time() - t0) * 1000
            # 响应预览：跳车原始换行，避免 log 一行被拆成 200 行
            #    超过 300 字符仍截断；完整响应另会通过 log_llm_payload() 入 log
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())  # 压缩空白
            logger.info(
                f"[LLM:minimax] ← {self.model} ok duration={duration_ms:.0f}ms "
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
            duration_ms = (time.time() - t0) * 1000
            logger.error(f"[LLM:minimax] 401 鉴权失败: {e}")
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
            )
            raise RuntimeError(
                "MiniMax 鉴权失败 (401)。请检查 .env 中 MINIMAX_API_KEY 是否正确。\n"
                "获取 API Key: https://platform.minimaxi.com/user-center/basic-information/interface-key"
            ) from e
        except anthropic.PermissionDeniedError as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(f"[LLM:minimax] 403 模型无权访问: {self.model} ({e})")
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
            )
            raise RuntimeError(
                f"MiniMax 403: 无权访问模型 '{self.model}'。"
                f"该模型可能需要单独开通权限。可选: MiniMax-M2.7 / M2.5 / M2.1 / M2"
            ) from e
        except anthropic.NotFoundError as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(f"[LLM:minimax] 404 模型/URL 错误: {self.model} @ {self.base_url} ({e})")
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
                extra={"base_url": self.base_url},
            )
            raise RuntimeError(
                f"MiniMax 404: 模型 '{self.model}' 不存在或 base_url '{self.base_url}' 错误。"
            ) from e
        except anthropic.RateLimitError as e:
            duration_ms = (time.time() - t0) * 1000
            logger.warning(f"[LLM:minimax] 429 限流: {e}")
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
            )
            raise RuntimeError("MiniMax 触发限流 (429)，请稍后重试。") from e
        except anthropic.APIStatusError as e:
            # 其他 4xx/5xx
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:minimax] ← {self.model} API 错误 status={e.status_code} body={e.body}"
            )
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
                extra={"status_code": e.status_code, "body": str(e.body)},
            )
            raise RuntimeError(
                f"MiniMax API 错误 (status={e.status_code}): {e.message or e.body}"
            ) from e
        except anthropic.APIConnectionError as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:minimax] 网络异常 duration={duration_ms:.0f}ms err={e}",
                exc_info=True,
            )
            log_llm_payload(
                provider=self.provider_name, model=self.model, task_type=task_type,
                system_prompt=system_prompt, user_prompt=prompt, response_text="",
                duration_ms=duration_ms, success=False, error=str(e),
                extra={"base_url": self.base_url},
            )
            raise RuntimeError(
                f"MiniMax 网络请求失败（{self.base_url}）: {e}"
            ) from e
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:minimax] ← {self.model} FAIL duration={duration_ms:.0f}ms: {e}",
                exc_info=True,
            )
            # 失败也记 payload（response 是空字符串）
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

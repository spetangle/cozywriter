# DeepSeek JSON 模式排查说明

> 背景：`docs/TEST_REPORT_NOVEL_FLOW.md` / `docs/FIX_PLAN_NOVEL_FLOW.md` §5（P1-5）
> 现象：`deepseek-v4-flash` 在 `use_json=True`（`response_format={"type":"json_object"}`）时返回空字符串，
> 去掉 `response_format` 重试仍为空；同一提示下 `mimo` / `minimax` 正常。

## 已做的容错（`llm/deepseek_provider.py`）

1. **降级重试加强**：JSON 模式首次返回空时，自动去掉 `response_format` 重试一次，并在消息末尾追加
   “只输出合法 JSON，以 `{` 开头、以 `}` 结尾，不要输出解释/思考/markdown” 的强约束
   （`DeepSeekProvider.JSON_RETRY_HINT`）。
2. **抬高 token 下限**：降级重试的 `max_tokens` 不低于 `DeepSeekProvider.JSON_MIN_MAX_TOKENS`（512），
   避免短预算下模型只输出空。
3. **失败可观测**：`log_llm_payload` 的 `extra` 增加 `json_fallback`、`finish_reason`、`first_finish_reason`、
   `first_usage`、`empty_response`，便于在 `data/logs/cozywriter_YYYYMMDD.log` 定位。
   Anthropic 兼容协议路径（`base_url` 以 `/anthropic` 结尾）同样支持空内容降级重试。
4. **可配置关闭 JSON 模式**：不再强行使用 `response_format`。

## 如何关闭某个服务商的 JSON 模式

“全局设置 → 服务商 → 编辑”里，将 **JSON 输出模式** 设为：

- `跟随服务商默认`（`use_json_output = null`）：使用 provider 内置默认（DeepSeek 默认开启）。
- `强制开启`（`true`）：始终传 `response_format={"type":"json_object"}`。
- `强制关闭`（`false`）：不传 `response_format`，改由 prompt 约束 JSON（**某些 DeepSeek 模型 / 自建端点
  返回空响应时建议选择此项**）。

该值持久化在 `providers.use_json_output`（可空布尔列，`NULL`=默认），工厂创建 provider 时透传；
`.env` 里仍可用 `DEEPSEEK_*` 配置 key / base_url / model。

## 回归测试

```bash
python tests/test_deepseek_json_fallback.py   # 无真实 LLM：降级参数、开关、API 覆盖
```

纯函数级覆盖：降级去 `response_format`、追加约束、max_tokens 下限、`use_json_output` 开关与
“显式 null 恢复默认 / 未传字段不改动”。

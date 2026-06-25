"""
trident.llm.anthropic_client — Tier 2 LLM client for Anthropic Claude.
"""

from __future__ import annotations

from shellstory.llm.base import (
    LLMAuthError,
    LLMClient,
    LLMMessage,
    LLMRateLimitError,
    LLMResponse,
    LLMProviderError,
)


class AnthropicClient(LLMClient):
    """Calls Anthropic's Messages API via the anthropic SDK."""

    def __init__(self, config: dict) -> None:
        llm = config.get("llm", {})
        self._model = llm.get("model", "claude-sonnet-4-6")
        self._api_key = llm.get("api_key", "")
        self._max_tokens = 8192

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic client requires: pip install 'trident-cli[byok]'"
            ) from exc

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system

        try:
            resp = await client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(f"Invalid Anthropic API key: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(f"Anthropic rate limit: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(f"Anthropic API error: {exc}") from exc

        content = resp.content[0].text if resp.content else ""
        return LLMResponse(
            content=content,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            finish_reason=resp.stop_reason or "stop",
        )

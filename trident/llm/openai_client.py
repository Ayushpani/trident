"""
trident.llm.openai_client — Tier 2 LLM client for OpenAI.
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


class OpenAIClient(LLMClient):
    """Calls OpenAI's Chat Completions API via the openai SDK."""

    def __init__(self, config: dict) -> None:
        llm = config.get("llm", {})
        self._model = llm.get("model", "gpt-4o-mini")
        self._api_key = llm.get("api_key", "")

    @property
    def provider_name(self) -> str:
        return "openai"

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
            import openai
        except ImportError as exc:
            raise ImportError(
                "OpenAI client requires: pip install 'trident-cli[byok]'"
            ) from exc

        client = openai.AsyncOpenAI(api_key=self._api_key)

        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)

        kwargs: dict = {
            "model": self._model,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMAuthError(f"Invalid OpenAI API key: {exc}") from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(f"OpenAI rate limit: {exc}") from exc
        except openai.APIStatusError as exc:
            raise LLMProviderError(f"OpenAI API error: {exc}") from exc

        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=resp.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            finish_reason=choice.finish_reason or "stop",
        )

"""
trident.llm.openrouter_client — Tier 2 LLM client for OpenRouter.
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


class OpenRouterClient(LLMClient):
    """Calls https://openrouter.ai/api/v1/chat/completions."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: dict) -> None:
        llm = config.get("llm", {})
        self._model = llm.get("model", "anthropic/claude-sonnet-4")
        self._api_key = llm.get("api_key", "")
        self._site_url = llm.get("site_url", "")
        self._app_name = "trident"

    @property
    def provider_name(self) -> str:
        return "openrouter"

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
        import httpx

        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)

        payload: dict = {
            "model": self._model,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._site_url,
            "X-Title": self._app_name,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.BASE_URL, json=payload, headers=headers)

        if resp.status_code == 401:
            raise LLMAuthError("Invalid OpenRouter API key")
        if resp.status_code == 429:
            raise LLMRateLimitError("OpenRouter rate limit exceeded")
        if resp.status_code >= 500:
            raise LLMProviderError(f"OpenRouter server error: {resp.status_code}")
        resp.raise_for_status()

        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self._model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )

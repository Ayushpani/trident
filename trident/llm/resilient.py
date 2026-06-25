"""
trident.llm.resilient — retry and fallback chain for LLM clients.
"""

from __future__ import annotations

import asyncio
import time

from shellstory.llm.base import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponse,
)


class ResilientLLMClient(LLMClient):
    """
    Wraps a primary LLMClient with exponential backoff and a fallback chain.

    If the primary raises LLMRateLimitError, waits and retries up to
    max_retries times.  If all retries fail, tries each fallback client
    in order.
    """

    def __init__(
        self,
        primary: LLMClient,
        fallbacks: list[LLMClient] | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks or []
        self._max_retries = max_retries
        self._base_delay = base_delay

    @property
    def provider_name(self) -> str:
        return self._primary.provider_name

    @property
    def model_name(self) -> str:
        return self._primary.model_name

    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs = dict(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
        )

        # Try primary with retries
        for attempt in range(self._max_retries):
            try:
                return await self._primary.complete(**kwargs)
            except LLMRateLimitError:
                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            except LLMError:
                break  # non-rate-limit errors go straight to fallbacks

        # Try each fallback
        for client in self._fallbacks:
            try:
                return await client.complete(**kwargs)
            except LLMError:
                continue

        raise LLMError("All LLM clients failed (primary + all fallbacks)")

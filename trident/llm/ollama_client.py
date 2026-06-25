"""
trident.llm.ollama_client — Tier 1 LLM client wrapping Ollama's HTTP API.
"""

from __future__ import annotations

from shellstory.llm.base import LLMClient, LLMMessage, LLMResponse, LLMError


class OllamaClient(LLMClient):
    """Calls a local Ollama instance at http://localhost:11434."""

    def __init__(self, config: dict) -> None:
        self._model = config.get("llm", {}).get("model", "llama3:8b")
        self._base_url = "http://localhost:11434"

    @property
    def provider_name(self) -> str:
        return "ollama"

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

        payload = {
            "model": self._model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"Ollama HTTP error: {exc}") from exc
            except httpx.ConnectError as exc:
                raise LLMError(
                    "Cannot connect to Ollama. Is it running? "
                    f"(ollama serve / http://localhost:11434): {exc}"
                ) from exc

        data = resp.json()
        content = data["message"]["content"]
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            finish_reason="stop",
        )

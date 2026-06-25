"""
trident.llm.base — re-exports ShellStory's abstract LLMClient interface.

All Trident LLM clients implement the same abstract base so that
ShellStory's swarm agents work unmodified with any Trident-registered
provider.
"""

from shellstory.llm.base import (  # noqa: F401
    LLMAuthError,
    LLMClient,
    LLMContextError,
    LLMError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
)

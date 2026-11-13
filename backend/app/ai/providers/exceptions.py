"""Exceptions for AI provider adapter (PBI-020)."""

from __future__ import annotations


class AIProviderError(Exception):
    """Base error for AI provider failures.

    Message must never contain secrets or private code.
    """

    def __init__(
        self, message: str, *, provider: str = "unknown", retryable: bool = False
    ):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class AIConfigurationError(AIProviderError):
    """Missing or invalid API key / provider configuration."""

    def __init__(
        self,
        message: str = "AI provider is not configured",
        *,
        provider: str = "unknown",
    ):
        super().__init__(message, provider=provider, retryable=False)


class AITimeoutError(AIProviderError):
    """Request exceeded timeout."""

    def __init__(
        self, message: str = "AI request timed out", *, provider: str = "unknown"
    ):
        super().__init__(message, provider=provider, retryable=True)


class AIRateLimitError(AIProviderError):
    """Provider rate limit or quota exceeded."""

    def __init__(
        self, message: str = "AI rate limit exceeded", *, provider: str = "unknown"
    ):
        super().__init__(message, provider=provider, retryable=True)


class AICostLimitError(AIProviderError):
    """Estimated cost exceeds configured limit."""

    def __init__(
        self, message: str = "AI cost limit exceeded", *, provider: str = "unknown"
    ):
        super().__init__(message, provider=provider, retryable=False)


class AIInjectionBlockedError(AIProviderError):
    """Content was blocked by prompt-injection / safety policy."""

    def __init__(
        self,
        message: str = "Request blocked by safety policy",
        *,
        provider: str = "unknown",
    ):
        super().__init__(message, provider=provider, retryable=False)

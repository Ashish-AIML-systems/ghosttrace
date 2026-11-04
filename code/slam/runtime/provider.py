"""Provider-neutral structured model interface.

Providers return proposals only. They never receive tools and never decide
identity, policy, deletion status, ordering, or export readiness.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

StructuredT = TypeVar("StructuredT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelImageInput:
    """In-memory image supplied to a provider; never a provider-accessible path."""

    content: bytes
    mime_type: str
    sha256: str

    def __post_init__(self) -> None:
        if self.mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            raise ValueError("unsupported image MIME type")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class ModelCallMetadata:
    provider: str
    model: str
    request_id: str | None
    prompt_version: str
    schema_name: str
    latency_ms: int
    retries: int
    cache_hit: bool
    usage: ModelUsage


@dataclass(frozen=True, slots=True)
class ModelResult(Generic[StructuredT]):
    value: StructuredT
    metadata: ModelCallMetadata


class ModelProviderError(RuntimeError):
    """Base class for explicit, non-decision provider failures."""


class ModelRefusalError(ModelProviderError):
    pass


class ModelTruncationError(ModelProviderError):
    pass


class ModelMalformedResponseError(ModelProviderError):
    pass


class ModelResponseError(ModelMalformedResponseError):
    """Backward-compatible name for malformed structured output."""


class ModelTimeoutError(ModelProviderError):
    pass


class ModelBudgetError(ModelProviderError):
    pass


class ModelAuthenticationError(ModelProviderError):
    pass


class ModelQuotaError(ModelProviderError):
    pass


class ModelProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def generate(
        self,
        *,
        prompt: str,
        prompt_version: str,
        response_model: type[StructuredT],
        images: Sequence[ModelImageInput] = (),
    ) -> ModelResult[StructuredT]: ...

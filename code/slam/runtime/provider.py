"""Provider-neutral structured model interface.

Providers return proposals only. They never receive tools and never decide
identity, policy, deletion status, ordering, or export readiness.
"""

from __future__ import annotations

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


class ModelResponseError(ModelProviderError):
    pass


class ModelBudgetError(ModelProviderError):
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
    ) -> ModelResult[StructuredT]: ...

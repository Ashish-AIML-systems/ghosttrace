"""Deterministic offline model provider used by all ordinary tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from slam.runtime.provider import (
    ModelCallMetadata,
    ModelProviderError,
    ModelResult,
    ModelUsage,
    StructuredT,
)


class FakeModelProvider:
    """Return queued payloads without network, credentials, or hidden behavior."""

    def __init__(
        self,
        responses: Iterable[Mapping[str, Any] | BaseModel | Exception] = (),
        *,
        model: str = "fake-structured-v1",
    ) -> None:
        self._responses = deque(responses)
        self._model = model
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        *,
        prompt: str,
        prompt_version: str,
        response_model: type[StructuredT],
    ) -> ModelResult[StructuredT]:
        del prompt
        self.calls += 1
        if not self._responses:
            raise ModelProviderError("fake provider has no queued response")
        raw = self._responses.popleft()
        if isinstance(raw, Exception):
            raise raw
        value = raw if isinstance(raw, response_model) else response_model.model_validate(raw)
        metadata = ModelCallMetadata(
            provider=self.name,
            model=self.model,
            request_id=f"fake-{self.calls}",
            prompt_version=prompt_version,
            schema_name=response_model.__name__,
            latency_ms=0,
            retries=0,
            cache_hit=False,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
        )
        return ModelResult(value=value, metadata=metadata)

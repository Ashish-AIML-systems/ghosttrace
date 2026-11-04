"""In-memory usage ledger with no secret or prompt-content logging."""

from __future__ import annotations

from dataclasses import dataclass, field

from slam.runtime.provider import ModelCallMetadata


@dataclass(slots=True)
class UsageLedger:
    calls: list[ModelCallMetadata] = field(default_factory=list)

    def record(self, metadata: ModelCallMetadata) -> None:
        self.calls.append(metadata)

    def summary(self) -> dict[str, int | None]:
        actual = [call for call in self.calls if not call.cache_hit]
        cache_hits = len(self.calls) - len(actual)

        def total(name: str) -> int | None:
            values = [getattr(call.usage, name) for call in actual]
            known = [value for value in values if value is not None]
            return sum(known) if len(known) == len(values) else None

        return {
            "actual_calls": len(actual),
            "cache_hits": cache_hits,
            "retries": sum(call.retries for call in actual),
            "latency_ms": sum(call.latency_ms for call in actual),
            "input_tokens": total("input_tokens"),
            "output_tokens": total("output_tokens"),
            "cached_input_tokens": total("cached_input_tokens"),
            "reasoning_tokens": total("reasoning_tokens"),
        }

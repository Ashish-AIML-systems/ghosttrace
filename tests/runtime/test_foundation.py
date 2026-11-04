from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError
from slam.config import ProviderName, Settings
from slam.runtime.cache import build_cache_key
from slam.runtime.fake_provider import FakeModelProvider
from slam.runtime.metering import UsageLedger
from slam.runtime.provider import ModelProviderError


class Proposal(BaseModel):
    value: str


def test_safe_default_configuration_is_offline() -> None:
    settings = Settings(_env_file=None)
    assert settings.model_provider is ProviderName.FAKE
    assert settings.api_budget_usd == Decimal("0")


def test_openai_configuration_requires_key_and_budget() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            SLAM_MODEL_PROVIDER="openai",
            SLAM_MODEL="explicit-model",
            SLAM_API_BUDGET_USD="0",
        )


def test_fake_provider_validates_and_meters() -> None:
    provider = FakeModelProvider([{"value": "grounded"}])
    result = provider.generate(prompt="data", prompt_version="v1", response_model=Proposal)
    ledger = UsageLedger()
    ledger.record(result.metadata)
    assert result.value.value == "grounded"
    assert ledger.summary()["actual_calls"] == 1
    assert provider.calls == 1


def test_fake_provider_fails_when_empty() -> None:
    with pytest.raises(ModelProviderError):
        FakeModelProvider().generate(prompt="x", prompt_version="v1", response_model=Proposal)


def test_cache_key_is_order_independent_and_namespaced() -> None:
    first = build_cache_key(namespace="extract", parts={"b": 2, "a": 1})
    second = build_cache_key(namespace="extract", parts={"a": 1, "b": 2})
    assert first == second
    assert first != build_cache_key(namespace="decision", parts={"a": 1, "b": 2})

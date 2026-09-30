from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import RateLimitError
from test_anthropic_engine import MOCK_DOSSIER_JSON

from config import Settings
from key_pool import KeyPool, get_key_pool, parse_keys
from synthesis.models import SynthesisRequest
from synthesis.nvidia_engine import NvidiaSynthesisEngine


def test_parse_keys_splits_and_dedupes() -> None:
    assert parse_keys(" a, b ,,a\nc ") == ["a", "b", "c"]
    assert parse_keys("") == []
    assert parse_keys(None) == []


def test_round_robin_order() -> None:
    pool = KeyPool("t", ["a", "b", "c"])
    assert [pool.next_key() for _ in range(5)] == ["a", "b", "c", "a", "b"]


def test_failed_key_is_skipped() -> None:
    pool = KeyPool("t", ["a", "b"])
    pool.mark_failed("a", cooldown_s=60)
    assert [pool.next_key() for _ in range(3)] == ["b", "b", "b"]


def test_all_keys_cooling_returns_soonest() -> None:
    pool = KeyPool("t", ["a", "b"])
    pool.mark_failed("a", cooldown_s=120)
    pool.mark_failed("b", cooldown_s=10)
    assert pool.next_key() == "b"


def test_empty_pool() -> None:
    assert KeyPool("t", []).next_key() is None


def test_get_key_pool_is_shared() -> None:
    assert get_key_pool("x", "k1,k2") is get_key_pool("x", "k1, k2")


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return RateLimitError(
        "rate limited", response=httpx.Response(429, request=request), body=None
    )


@pytest.mark.asyncio
async def test_nvidia_engine_rotates_key_on_rate_limit() -> None:
    engine = NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY="nvapi-rl-1,nvapi-rl-2"))

    message = MagicMock()
    message.content = MOCK_DOSSIER_JSON
    ok_response = MagicMock()
    ok_response.choices = [MagicMock(message=message)]

    limited = MagicMock()
    limited.chat.completions.create = AsyncMock(side_effect=_rate_limit_error())
    healthy = MagicMock()
    healthy.chat.completions.create = AsyncMock(return_value=ok_response)
    engine._clients = {"nvapi-rl-1": limited, "nvapi-rl-2": healthy}

    result = await engine.synthesize(SynthesisRequest(person_name="Elon Musk"))

    assert result.success is True
    limited.chat.completions.create.assert_awaited_once()
    healthy.chat.completions.create.assert_awaited_once()
    # The rate-limited key is now skipped
    assert engine._key_pool.next_key() == ("nvapi-rl-2", "meta/llama-3.3-70b-instruct")


@pytest.mark.asyncio
async def test_nvidia_engine_rotates_models() -> None:
    engine = NvidiaSynthesisEngine(
        Settings(NVIDIA_API_KEY="nvapi-mr-1", NVIDIA_MODELS="model-a, model-b")
    )
    message = MagicMock()
    message.content = MOCK_DOSSIER_JSON
    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    engine._clients = {"nvapi-mr-1": client}

    await engine.synthesize(SynthesisRequest(person_name="A"))
    await engine.synthesize(SynthesisRequest(person_name="B"))

    models = [c.kwargs["model"] for c in client.chat.completions.create.call_args_list]
    assert models == ["model-a", "model-b"]


def test_nvidia_model_list_falls_back_to_single_model() -> None:
    assert Settings(NVIDIA_MODEL="m1", NVIDIA_MODELS="").nvidia_model_list() == ["m1"]
    assert Settings(NVIDIA_MODELS="a,b").nvidia_model_list() == ["a", "b"]

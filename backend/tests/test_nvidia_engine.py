from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from test_anthropic_engine import MOCK_DOSSIER_JSON

from config import Settings
from synthesis.models import SynthesisRequest
from synthesis.nvidia_engine import NvidiaSynthesisEngine


def _mock_client(content: str | None) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def test_nvidia_engine_configured_flag() -> None:
    assert NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY="")).configured is False
    assert NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY="nvapi-test")).configured is True


@pytest.mark.asyncio
async def test_nvidia_engine_not_configured_returns_error() -> None:
    engine = NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY=""))
    result = await engine.synthesize(SynthesisRequest(person_name="Test"))
    assert result.success is False
    assert "NVIDIA_API_KEY" in (result.error or "")


@pytest.mark.asyncio
async def test_nvidia_engine_parses_dossier() -> None:
    engine = NvidiaSynthesisEngine(
        Settings(NVIDIA_API_KEY="nvapi-test", NVIDIA_MODEL="meta/llama-3.3-70b-instruct")
    )
    client = _mock_client(f"```json\n{MOCK_DOSSIER_JSON}\n```")
    engine._client = client

    result = await engine.synthesize(SynthesisRequest(person_name="Elon Musk"))

    assert result.success is True
    assert result.organization == "Tesla / SpaceX"
    assert result.dossier is not None
    assert len(result.dossier.work_history) == 3
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "meta/llama-3.3-70b-instruct"


@pytest.mark.asyncio
async def test_nvidia_engine_empty_response() -> None:
    engine = NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY="nvapi-test"))
    engine._client = _mock_client(None)
    result = await engine.synthesize(SynthesisRequest(person_name="Test"))
    assert result.success is False


def test_nvidia_client_uses_base_url() -> None:
    engine = NvidiaSynthesisEngine(Settings(NVIDIA_API_KEY="nvapi-test"))
    client = engine._get_client()
    assert str(client.base_url).startswith("https://integrate.api.nvidia.com/v1")

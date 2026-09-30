from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.genai import errors

from gemini_pool import GeminiRotator


def _rotator_with_clients(keys: str, models: str) -> tuple[GeminiRotator, dict[str, MagicMock]]:
    rotator = GeminiRotator(keys, models)
    clients = {key: MagicMock(name=key) for key in rotator.keys}
    rotator._clients = clients
    return rotator, clients


def _called_pairs(clients: dict[str, MagicMock]) -> list[tuple[str, str]]:
    calls = []
    for key, client in clients.items():
        for call in client.models.generate_content.call_args_list:
            calls.append((key, call.kwargs["model"]))
    return calls


def test_default_model_when_unset() -> None:
    assert GeminiRotator("k", "").models == ["gemini-2.0-flash"]
    assert GeminiRotator("", "m").configured is False


def test_rotates_keys_then_models() -> None:
    rotator, clients = _rotator_with_clients("rot-a,rot-b", "m1,m2")
    for _ in range(4):
        rotator.generate_content(contents="hi")
    assert sorted(_called_pairs(clients)) == [
        ("rot-a", "m1"), ("rot-a", "m2"), ("rot-b", "m1"), ("rot-b", "m2"),
    ]


def test_quota_error_fails_over_to_next_pair() -> None:
    rotator, clients = _rotator_with_clients("quota-a,quota-b", "qm")
    clients["quota-a"].models.generate_content.side_effect = errors.ClientError(
        429, {"error": {"message": "quota"}}
    )
    clients["quota-b"].models.generate_content.return_value = "ok"

    assert rotator.generate_content(contents="hi") == "ok"
    # quota-a is cooling down, so quota-b keeps serving
    assert rotator.generate_content(contents="hi") == "ok"
    assert clients["quota-a"].models.generate_content.call_count == 1


def test_unknown_model_skipped() -> None:
    rotator, clients = _rotator_with_clients("nf-a", "gone-model,good-model")

    def fake(model: str, **_: object) -> str:
        if model == "gone-model":
            raise errors.ClientError(404, {"error": {"message": "not found"}})
        return model

    clients["nf-a"].models.generate_content.side_effect = fake
    assert rotator.generate_content(contents="hi") == "good-model"
    assert rotator.generate_content(contents="hi") == "good-model"


def test_all_pairs_failing_raises_last_error() -> None:
    rotator, clients = _rotator_with_clients("dead-a", "dead-m")
    clients["dead-a"].models.generate_content.side_effect = errors.ClientError(
        429, {"error": {"message": "quota"}}
    )
    with pytest.raises(errors.ClientError):
        rotator.generate_content(contents="hi")


def test_non_retryable_error_is_raised_immediately() -> None:
    rotator, clients = _rotator_with_clients("bad-a,bad-b", "bm")
    clients["bad-a"].models.generate_content.side_effect = errors.ClientError(
        400, {"error": {"message": "bad request"}}
    )
    with pytest.raises(errors.ClientError):
        rotator.generate_content(contents="hi")
    clients["bad-b"].models.generate_content.assert_not_called()

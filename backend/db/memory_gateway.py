from __future__ import annotations

from typing import Any


class InMemoryDatabaseGateway:
    """In-memory implementation of DatabaseGateway for testing and local dev.

    Implements the DatabaseGateway protocol from db/__init__.py.
    """

    def __init__(self) -> None:
        self._persons: dict[str, dict[str, Any]] = {}
        self._captures: dict[str, dict[str, Any]] = {}

    @property
    def configured(self) -> bool:
        return True

    async def store_person(self, person_id: str, data: dict[str, Any]) -> str:
        self._persons[person_id] = {**data, "person_id": person_id}
        return person_id

    async def get_person(self, person_id: str) -> dict[str, Any] | None:
        return self._persons.get(person_id)

    async def update_person(self, person_id: str, data: dict[str, Any]) -> None:
        existing = self._persons.get(person_id, {})
        self._persons[person_id] = {**existing, **data}

    async def store_capture(self, capture_id: str, metadata: dict[str, Any]) -> str:
        self._captures[capture_id] = {**metadata, "capture_id": capture_id}
        return capture_id

# RESEARCH: Checked kitUIN/PicImageSearch (700★, 14+ engines, async httpx)
# DECISION: Using PicImageSearch — aggregates Google, Yandex, Bing reverse image search
#   No API keys needed for most engines. Pure HTTP (no Selenium).
# ALT: Manual httpx reverse image upload to each engine (more code, same result)
from __future__ import annotations

import asyncio
import io
import re
from typing import Any

from loguru import logger

from identification.models import FaceSearchMatch, FaceSearchRequest, FaceSearchResult

_ENGINE_TIMEOUT = 20  # seconds per engine


class ReverseImageSearcher:
    """Reverse image search across multiple engines via PicImageSearch.

    Implements the FaceSearcher protocol from identification/__init__.py.
    Searches Google, Yandex, and Bing in parallel and merges results.
    """

    def __init__(self, *, engines: list[str] | None = None) -> None:
        self._engines = engines or ["google", "yandex", "bing"]

    @property
    def configured(self) -> bool:
        return True  # No API keys required

    async def search_face(self, request: FaceSearchRequest) -> FaceSearchResult:
        """Search for a face across multiple reverse image search engines."""
        if not request.image_data:
            return FaceSearchResult(
                success=False,
                error="Reverse image search requires image_data",
            )

        tasks = []
        for engine in self._engines:
            tasks.append(self._search_engine(engine, request.image_data))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_matches: list[FaceSearchMatch] = []
        errors: list[str] = []

        for engine, result in zip(self._engines, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Reverse search engine {} failed: {}", engine, result)
                errors.append(f"{engine}: {result}")
            elif result:
                all_matches.extend(result)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_matches: list[FaceSearchMatch] = []
        for match in all_matches:
            if match.url not in seen_urls:
                seen_urls.add(match.url)
                unique_matches.append(match)

        # Sort by similarity descending
        unique_matches.sort(key=lambda m: m.similarity, reverse=True)

        success = len(unique_matches) > 0 or len(errors) < len(self._engines)
        error_msg = "; ".join(errors) if errors and not unique_matches else None

        logger.info(
            "Reverse image search: {} matches across {} engines ({} errors)",
            len(unique_matches), len(self._engines), len(errors),
        )

        return FaceSearchResult(
            matches=unique_matches[:30],  # Cap at 30
            success=success,
            error=error_msg,
        )

    async def _search_engine(
        self, engine: str, image_data: bytes
    ) -> list[FaceSearchMatch]:
        try:
            return await asyncio.wait_for(
                self._do_engine_search(engine, image_data),
                timeout=_ENGINE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning("Reverse search engine {} timed out", engine)
            raise

    async def _do_engine_search(
        self, engine: str, image_data: bytes
    ) -> list[FaceSearchMatch]:
        """Run a single engine search via PicImageSearch."""
        engine_class = self._get_engine_class(engine)
        if engine_class is None:
            return []

        searcher = engine_class()
        # PicImageSearch expects a file-like object or path
        file_obj = io.BytesIO(image_data)
        file_obj.name = "face.jpg"

        result = await searcher.search(file=file_obj)

        if not result or not result.raw:
            return []

        return self._parse_engine_results(engine, result.raw)

    @staticmethod
    def _get_engine_class(engine: str) -> Any:
        try:
            if engine == "google":
                from PicImageSearch import Google

                return Google
            elif engine == "yandex":
                from PicImageSearch import Yandex

                return Yandex
            elif engine == "bing":
                from PicImageSearch import Bing

                return Bing
        except ImportError:
            logger.warning("PicImageSearch engine {} not available", engine)
        return None

    @staticmethod
    def _parse_engine_results(
        engine: str, raw_results: list[Any]
    ) -> list[FaceSearchMatch]:
        matches: list[FaceSearchMatch] = []
        for item in raw_results[:15]:
            url = getattr(item, "url", "") or ""
            thumbnail = getattr(item, "thumbnail", None)
            title = getattr(item, "title", "") or ""
            similarity = getattr(item, "similarity", 0.5)
            if isinstance(similarity, str):
                try:
                    similarity = float(similarity.strip("%")) / 100.0
                except ValueError:
                    similarity = 0.5

            # Try to extract a person name from the title
            person_name = _extract_name_from_title(title)

            matches.append(
                FaceSearchMatch(
                    url=url,
                    thumbnail_url=thumbnail,
                    similarity=max(0.0, min(1.0, float(similarity))),
                    source=engine,
                    person_name=person_name,
                )
            )
        return matches


def _extract_name_from_title(title: str) -> str | None:
    """Best-effort name extraction from a search result title."""
    if not title:
        return None

    # Strip parenthetical handles like (@jdoe)
    title = re.sub(r"\s*\(@?\w+\)", "", title)

    # Common patterns: "John Doe - LinkedIn", "John Doe / X"
    # Strip trailing platform names
    cleaned = re.split(r"\s*[-|–—/\\]\s*(?:LinkedIn|Twitter|X|Instagram|Facebook|YouTube)", title)
    candidate = cleaned[0].strip() if cleaned else title.strip()

    # Basic heuristic: 2-4 capitalized words
    words = candidate.split()
    if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
        return candidate

    return None

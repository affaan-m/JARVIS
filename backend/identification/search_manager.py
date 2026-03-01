# RESEARCH: Custom orchestration layer — no existing library for PimEyes+fallback combo
# DECISION: Simple waterfall: PimEyes first (best for faces), reverse image search fallback
from __future__ import annotations

from loguru import logger

from config import Settings
from identification.models import FaceSearchRequest, FaceSearchResult
from identification.pimeyes import PimEyesSearcher
from identification.reverse_search import ReverseImageSearcher


class FaceSearchManager:
    """Orchestrates face search across PimEyes and reverse image engines.

    Implements the FaceSearcher protocol from identification/__init__.py.
    Strategy: PimEyes first (purpose-built for faces), reverse image fallback.
    """

    def __init__(self, settings: Settings) -> None:
        self._pimeyes = PimEyesSearcher(settings)
        self._reverse = ReverseImageSearcher()

    @property
    def configured(self) -> bool:
        return True

    async def search_face(self, request: FaceSearchRequest) -> FaceSearchResult:
        """Search for a face: PimEyes first, reverse image search fallback."""

        # Tier 1: PimEyes (purpose-built face search)
        logger.info("Face search: trying PimEyes first")
        pimeyes_result = await self._pimeyes.search_face(request)

        if pimeyes_result.success and pimeyes_result.matches:
            logger.info("PimEyes found {} matches, skipping reverse search",
                        len(pimeyes_result.matches))
            return pimeyes_result

        # Tier 2: Reverse image search (Google, Yandex, Bing)
        logger.info("PimEyes returned no matches, falling back to reverse image search")
        reverse_result = await self._reverse.search_face(request)

        if reverse_result.success and reverse_result.matches:
            logger.info("Reverse search found {} matches", len(reverse_result.matches))
            return reverse_result

        # Both failed — merge errors
        errors = []
        if pimeyes_result.error:
            errors.append(f"PimEyes: {pimeyes_result.error}")
        if reverse_result.error:
            errors.append(f"ReverseSearch: {reverse_result.error}")

        return FaceSearchResult(
            matches=[],
            success=False,
            error=" | ".join(errors) if errors else "No matches found across any search engine",
        )

    def best_name_from_results(self, result: FaceSearchResult) -> str | None:
        """Extract the most likely person name from search results.

        Uses frequency analysis: the name that appears most across matches wins.
        """
        if not result.matches:
            return None

        name_counts: dict[str, int] = {}
        for match in result.matches:
            if match.person_name:
                name = match.person_name.strip()
                name_counts[name] = name_counts.get(name, 0) + 1

        if not name_counts:
            return None

        # Return the most frequent name
        return max(name_counts, key=name_counts.get)  # type: ignore[arg-type]

    def profile_urls_from_results(self, result: FaceSearchResult) -> list[str]:
        """Extract social profile URLs from search results."""
        social_domains = {
            "linkedin.com", "twitter.com", "x.com", "instagram.com",
            "facebook.com", "github.com", "tiktok.com",
        }
        urls: list[str] = []
        seen: set[str] = set()
        for match in result.matches:
            if match.url and match.url not in seen:
                if any(domain in match.url for domain in social_domains):
                    urls.append(match.url)
                    seen.add(match.url)
        return urls

from __future__ import annotations

import io

import pytest
from PIL import Image

from identification.models import (
    BoundingBox,
    DetectedFace,
    FaceSearchMatch,
    FaceSearchRequest,
    FaceSearchResult,
)
from identification.pimeyes import PimEyesSearcher
from identification.reverse_search import ReverseImageSearcher, _extract_name_from_title
from identification.search_manager import FaceSearchManager


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _fake_embedding() -> list[float]:
    return [0.1] * 512


def _make_request(*, with_image: bool = True) -> FaceSearchRequest:
    return FaceSearchRequest(
        embedding=_fake_embedding(),
        image_data=_make_jpeg() if with_image else None,
    )


# --- PimEyes Tests ---


class TestPimEyesSearcher:
    def _make_searcher(self, pool: str = "[]") -> PimEyesSearcher:
        """Create a PimEyesSearcher with a fake Settings object."""
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.pimeyes_account_pool = pool
        return PimEyesSearcher(settings)

    def test_configured_without_accounts(self) -> None:
        searcher = self._make_searcher()
        assert searcher.configured is True

    @pytest.mark.asyncio
    async def test_search_without_image_fails(self) -> None:
        searcher = self._make_searcher()
        request = FaceSearchRequest(embedding=_fake_embedding(), image_data=None)
        result = await searcher.search_face(request)
        assert result.success is False
        assert "image_data" in (result.error or "")

    @pytest.mark.asyncio
    async def test_search_timeout_returns_error(self) -> None:
        """When httpx times out, returns graceful error."""
        from unittest.mock import patch

        searcher = self._make_searcher()
        import httpx

        with patch.object(
            searcher, "_search_via_api", side_effect=httpx.TimeoutException("timeout")
        ):
            result = await searcher.search_face(_make_request())
        assert result.success is False
        assert "timed out" in (result.error or "")


# --- Reverse Image Search Tests ---


class TestReverseImageSearcher:
    def test_configured(self) -> None:
        searcher = ReverseImageSearcher()
        assert searcher.configured is True

    @pytest.mark.asyncio
    async def test_search_without_image_fails(self) -> None:
        searcher = ReverseImageSearcher()
        request = FaceSearchRequest(embedding=_fake_embedding(), image_data=None)
        result = await searcher.search_face(request)
        assert result.success is False
        assert "image_data" in (result.error or "")

    @pytest.mark.asyncio
    async def test_search_with_mocked_engines(self) -> None:
        """Mock PicImageSearch engines and verify result merging."""
        from unittest.mock import AsyncMock, MagicMock, patch

        searcher = ReverseImageSearcher(engines=["google"])

        # Mock the engine search to return fake results
        fake_item = MagicMock()
        fake_item.url = "https://linkedin.com/in/johndoe"
        fake_item.thumbnail = "https://thumb.example.com/1.jpg"
        fake_item.title = "John Doe - LinkedIn"
        fake_item.similarity = 0.85

        fake_result = MagicMock()
        fake_result.raw = [fake_item]

        fake_engine_instance = MagicMock()
        fake_engine_instance.search = AsyncMock(return_value=fake_result)

        fake_engine_class = MagicMock(return_value=fake_engine_instance)

        with patch.object(searcher, "_get_engine_class", return_value=fake_engine_class):
            result = await searcher.search_face(_make_request())

        assert result.success is True
        assert len(result.matches) == 1
        assert result.matches[0].url == "https://linkedin.com/in/johndoe"
        assert result.matches[0].person_name == "John Doe"
        assert result.matches[0].source == "google"

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self) -> None:
        """Duplicate URLs across engines are removed."""
        from unittest.mock import AsyncMock, MagicMock, patch

        searcher = ReverseImageSearcher(engines=["google", "bing"])

        fake_item = MagicMock()
        fake_item.url = "https://example.com/same"
        fake_item.thumbnail = None
        fake_item.title = ""
        fake_item.similarity = 0.7

        fake_result = MagicMock()
        fake_result.raw = [fake_item]

        fake_engine_instance = MagicMock()
        fake_engine_instance.search = AsyncMock(return_value=fake_result)
        fake_engine_class = MagicMock(return_value=fake_engine_instance)

        with patch.object(searcher, "_get_engine_class", return_value=fake_engine_class):
            result = await searcher.search_face(_make_request())

        assert result.success is True
        assert len(result.matches) == 1

    @pytest.mark.asyncio
    async def test_all_engines_fail_returns_error(self) -> None:
        """If all engines fail, returns error."""
        from unittest.mock import patch

        searcher = ReverseImageSearcher(engines=["google"])

        with patch.object(
            searcher, "_do_engine_search", side_effect=TimeoutError("timed out")
        ):
            result = await searcher.search_face(_make_request())

        assert result.success is False


# --- Name Extraction Tests ---


class TestExtractNameFromTitle:
    def test_linkedin_title(self) -> None:
        assert _extract_name_from_title("John Doe - LinkedIn") == "John Doe"

    def test_twitter_title(self) -> None:
        assert _extract_name_from_title("Jane Smith (@jane) / X") == "Jane Smith"

    def test_no_name(self) -> None:
        assert _extract_name_from_title("some random page title") is None

    def test_empty(self) -> None:
        assert _extract_name_from_title("") is None

    def test_single_word(self) -> None:
        assert _extract_name_from_title("Madonna") is None

    def test_three_word_name(self) -> None:
        assert _extract_name_from_title("Mary Jane Watson - Instagram") == "Mary Jane Watson"


# --- Search Manager Tests ---


class TestFaceSearchManager:
    def _make_manager(self) -> FaceSearchManager:
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.pimeyes_account_pool = "[]"
        return FaceSearchManager(settings)

    def test_configured(self) -> None:
        manager = self._make_manager()
        assert manager.configured is True

    @pytest.mark.asyncio
    async def test_pimeyes_success_skips_reverse(self) -> None:
        """When PimEyes returns matches, reverse search is skipped."""
        from unittest.mock import AsyncMock, patch

        manager = self._make_manager()

        pimeyes_result = FaceSearchResult(
            matches=[
                FaceSearchMatch(
                    url="https://example.com/1",
                    similarity=0.9,
                    source="pimeyes",
                    person_name="Alice Smith",
                )
            ],
            success=True,
        )

        with (
            patch.object(manager._pimeyes, "search_face", new_callable=AsyncMock,
                         return_value=pimeyes_result),
            patch.object(manager._reverse, "search_face", new_callable=AsyncMock) as mock_reverse,
        ):
            result = await manager.search_face(_make_request())

        assert result.success is True
        assert len(result.matches) == 1
        assert result.matches[0].source == "pimeyes"
        mock_reverse.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_reverse_search(self) -> None:
        """When PimEyes fails, reverse search is used."""
        from unittest.mock import AsyncMock, patch

        manager = self._make_manager()

        pimeyes_fail = FaceSearchResult(success=False, error="rate limited")
        reverse_ok = FaceSearchResult(
            matches=[
                FaceSearchMatch(
                    url="https://google.com/img/1",
                    similarity=0.7,
                    source="google",
                    person_name="Bob Jones",
                )
            ],
            success=True,
        )

        with (
            patch.object(manager._pimeyes, "search_face", new_callable=AsyncMock,
                         return_value=pimeyes_fail),
            patch.object(manager._reverse, "search_face", new_callable=AsyncMock,
                         return_value=reverse_ok),
        ):
            result = await manager.search_face(_make_request())

        assert result.success is True
        assert result.matches[0].source == "google"

    @pytest.mark.asyncio
    async def test_both_fail_returns_error(self) -> None:
        """When both PimEyes and reverse fail, returns combined error."""
        from unittest.mock import AsyncMock, patch

        manager = self._make_manager()

        fail1 = FaceSearchResult(success=False, error="pimeyes down")
        fail2 = FaceSearchResult(success=False, error="all engines failed")

        with (
            patch.object(manager._pimeyes, "search_face", new_callable=AsyncMock,
                         return_value=fail1),
            patch.object(manager._reverse, "search_face", new_callable=AsyncMock,
                         return_value=fail2),
        ):
            result = await manager.search_face(_make_request())

        assert result.success is False
        assert "pimeyes down" in (result.error or "")
        assert "all engines failed" in (result.error or "")

    def test_best_name_from_results_frequency(self) -> None:
        manager = self._make_manager()
        result = FaceSearchResult(
            matches=[
                FaceSearchMatch(url="a", similarity=0.9, source="x", person_name="Alice"),
                FaceSearchMatch(url="b", similarity=0.8, source="y", person_name="Bob"),
                FaceSearchMatch(url="c", similarity=0.7, source="z", person_name="Alice"),
            ],
            success=True,
        )
        assert manager.best_name_from_results(result) == "Alice"

    def test_best_name_no_names(self) -> None:
        manager = self._make_manager()
        result = FaceSearchResult(
            matches=[
                FaceSearchMatch(url="a", similarity=0.9, source="x"),
            ],
            success=True,
        )
        assert manager.best_name_from_results(result) is None

    def test_best_name_empty_results(self) -> None:
        manager = self._make_manager()
        result = FaceSearchResult(matches=[], success=True)
        assert manager.best_name_from_results(result) is None

    def test_profile_urls_extraction(self) -> None:
        manager = self._make_manager()
        result = FaceSearchResult(
            matches=[
                FaceSearchMatch(url="https://linkedin.com/in/alice", similarity=0.9, source="x"),
                FaceSearchMatch(url="https://twitter.com/alice", similarity=0.8, source="y"),
                FaceSearchMatch(url="https://random-blog.com/post", similarity=0.7, source="z"),
                FaceSearchMatch(url="https://github.com/alice", similarity=0.6, source="w"),
            ],
            success=True,
        )
        urls = manager.profile_urls_from_results(result)
        assert "https://linkedin.com/in/alice" in urls
        assert "https://twitter.com/alice" in urls
        assert "https://github.com/alice" in urls
        assert "https://random-blog.com/post" not in urls


# --- Pipeline Integration with Face Search ---


class TestPipelineFaceSearchIntegration:
    @pytest.mark.asyncio
    async def test_pipeline_uses_face_search_when_no_name(self) -> None:
        """Pipeline uses face search to identify person when no name is provided."""
        from unittest.mock import AsyncMock, MagicMock

        from db.memory_gateway import InMemoryDatabaseGateway
        from identification.embedder import ArcFaceEmbedder
        from identification.models import FaceDetectionRequest, FaceDetectionResult
        from pipeline import CapturePipeline

        face = DetectedFace(
            bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
            confidence=0.95,
        )

        class FakeDetector:
            configured = True

            async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
                return FaceDetectionResult(
                    faces=[face], frame_width=100, frame_height=100, success=True,
                )

        db = InMemoryDatabaseGateway()
        face_searcher = MagicMock()
        face_searcher.search_face = AsyncMock(
            return_value=FaceSearchResult(
                matches=[
                    FaceSearchMatch(
                        url="https://linkedin.com/in/alice",
                        similarity=0.9,
                        source="pimeyes",
                        person_name="Alice Smith",
                    )
                ],
                success=True,
            )
        )
        face_searcher.best_name_from_results = MagicMock(return_value="Alice Smith")

        pipeline = CapturePipeline(
            detector=FakeDetector(),
            embedder=ArcFaceEmbedder(),
            db=db,
            face_searcher=face_searcher,
        )

        result = await pipeline.process(
            capture_id="cap_search01",
            data=_make_jpeg(),
            content_type="image/jpeg",
            # No person_name — should use face search
        )

        assert result.success is True
        assert result.faces_detected == 1
        assert len(result.persons_created) == 1

        # Verify face search was called
        face_searcher.search_face.assert_called_once()

        # Verify person was stored with identified name
        # Note: status may be overwritten by enrichment step (enriched_no_synthesis)
        person = await db.get_person(result.persons_created[0])
        assert person is not None
        assert person["name"] == "Alice Smith"

    @pytest.mark.asyncio
    async def test_pipeline_skips_face_search_when_name_provided(self) -> None:
        """Pipeline skips face search when person_name is already provided."""
        from unittest.mock import AsyncMock, MagicMock

        from db.memory_gateway import InMemoryDatabaseGateway
        from identification.embedder import ArcFaceEmbedder
        from identification.models import FaceDetectionRequest, FaceDetectionResult
        from pipeline import CapturePipeline

        face = DetectedFace(
            bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
            confidence=0.95,
        )

        class FakeDetector:
            configured = True

            async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
                return FaceDetectionResult(
                    faces=[face], frame_width=100, frame_height=100, success=True,
                )

        db = InMemoryDatabaseGateway()
        face_searcher = MagicMock()
        face_searcher.search_face = AsyncMock()

        pipeline = CapturePipeline(
            detector=FakeDetector(),
            embedder=ArcFaceEmbedder(),
            db=db,
            face_searcher=face_searcher,
        )

        result = await pipeline.process(
            capture_id="cap_search02",
            data=_make_jpeg(),
            content_type="image/jpeg",
            person_name="Bob Jones",  # Name provided — face search skipped
        )

        assert result.success is True
        face_searcher.search_face.assert_not_called()

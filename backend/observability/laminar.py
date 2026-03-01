# RESEARCH: Checked lmnr SDK (0.7.x, official Laminar Python client)
# DECISION: Using lmnr.Laminar.initialize + @observe decorator for auto-tracing
# ALT: Raw OpenTelemetry spans (more control, way more boilerplate)

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

from loguru import logger

from config import Settings

F = TypeVar("F", bound=Callable[..., Any])

_initialized = False


def initialize_laminar(settings: Settings) -> bool:
    """Initialize Laminar SDK for tracing. Call once at app startup.

    Returns True if Laminar was successfully initialized, False otherwise.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return True

    if not settings.laminar_api_key:
        logger.warning("LMNR_PROJECT_API_KEY not set — Laminar tracing disabled")
        return False

    try:
        from lmnr import Laminar

        Laminar.initialize(project_api_key=settings.laminar_api_key)
        _initialized = True
        logger.info("Laminar tracing initialized")
        return True
    except Exception as exc:
        logger.error("Failed to initialize Laminar: {}", exc)
        return False


def laminar_ready(settings: Settings) -> bool:
    return bool(settings.laminar_api_key)


def observe_span(
    name: str | None = None,
    *,
    span_type: str = "DEFAULT",
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps a function in a Laminar @observe span.

    Falls back to a no-op passthrough when Laminar is not initialized.
    Works with both sync and async functions.
    """

    def decorator(fn: F) -> F:
        if not _initialized:
            return fn

        try:
            from lmnr import observe

            return observe(  # type: ignore[return-value]
                name=name or fn.__name__,
                span_type=span_type,  # type: ignore[arg-type]
                metadata=metadata,
            )(fn)
        except Exception:
            return fn

    return decorator  # type: ignore[return-value]


def traced(name: str, metadata: dict[str, Any] | None = None) -> Callable[[F], F]:
    """Lightweight timing + logging decorator that also feeds Laminar spans.

    Always logs duration/status even without Laminar.
    """

    def decorator(fn: F) -> F:
        import asyncio

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.monotonic()
                logger.debug("trace.start name={}", name)
                try:
                    result = await fn(*args, **kwargs)
                    elapsed = time.monotonic() - start
                    logger.info("trace.end name={} status=ok elapsed={:.2f}s", name, elapsed)
                    return result
                except Exception as exc:
                    elapsed = time.monotonic() - start
                    logger.error(
                        "trace.end name={} status=error elapsed={:.2f}s error={}",
                        name, elapsed, exc,
                    )
                    raise

            # Layer Laminar observe on top if available
            wrapped: Any = async_wrapper
            if _initialized:
                try:
                    from lmnr import observe

                    wrapped = observe(name=name, metadata=metadata)(async_wrapper)
                except Exception:
                    pass
            return wrapped  # type: ignore[return-value]

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.monotonic()
                logger.debug("trace.start name={}", name)
                try:
                    result = fn(*args, **kwargs)
                    elapsed = time.monotonic() - start
                    logger.info("trace.end name={} status=ok elapsed={:.2f}s", name, elapsed)
                    return result
                except Exception as exc:
                    elapsed = time.monotonic() - start
                    logger.error(
                        "trace.end name={} status=error elapsed={:.2f}s error={}",
                        name, elapsed, exc,
                    )
                    raise

            wrapped_sync: Any = sync_wrapper
            if _initialized:
                try:
                    from lmnr import observe

                    wrapped_sync = observe(name=name, metadata=metadata)(sync_wrapper)
                except Exception:
                    pass
            return wrapped_sync  # type: ignore[return-value]

    return decorator  # type: ignore[return-value]

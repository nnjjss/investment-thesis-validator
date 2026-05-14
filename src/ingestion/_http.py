from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = 30.0
RETRY_ATTEMPTS = 3


class RateLimitedError(Exception):
    """HTTP 429 from upstream — eligible for retry with backoff."""


class TransientUpstreamError(Exception):
    """HTTP 5xx from upstream — eligible for retry."""


_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    RateLimitedError,
    TransientUpstreamError,
    httpx.NetworkError,
    httpx.TimeoutException,
)


class AsyncHTTPClient:
    """Thin async httpx wrapper with retry, timeout, and structured logging.

    Designed for ingestion clients (FMP, NewsAPI, SEC EDGAR). Not for general
    application traffic.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        headers: dict[str, str] | None = None,
        max_attempts: int = RETRY_ATTEMPTS,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers or {},
        )
        self._log = logger.bind(base_url=base_url)
        self._max_attempts = max_attempts

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(_RETRYABLE_EXC),
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        ):
            with attempt:
                return await self._do_get_json(path, params=params, headers=headers)
        # Unreachable: AsyncRetrying with reraise=True either returns or raises.
        raise RuntimeError("retry loop exited without result")

    async def _do_get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> Any:
        response = await self._client.get(path, params=params, headers=headers)
        log = self._log.bind(path=path, status=response.status_code)

        if response.status_code == 429:
            log.warning("upstream_rate_limited")
            raise RateLimitedError(f"429 from {path}")
        if 500 <= response.status_code < 600:
            log.warning("upstream_transient_error")
            raise TransientUpstreamError(f"{response.status_code} from {path}")

        response.raise_for_status()
        log.debug("upstream_ok")
        return response.json()

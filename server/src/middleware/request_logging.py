"""Request logging middleware for FastAPI."""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from src.utils.logger import logger


SKIP_PATHS = {"/docs", "/redoc", "/openapi.json", "/favicon.ico", "/health"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()
        logger.debug(
            f"Incoming request: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}"
        )

        response = await call_next(request)
        response_time_ms = (time.perf_counter() - start_time) * 1000

        self._log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            response_time_ms=response_time_ms
        )
        return response

    def _log_request(self, method: str, path: str, status_code: int, response_time_ms: float) -> None:
        message = f"{method} {path} {status_code} - {response_time_ms:.0f}ms"
        if status_code >= 500:
            logger.error(message)
        elif status_code >= 400:
            logger.warning(message)
        else:
            logger.info(message)
